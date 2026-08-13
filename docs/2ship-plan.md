# Bringing the harness up on 2ship / Majora's Mask

## Context

This harness proved Torch can reproduce Shipwright's OoT asset extraction byte-for-byte
across 14 ROM targets. That job is finished and has moved on: Shipwright `develop` now
submodules Torch directly, checks its asset YAMLs in at `soh/assets/yml`, and builds
`oot.o2r` through a `soh-torch` static-lib CLI and an `ExtractAssets` CMake target.
OoT XML→YAML generation is retired; this repo no longer owns those files.

The same job now needs doing for Majora's Mask via 2ship2harkinian. Recon found:

- **Torch has no MM support whatsoever.** `src/factories/` has `oot/ sm64/ mk64/ sf64/
  pm64/ fzerox/ bk64/ mario_artist/ naudio/`. No MM directory, no `BUILD_MM`, no MM
  branch or PR upstream. This is greenfield and it is the bulk of the work.
- **2ship is structurally a twin of pre-migration Shipwright**: ZAPD XMLs at
  `mm/assets/xml/{N64_US,GC_US}` (660 files for N64_US), DMA filelists at
  `mm/assets/extractor/filelists/` (`mm.txt` 1552 lines, `mm_gc.txt` 1549), ZAPDTR +
  OTRExporter submodules, reference archive `mm.o2r`. Two supported ROMs per
  `docs/supportedHashes.json`: NTSC-U 1.0 `d6133ace…` and NTSC-U GC `9743aa02…`.
  (GC JP has a filelist but is not a supported hash.)
- **The OoT factories are small and cleanly hooked.** `src/factories/oot/` is ~5.5k lines
  across 45 files. The hooks into the common factories are fall-through escape hatches —
  `DisplayListFactory.cpp` tries `OoT::DListHelpers::SearchVtx` / `::Export` first and
  falls back to the generic path — guarded by only 7 `#ifdef OOT_SUPPORT` sites total.
  That pattern re-namespaces to `Zelda64::` almost mechanically.

Intended outcome: Torch produces an `mm.o2r` byte-identical to the ZAPD/OTRExporter
reference for NTSC-U 1.0, with OoT extraction provably unbroken throughout. 2ship itself
is **not** modified — no `mm/assets/yml`, no `mm-torch` CLI, no CMake target. This
harness owns the MM YAMLs, exactly as it originally owned the OoT ones.

## Hard constraints

**No ROM data may ever be committed.** This is why 2ship CI publishes `2ship.o2r`
(custom assets only) and never `mm.o2r`. Committed artifacts may contain hashes, names,
offsets, and counts — never ROM bytes. `roms/` and `o2r/` are already gitignored; the
2ship build lands in a gitignored `2ship-bin/` alongside the existing `shipwright-bin/`.
Every new committed file gets checked against this rule before it goes in.

**The `OOT:` type strings are a public contract.** Shipwright's checked-in
`soh/assets/yml` references `OOT:SKELETON`, `OOT:SCENE`, `OOT:AUDIO`, etc. The ZELDA64
refactor must not rename a single one of them.

## Already done (branch `2ship`, off `origin/code` `75fd416`)

- `0f98b71` on `dbg2-experiment` — parked the stray `config.yml` edit.
- `cabddbc` — `2ship/` submodule at `develop` `4c128e4cd`, nested submodules uninit'd.

## Phase 1 — Torch branch: rebase onto upstream main, land PR #253

Shipwright pins Torch at `e92c2103`, which is on **upstream `main`** (9 commits behind
current tip `2ab12fe9`). Our `torch/` submodule points at briaguya0/Torch
`oot-assets-torchonly` `9422bf4`, which GitHub reports as 174 commits diverged from main
— almost certainly because PR #219 was squash-merged upstream rather than fast-forwarded.

1. Establish the real content delta between `oot-assets-torchonly` and upstream `main`
   (`git diff upstream/main origin/oot-assets-torchonly -- src/`). If it is empty or
   near-empty, base all new work on upstream `main` and repoint this repo's `torch/`
   submodule there. Do not carry the stale branch forward on a guess.
