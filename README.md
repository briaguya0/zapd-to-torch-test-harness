# zapd-to-torch-test-harness — Majora's Mask

Test harness for verifying [Torch](https://github.com/HarbourMasters/Torch)'s
Majora's Mask asset extraction against a
[2ship2harkinian](https://github.com/HarbourMasters/2ship2harkinian)/ZAPD reference
archive, file by file.

Torch and 2ship are vendored as submodules so the whole thing is reproducible
independent of either repo.

```sh
git clone --recurse-submodules https://github.com/briaguya0/zapd-to-torch-test-harness.git
```

> The OoT side of this work is finished and has moved on: Shipwright now submodules
> Torch directly, checks its asset YAMLs in at `soh/assets/yml`, and builds `oot.o2r`
> itself. This branch is MM-only. OoT survives here purely as a regression signal —
> see [the gate](#the-oot-gate).

## Status

**Complete.** Every asset in the reference archive is reproduced byte for byte.

Against `manifests/ntsc_u.json` (50496 assets, OTRExporter reference for NTSC-U 1.0):

```
generated 50496 of 50496 reference assets
  PASS  50496
  FAIL      0
  EXTRA     0
```

OoT is unaffected throughout: `./tools/oot_gate.sh pal_gc` → 35386 matching, 0
mismatched.

Much of this rides on OoT's factories unchanged — MM runs the same engine and
shares most formats, which is the argument for a shared `zelda64/` namespace
rather than MM copies. TEXTURE (13542), MM:ANIMATION (1755), MM:PLAYER_ANIMATION
and its data (695 each) and MM:CURVE_ANIMATION (3) needed no factory work at all.
The rest needed either MM-specific behaviour inside the shared factories (scenes,
rooms, collision, cutscenes, display lists, skeletons, arrays) or new factories
of their own: MM:TEXTURE_ANIMATION (191), MM:KEYFRAME_SKELETON and
MM:KEYFRAME_ANIMATION (6 each), MM:TEXT (2).

### The reference is not stock

It is built from `briaguya0/2ship2harkinian` `deterministic-extraction`
(`95a0b33eb`), which carries two fixes without which the archive is not
reproducible at all — ZAPD writes uninitialized memory into it:

| Fix | What it was | Affected |
|-----|-------------|---------:|
| ZAPDTR `be1c68a` (#37) | `ZLimb`'s `totalVtxCount`/`dlist` uninitialized | 1929 limbs |
| `briaguya0/OTRExporter` `deterministic-arrays` | `ZArray` casts Pointer/CollisionPoly elements to `ZScalar` and writes the uninitialized `scalarType` | 3 arrays |

Rebuilding the manifest from an upstream-built o2r reintroduces both, and the
mismatches look like Torch regressions. See
[docs/decisions.md](docs/decisions.md) 38.

### Not done yet

- **GC US (`ntsc_u_gc`, sha1 `9743aa02`).** A second target, and the payoff for
  emitting segment bases as DMA file *names* — the YAML tree should carry over
  unchanged. No manifest yet. GC JP is out of scope; it is not in
  `supportedHashes.json`.
- **The `zelda64/` namespace refactor.** MM currently runs through factories
  named `OoT*`, which is now the wrong name for shared code.

| Doc | What's in it |
|-----|--------------|
| [docs/2ship-plan.md](docs/2ship-plan.md) | the plan, in phases |
| [docs/decisions.md](docs/decisions.md) | decisions and the options not taken |
| [docs/mm-status.md](docs/mm-status.md) | final scoreboard, per type |
| [docs/mm-remaining-work.md](docs/mm-remaining-work.md) | how the last 93 were diagnosed and closed |
| [docs/mm-dma.md](docs/mm-dma.md) | where the DMA offsets come from, and how they're verified |
| [docs/mm-yar-archives.md](docs/mm-yar-archives.md) | the CmpDma container format under `archives/` |

## Layout

```
torch/        Torch submodule (briaguya0/Torch mm-support; build to torch/build/torch)
2ship/        2ship submodule (briaguya0 deterministic-extraction; ZAPD XMLs + filelists)
tools/        converters, generators, and the two scoring drivers
assets/yml/   config.yml + <version>.filelist.yml (committed); <version>/ generated
dma/          DMA tables per ROM version
manifests/    sha256 manifests of the reference archive
supplemental/ per-version metadata recovered from the reference
o2r/          reference + generated archives (gitignored, local)
roms/mm/      MM ROMs; roms/oot/ OoT ROMs (gitignored, local)
```

**No ROM data is ever committed.** `roms/` and `o2r/` are `*`-ignored. Committed
artifacts hold hashes, names, offsets, and counts only. This is why 2ship CI
publishes `2ship.o2r` (custom assets) and never `mm.o2r`.

## Building Torch

Needs `cmake`, `ninja`, `libbz2-dev`, and a C++20 compiler.

```sh
cd torch
cmake -H. -Bbuild -GNinja -DCMAKE_BUILD_TYPE=Debug -DPORT_VERSION_ENDIANNESS=ON
cmake --build build -j
```

`-DPORT_VERSION_ENDIANNESS=ON` matches OTRExporter, which writes the `portVersion`
file with a leading endianness byte. Without it every asset still matches but that
one metadata file does not.

## The pipeline

```
2ship XML ─┐
ROM ───────┼─ extract_dma.py ──▶ dma/ntsc_u.json ──▶ make_filelist.py ──▶ filelist yml
           │                            │
           └── zapd_to_torch.py ◀───────┘──▶ assets/yml/ntsc_u/ ──torch──▶ mm.o2r
                      ▲                                                      │
     supplemental/ntsc_u.json                                          score.sh
                      ▲                                                      │
     generate_supplemental.py ◀── reference mm.o2r              manifests/ntsc_u.json
```

### 1. Reference archive and manifest

The reference comes from running a 2ship CI build (the `2ship-linux` AppImage,
which bundles ZAPD) against a local ROM. It stays local; only its hashes are
committed.

```sh
./manifest.sh o2r/ntsc_u_d6133a.o2r manifests/ntsc_u.json
```

### 2. DMA table and filelist

```sh
python3 tools/extract_dma.py
python3 tools/make_filelist.py dma/ntsc_u.json assets/yml/ntsc_u.filelist.yml
```

Table offsets come from OTRExporter's `rom_info.py` and are **verified on every
run**, not trusted — see [docs/mm-dma.md](docs/mm-dma.md) for why.

Segment bases are emitted as DMA file *names*, not hex ROM offsets, and Torch
resolves them through the filelist ([Torch PR #253](https://github.com/HarbourMasters/Torch/pull/253)).
That keeps each file's `:config:` version-independent, so a second ROM version
reuses the same YAML tree.

### 3. YAMLs

```sh
python3 tools/generate_supplemental.py \
    o2r/ntsc_u_d6133a.o2r roms/mm/ntsc_u_d6133a.z64 \
    dma/ntsc_u.json supplemental/ntsc_u.json

python3 tools/zapd_to_torch.py \
    --xml-dir 2ship/mm/assets/xml/N64_US \
    --dma-json dma/ntsc_u.json \
    --supplemental-json supplemental/ntsc_u.json \
    --out-dir assets/yml/ntsc_u
```

The XML declares 23477 assets; the reference holds 50496. The rest — Vtx arrays,
child DLists, limbs, skeletons, animations, collision — are recovered from the
reference by `generate_supplemental.py`, which adds 23329 more. Without it most
of the archive is missing.

### 4. Score

```sh
./tools/score.sh              # everything
./tools/score.sh Texture      # one type, plus its dependencies
```

Failures are attributed to the declaring asset type, so a run says which factory is
wrong rather than only how many assets are.

## The OoT gate

Torch's OoT factories are shared code that the MM work keeps touching, so every
Torch change is checked against OoT:

```sh
./tools/oot_gate.sh pal_gc      # 35386 matching, 0 mismatched
```

It needs no Shipwright build — which is why there is no `shipwright/` submodule. The
OoT manifest and config are recovered from git history (this branch deleted them in
`a20b505`), the YAML trees are already in the working tree, and the ROMs are in
`roms/oot/`. Nothing it recovers is committed.
