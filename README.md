# zapd-to-torch-test-harness

Test harness for verifying [Torch](https://github.com/HarbourMasters/Torch)'s
OoT asset extraction against a Shipwright/OTRExporter reference O2R, file by file.

Torch and Shipwright are vendored as submodules so the whole thing is
reproducible independent of the Torch repo itself.

```sh
git clone --recurse-submodules https://github.com/briaguya0/zapd-to-torch-test-harness.git
```

## Submodules

| Path | Repo | Pinned commit | Notes |
|------|------|---------------|-------|
| `torch/` | briaguya0/Torch `oot-assets-torchonly` | `de68e4b` | PR #219 head — OoT factories, no scaffolding |
| `shipwright/` | briaguya0/Shipwright `fix-skinvtxcnt-ub` | `b48e5f7` | dev + [ZAPDTR PR #37](https://github.com/HarbourMasters/ZAPDTR/pull/37); builds the reference O2R |

## Layout

```
torch/        Torch submodule (build to torch/build/torch)
shipwright/   Shipwright submodule (builds OTRExporter → reference O2R)
tools/        Python/shell helpers (zapd_to_torch.py, extract_*, test_assets.py, ...)
assets/yml/   config.yml (committed) + per-version YAMLs (gitignored, generated)
dma/          DMA tables per ROM version
manifests/    sha256 manifests of reference O2R contents (14 files, 17 ROMs)
vtx/          pre-computed VTX metadata per version
o2r/          reference.o2r / generated.o2r (gitignored, local)
roms/         OoT ROMs (gitignored, local)
logs/         torch run logs (gitignored)
lib.sh check.sh verify.sh manifest.sh   test drivers
```

## The workflow

The loop, at a glance:

```
shipwright @ b48e5f7 + PAL GC ROM ──OTRExporter──▶ reference.o2r ──manifest.sh──▶ manifests/pal_gc.json
                                                                                        │
shipwright XML ──zapd_to_torch.py──▶ YAMLs ──torch o2r──▶ oot.o2r ──test_assets.py/check.sh──┘ (compare)
```

### 1. Reference O2R (the "correct" output)

- **Shipwright build:** `shipwright/` submodule at `b48e5f7`.
- **ROM:** Legend of Zelda, The - Ocarina of Time (Europe) (GameCube), PAL GC,
  SHA1 `0227D7C0074F2D0AC935631990DA8EC5914597B4`. 35,386 assets.
- Build Shipwright and run **OTRExporter** against the ROM → this is the
  reference O2R. Store it locally (gitignored) as `o2r/reference.o2r`
  (naming convention `pal_gc_0227d7.o2r`).

Hash it into a manifest for fast per-asset comparison:

```sh
./manifest.sh o2r/reference.o2r manifests/pal_gc.json
```

> The reference is the fork branch, **not upstream SoH** — rebuilding against
> current SoH dev would drift the hashes. ZIP archives aren't byte-deterministic,
> so comparison is always file-by-file within the extracted archive.

### 2. Generate the YAMLs

Convert Shipwright XML → Torch YAML:

```sh
python3 tools/zapd_to_torch.py \
    --xml-dir shipwright/soh/assets/xml/GC_NMQ_PAL_F \
    --dma-json dma/pal_gc.json \
    --out-dir  assets/yml/pal_gc \
    --vtx-json vtx/pal_gc.json
```

`assets/yml/pal_gc/` is gitignored — regenerate locally. `assets/yml/config.yml`
is hand-maintained and committed (ROM SHA1 → `pal_gc`, gbi `F3DEX2_OoT`,
`primary_virtual_segment: 0x80`, output `oot.o2r`).

Supporting inputs (already committed; this is how they were produced):

- `dma/*.json` ← `tools/extract_dma.py`
- `vtx/*.json` ← `python3 tools/extract_vtx.py <reference.o2r> vtx/pal_gc.json`
- `tools/extract_rom_assets.py` → MTX offsets + `Set_` alternate headers from ROM+DMA

### 3. Generate the Torch O2R and compare

Build Torch to `torch/build/torch`, then the core invocation (from `test_assets.py`):

```sh
torch/build/torch o2r -s <yml-dir> -d <out-dir> -u 9.2.0 roms/pal_gc_0227d7.z64
# → <out-dir>/oot.o2r
```

`-u 9.2.0` is the portVersion; `verify.sh` omits it for subset runs.

Three ways to run + compare, by scope:

| Script | Scope | What it does |
|--------|-------|--------------|
| `python3 tools/test_assets.py <rom> [--category/--file/--type]` | full or filtered | runs torch, hashes assets vs `manifests/<ver>.json`, writes `o2r/generated.o2r` |
| `./verify.sh <rom> <asset-path>…` | a few named assets | copies just those YAMLs (+externals) to a scratch dir, runs torch, compares |
| `./check.sh` | whole archive | extracts `o2r/reference.o2r` vs `o2r/torch.o2r` and diffs file lists + sha256 |

`ROM_VERSION` env var (default `pal_gc`) selects which manifest / yml dir is used.