2. New branch off that base, merge PR #253 head `f306edc` (`louist103/Torch-1:offsetfile`,
   64 lines across `src/Companion.{cpp,h}`). It adds a `filelist:` key on the ROM config
   pointing at a `Files:` name→offset YAML, and lets `segments:` entries and asset
   `offset:` fields be a DMA file *name* instead of a hex literal.
3. One fix on top of it: it gates on `StringHelper::IsValidHex`, which requires a `0x`
   prefix and length ≥ 3 (`src/utils/StringHelper.cpp:128`), so a bare `offset: 0` falls
   through to a filelist lookup and throws. `StringHelper::IsValidOffset` (same file,
   line 142) exists for exactly this case — use it.

   Otherwise leave the PR alone. The API rename it performs (`GetFileOffset` → `GetFileOffsetFromName`,
   `GetCurrSegmentNumber` dropping its `optional`) touches **zero** call sites — both are
   declared in `Companion.h` and never called — so the merge itself should be clean.

Gate: OoT invariance (see Verification).

## Phase 2 — Torch: split `oot/` into shared `zelda64/` + game-specific

Add `BUILD_ZELDA64` / `-DZELDA64_SUPPORT`, auto-enabled when `BUILD_OOT` or `BUILD_MM` is
on, following the existing `BUILD_OOT` shape at `CMakeLists.txt:210` (define + a
`list(FILTER SRC_DIR EXCLUDE …)` for the directory).

Move genuinely shared code to `src/factories/zelda64/` under a `Zelda64::` namespace, and
retarget the 7 `#ifdef OOT_SUPPORT` hook sites (`DisplayListFactory.{cpp,h}`,
`Companion.cpp:122,314`) at it. Keep `OOT:`-prefixed registrations pointing at whatever
class now implements them.

Expected split, **to be confirmed by reading each file rather than assumed**:

- *Likely shared* — `DeferredVtx`, `OoTDListHelpers` (759 lines), `OoTArrayFactory`,
  `OoTMtxFactory`, `OoTSkeletonFactory`/`Types`, `OoTLimbFactory`, `OoTAnimationFactory`,
  `OoTCurveAnimationFactory`, `OoTPathFactory`, `OoTCollisionFactory`, `OoTSceneUtils`,
  the `OoTAudio*` set. MM shares F3DEX2, segmented addressing, and most struct layouts.
- *Likely MM-divergent, keep game-specific* — `OoTSceneCommandWriter` (696 lines; scene
  and room command sets diverge most between the two games), `OoTSceneFactory`,
  `OoTCutsceneFactory`, `OoTTextFactory`, `OoTPlayerAnimationFactory` (`link_animetion`
  is OoT-only).

This phase changes no behaviour. It is pure code motion, which is what makes the
invariance gate below both meaningful and sufficient.

Gate: OoT invariance.

## Phase 3 — MM reference archive and manifest

1. Pull the `2ship-linux` AppImage artifact from a 2ship CI run at (or near) the pinned
   `4c128e4cd` into gitignored `2ship-bin/`. The AppImage bundles ZAPD plus
   `assets/xml` and `assets/Config_*.xml`, so it extracts without building
   ZAPDTR/OTRExporter locally. This mirrors the existing `shipwright-bin/` practice.
2. Run its extractor against a local NTSC-U 1.0 ROM (`d6133ace…`) → `mm.o2r`, kept local
   in `o2r/`. Fall back to a local ZAPDTR/OTRExporter build if the artifact is
   unavailable at the pinned commit.
3. `./manifest.sh o2r/mm.o2r manifests/mm_n64_us.json` — hashes and asset paths only,
   safe to commit. `manifest.sh` and `check.sh` are already game-agnostic (they only
   unzip, hash, and diff) and need **no changes**.

## Phase 4 — MM DMA and XML→YAML, in this harness

Repurpose the existing layout for MM and drop the OoT data — this branch does not care
about OoT. `dma/`, `supplemental/`, `manifests/`, and `assets/yml/` keep their shapes;
their contents become MM.

