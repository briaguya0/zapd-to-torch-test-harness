# zapd-to-torch-test-harness

Test harness for verifying [Torch](https://github.com/HarbourMasters/Torch)'s
OoT asset extraction against a Shipwright/OTRExporter reference O2R, file by file.

Torch and Shipwright are vendored as submodules so the whole thing is
reproducible independent of the Torch repo itself.

```sh
git clone --recurse-submodules https://github.com/briaguya0/zapd-to-torch-test-harness.git
```

## Status

Latest full-matrix run (`torch` at `oot-assets-torchonly` `7b7c50d`). "Clean" =
byte-for-byte identical to the reference O2R (0 failed, 0 not-generated, 0 extra).

| Version | ROM(s) | Assets | Status |
|---------|--------|-------:|--------|
| pal_gc | PAL GC | 35386 | ✅ clean |
| ntsc_u_gc | USA GC | 39066 | ✅ clean |
| ntsc_j_gc | JP GC | 39064 | ✅ clean |
| ntsc_j_gc_collection | JP GC (Zelda Collection) | 39066 | ✅ clean |
| pal_1-0 | PAL N64 1.0 | 35362 | ✅ clean |
| pal_1-1 | PAL N64 1.1 | 35362 | ✅ clean |
| ntsc_1-0 | JP + USA N64 1.0 | 38390 | ✅ clean |
| ntsc_1-1 | JP + USA N64 1.1 | 38526 | ✅ clean |
| ntsc_u_mq | USA GC Master Quest | 33762 | ⚠️ 5267 not generated (MQ discovery gap) |
| ntsc_j_mq | JP GC Master Quest | 33759 | ⚠️ 5267 not generated (MQ discovery gap) |
| pal_mq | PAL GC Master Quest | 30084 | ⚠️ 5267 not generated + 1 failed |
| pal_gc_dbg | PAL GC (Debug) | 35645 | ⚠️ 1 failed + 8 extras (syotes debug stub scene) |
| pal_mq_dbg | PAL GC MQ (Debug, 3 dumps) | 30342 | ⚠️ 5267 not generated + syotes stub scene |
| ntsc_1-2 | JP + USA N64 1.2 | — | ❌ Torch SIGSEGV (no O2R) |

**8 of 14 targets clean.** Remaining: MQ asset-discovery gap (~5267 assets), the
`syotes` debug stub scene on the debug ROMs, and a Torch crash on the 1.2 ROMs.

## Submodules

| Path | Repo | Pinned commit | Notes |
|------|------|---------------|-------|
| `torch/` | briaguya0/Torch `oot-assets-torchonly` | `7b7c50d` | PR #219 head — OoT factories, no scaffolding |
| `shipwright/` | HarbourMasters/Shipwright `develop` | `95d8f7e` | upstream SoH (ZAPD bump #6952); builds the reference O2R |

## Layout

```
torch/        Torch submodule (build to torch/build/torch)
shipwright/   Shipwright submodule (builds OTRExporter → reference O2R)
tools/        Python/shell helpers (zapd_to_torch.py, extract_*, test_assets.py, ...)
assets/yml/   config.yml (committed) + per-version YAMLs (gitignored, generated)
dma/          DMA tables per ROM version
manifests/    sha256 manifests of reference O2R contents (14 files, 17 ROMs)
supplemental/ per-version supplemental asset metadata (from generate_supplemental.py)
o2r/          reference.o2r / generated.o2r (gitignored, local)
roms/         OoT ROMs (gitignored, local)
logs/         torch run logs (gitignored)
lib.sh check.sh verify.sh manifest.sh   test drivers
```

## Building Torch

Torch needs `cmake`, `ninja`, and `libbz2-dev` (plus a C++20 compiler). Build it
into `build/` so the binary lands at `torch/build/torch`, where the harness scripts
look for it:

```sh
cd torch
cmake -H. -Bbuild -GNinja -DCMAKE_BUILD_TYPE=Debug -DPORT_VERSION_ENDIANNESS=ON
cmake --build build -j
```

- `BUILD_OOT` is ON by default on the pinned commit, so the OoT factories are
  compiled in.
- **`-DPORT_VERSION_ENDIANNESS=ON` is required to match the reference.** It's OFF
  by default, but OTRExporter writes the `portVersion` file with a leading
  endianness byte (7 bytes: `01` + 3× uint16 BE). Without this flag every asset
  still matches but the `portVersion` metadata file fails (6 bytes vs 7).

## The workflow

The loop, at a glance:

```
shipwright @ 95d8f7e + PAL GC ROM ──OTRExporter──▶ reference.o2r ──manifest.sh──▶ manifests/pal_gc.json
                                                                                        │
shipwright XML ──zapd_to_torch.py──▶ YAMLs ──torch o2r──▶ oot.o2r ──test_assets.py/check.sh──┘ (compare)
```

### 1. The reference manifest (already shipped)

The "correct" output is a reference O2R produced by Shipwright/OTRExporter. Rather
than require everyone to build Shipwright, **this repo already ships the sha256
manifests** in `manifests/`, generated from the exact Shipwright version pinned as
the `shipwright/` submodule (`95d8f7e`). `manifests/pal_gc.json` has 35,386 entries
— one sha256 per asset in the reference PAL GC O2R.

That means you can start comparing Torch output immediately; you do **not** need a
reference O2R or a Shipwright build just to run the tests.

If you do have a reference O2R (e.g. from a CI build of the submodule commit — the
reference is generated on GitHub Actions, then dropped into `o2r/`), you can
regenerate the manifest and confirm it matches what's checked in:

```sh
./manifest.sh o2r/pal_gc_0227d7.o2r /tmp/regen.json
diff <(jq -S . manifests/pal_gc.json) <(jq -S . /tmp/regen.json) && echo MATCH
```

> ✅ **Verified:** regenerating from the CI reference O2R of `95d8f7e` reproduces
> `manifests/pal_gc.json` exactly (35,386 entries, all hashes identical). The
> reference build is reproducible.

> Notes: the reference is pinned to a **specific** SoH commit (`95d8f7e`) —
> rebuilding against a newer SoH dev would drift the hashes, so bump the submodule
> and regenerate the manifests together. ZIP archives aren't byte-deterministic,
> so comparison is always file-by-file within the extracted archive, never a hash
> of the whole `.o2r`.

- **ROM:** Legend of Zelda, The - Ocarina of Time (Europe) (GameCube), PAL GC,
  SHA1 `0227D7C0074F2D0AC935631990DA8EC5914597B4`, placed at `roms/pal_gc_0227d7.z64`.

### 2. Generate the YAMLs

`zapd_to_torch.py` needs two committed data inputs besides the Shipwright XML: a
**DMA table** and the **supplemental metadata**. Both ship in the repo.

**DMA tables (`dma/`)** — file → ROM offsets, produced by `extract_dma.py`. It
reads each ROM in `roms/` plus the matching **filelist**, which is not something
this harness produces: the filelists are vendored upstream assets that ship inside
Shipwright at `shipwright/soh/assets/extractor/filelists/` (e.g. PAL GC uses
`gamecube_pal.txt`, a ~1510-line list of files in DMA order, maintained in the
Shipwright repo). `extract_dma.py` reads the filelist at a per-version ROM offset
(PAL GC: `0x7170`):

```sh
python3 tools/extract_dma.py roms dma
```

> ✅ **Verified:** regenerating from `roms/pal_gc_0227d7.z64` + the submodule's
> `gamecube_pal.txt` reproduces `dma/pal_gc.json` exactly (1510 entries).

**Supplemental metadata (`supplemental/`)** — the XML alone declares ~18.5k of the
35,386 assets; the rest (VTX arrays, child DLists, limbs, collision, `Set_`
alternate headers, MTX offsets, …) are not in the XML and must be supplied so
Torch emits them under the exact reference names. `generate_supplemental.py`
produces one JSON with all of it from the reference O2R + ROM + DMA:

```sh
python3 tools/generate_supplemental.py \
    o2r/pal_gc_0227d7.o2r roms/pal_gc_0227d7.z64 dma/pal_gc.json \
    supplemental/pal_gc.json
```

`supplemental/pal_gc.json` is committed, so you don't need a reference O2R just to
generate the YAMLs — only regenerate it when bumping the `shipwright/` submodule.

Now convert Shipwright XML → Torch YAML, injecting the supplemental data:

```sh
python3 tools/zapd_to_torch.py \
    --xml-dir shipwright/soh/assets/xml/GC_NMQ_PAL_F \
    --dma-json dma/pal_gc.json \
    --out-dir  assets/yml/pal_gc \
    --supplemental-json supplemental/pal_gc.json
```

Expected output — **two** lines (the second only prints when `--supplemental-json`
is passed):

```
Wrote 1065 YAML files with 18554 assets
Added 13017 supplemental assets to 1236 YAML files
```

→ **1450** YAML files (`find assets/yml/pal_gc -name '*.yml' | wc -l`).

**Don't expect 35,386 here.** These counts are what the *YAML declares*
(18554 + 13017 = **31571**), not the final asset count. Torch discovers the
remaining ~3,800 during extraction (DLists → sub-DLists/textures, scenes → rooms,
skeletons → limbs, …), so the O2R produced in step 3 ends up with the full 35,386.

Common gotcha: `18554` is just the **first** line — if you stop reading there it
looks like assets are missing. Without `--supplemental-json` at all, only that
first line prints (1065 files, ~18.5k assets) and step 3 leaves ~12k "not
generated"; the supplemental injection is what closes the gap.

`assets/yml/pal_gc/` is gitignored — regenerate locally. `assets/yml/config.yml`
is hand-maintained and committed (ROM SHA1 → `pal_gc`, gbi `F3DEX2_OoT`,
`primary_virtual_segment: 0x80`, output `oot.o2r`).

### 3. Generate the Torch O2R and compare

Build Torch to `torch/build/torch`, then the core invocation (from `test_assets.py`):

```sh
torch/build/torch o2r -s <yml-dir> -d <out-dir> -u 9.2.3 roms/pal_gc_0227d7.z64
# → <out-dir>/oot.o2r
```

`-u 9.2.3` is the portVersion (SoH `95d8f7e` stamps 9.2.3); `verify.sh` omits it
for subset runs.

Three ways to run + compare, by scope:

| Script | Scope | What it does |
|--------|-------|--------------|
| `python3 tools/test_assets.py <rom> [--category/--file/--type]` | full or filtered | runs torch, hashes assets vs `manifests/<ver>.json`, writes `o2r/generated.o2r` |
| `./verify.sh <rom> <asset-path>…` | a few named assets | copies just those YAMLs (+externals) to a scratch dir, runs torch, compares |
| `./check.sh` | whole archive | extracts `o2r/reference.o2r` vs `o2r/torch.o2r` and diffs file lists + sha256 |

`ROM_VERSION` env var (default `pal_gc`) selects which manifest / yml dir is used.

> ✅ **Current result (PAL GC):** `35386 passed, 0 failed, 0 not generated, 0 not
> in reference` — Torch reproduces the OoT PAL GC O2R byte-for-byte against the
> `95d8f7e` reference, given the `-DPORT_VERSION_ENDIANNESS=ON` build and the
> supplemental-injected YAMLs.