- `tools/extract_dma.py` — its `ROM_VERSIONS` table (name → filelist + DMA table offset)
  and `SHIPWRIGHT_FILELISTS` path become MM: `mm.txt` for N64 US, pointed at
  `2ship/mm/assets/extractor/filelists/`. The MM DMA table ROM offset has to be
  determined; the table format itself (4× big-endian u32, one entry per filelist line)
  is identical, so `extract_dma_table` is unchanged.
- `tools/zapd_to_torch.py` — rewritten MM-only. Emits, from the start:
  - `segments: - [6, object_link_child]` — DMA file **names**, not hex ROM addresses,
    via PR #253. The per-file `:config:` header becomes version-independent.
  - a per-version filelist YAML (`Files:` name → offset) generated from `dma/mm_*.json`,
    referenced by `filelist:` in `assets/yml/config.yml`.

  This is why #253 matters here rather than as an OoT retrofit: the OoT measurements show
  asset offsets are already segment-relative and identical across versions — only the
  `:config:` header differs. Making that header version-independent means adding GC US
  later is close to free instead of a second full YAML tree.
- `assets/yml/config.yml` — replaced with the two MM ROM SHA1s, output `mm.o2r`.
- `tools/test_assets.py` — its OoT assumptions get retargeted (`--rom-version` default,
  the hardcoded `oot.o2r` at line 223, the `-u 9.2.3` portVersion at line 213). The
  scratch-dir/externals machinery is game-agnostic and stays.
- `tools/generate_supplemental.py` — the OoT XML declared only ~18.5k of 35,386 assets;
  the rest had to be recovered from the reference archive. Expect the same gap for MM and
  the same need for a supplemental pass. Scope this only once Phase 5 has real numbers,
  since the exact shortfall is what tells us which categories need it.

## Phase 5 — Torch: MM factories

`BUILD_MM` / `-DMM_SUPPORT` / `src/factories/mm/` / `MM::` namespace / `MM:`-prefixed
registrations, alongside the existing `OOT:` block at `Companion.cpp:314`. Types that MM
shares outright register the shared `Zelda64::` factory under an `MM:` name; divergent
ones get an MM implementation.

This is the long grind. Drive it exactly as OoT was driven: run
`tools/test_assets.py --category …` against `manifests/mm_n64_us.json` and work
category by category — textures and DLists first (they bottom out most other types),
then skeletons/animations, collision, scenes/rooms, cutscenes, text, audio — until
`0 failed, 0 not generated, 0 not in reference`.

## Phase 6 — Full regression

- Full OoT matrix across every supported ROM, via Shipwright's `ExtractAssets`.
- MM GC US added as a second target — the point at which the Phase 4 filelist design
  either pays off or doesn't.

## Verification

**OoT invariance gate — run after every Torch change in Phases 1, 2, and 5.** Since
Phases 1–2 are behaviour-preserving, the check is byte-identity against a baseline, which
needs no reference manifest and no committed ROM data:

```sh
# Baseline, built once: shipwright develop with torch @ upstream main
cmake --build build --target ExtractAssets   # SOH_ROM_PATH=<pal_gc retail rom>
cp build/soh/oot.o2r o2r/reference.o2r

# After a change: same build, torch submodule @ our branch
cp build/soh/oot.o2r o2r/torch.o2r
./check.sh          # file lists + per-file sha256; exits non-zero on any diff
```

One ROM (pal_gc retail) per change; the full matrix is Phase 6. `check.sh` reports
missing / extra / mismatched counts and needs no modification.

**MM progress metric:** `python3 tools/test_assets.py <mm rom> --rom-version mm_n64_us`,
scored against `manifests/mm_n64_us.json`. Done is `0 failed, 0 not generated, 0 not in
reference`.

**Constraint check before every commit:** confirm no added file contains ROM bytes —
manifests are hashes, `dma/` and supplemental are offsets and names.

## Known unknowns to resolve during execution

- The MM DMA table ROM offset for NTSC-U 1.0 (Phase 4). 2ship's extractor knows it.
- Whether the 2ship AppImage extractor can be driven non-interactively, or whether it
  needs a GUI pass to produce `mm.o2r` (Phase 3).
- The real shared/divergent split in Phase 2 — the list above is a hypothesis from file
  sizes and naming, and each file needs reading before it moves.
