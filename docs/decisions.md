# Decision log

Decisions taken while bringing the harness up on 2ship / MM, with the reasoning
behind them. Newest at the bottom. The plan itself lives in `2ship-plan.md`;
this records *why* it looks the way it does, including the options not taken.

## 2026-08-13

### 1. Branch `2ship` off `origin/code`, not off the working branch

`dbg2-experiment` had six unmerged commits and a dirty `config.yml`. That edit
(distinct `oot-mq.o2r` output name, second PAL GC debug dump) was committed to
`dbg2-experiment` as `0f98b71` and left there rather than carried onto the new
branch — it belongs to the OoT experiment, not to MM.

### 2. 2ship vendored as a submodule, nested submodules left uninitialized

`2ship/` tracks `HarbourMasters/2ship2harkinian`. Its own submodules
(`libultraship`, `ZAPDTR`, `OTRExporter`) are not initialized: the ZAPD XMLs and
DMA filelists this harness needs live in the parent repo, and ZAPDTR/OTRExporter
are only required to build a reference archive — which we get from a CI build
instead (see 11).

### 3. Scope: Torch output parity only; 2ship is not modified

No `mm/assets/yml` in 2ship, no `mm-torch` CLI, no `ExtractAssets` target.

*Rejected:* mirroring Shipwright's migration (which now submodules Torch, checks
its YAMLs in at `soh/assets/yml`, and builds `oot.o2r` itself). That is the
obvious endgame, but whether 2ship ever switches is a separate decision to make
after parity is proven, not a precondition for proving it. This harness owns the
MM YAMLs meanwhile, exactly as it originally owned the OoT ones.

### 4. NTSC-U 1.0 first, GC US later, GC JP never

`docs/supportedHashes.json` in 2ship lists exactly two ROMs: NTSC-U 1.0
(`d6133ace…`) and NTSC-U GC (`9743aa02…`). A `mm_gc_jp.txt` filelist exists but
no matching XML directory and no supported hash, so GC JP is out of scope.

### 5. No OoT XML→YAML work on this branch

OoT YAML generation is retired — Shipwright checks those files in and owns them.
This branch does not care about OoT except as a regression signal.

*Consequence:* the offset-file work (7) is adopted fresh for MM rather than
retrofitted onto OoT.

### 6. Torch work is based on upstream `main`, on a fork branch

The submodule tracked `briaguya0/Torch oot-assets-torchonly` at `9422bf4`, which
GitHub reports as 174 commits diverged from upstream `main` — an artifact of PR
#219 being squash-merged rather than fast-forwarded. Shipwright builds OoT
against upstream `main` (pinned at `e92c2103`), so that is the base the MM work
has to share.

New branch `mm-support` starts at upstream `main` `2ab12fe`. The submodule URL
stays on the **fork**, since the ZELDA64 refactor and MM factories land there and
need somewhere to push.

*Rejected:* reconciling the 174-commit delta first. Not worth the time when the
base we need is unambiguous.

### 7. Torch PR #253 merged, with exactly one change on top

PR #253 (offsets read from an external filelist) fast-forwarded cleanly onto
current upstream main. The one modification is `IsValidHex` → `IsValidOffset` in
`GetFileOffsetFromNodeStr`: `IsValidHex` demands an `0x` prefix and length ≥ 3,
so a bare `offset: 0` would fall through to a filelist lookup and throw.

*Rejected — replacing `gFileOffsets.at()` with an explanatory throw.* Proposed as
a defect, but there was no evidence it causes a real problem; it was speculative
polish on someone else's PR. The PR's code stands.

*Rejected — a decimal-offset branch alongside the fix.* Checked instead of
guessed: zero non-`0x` offsets across all 14 OoT version trees (~20k offsets), so
it was dead code.

### 8. Shared Torch factories move to `zelda64/`, and `OOT:` type strings are frozen

Shared code goes to `src/factories/zelda64/` under `Zelda64::`, behind
`BUILD_ZELDA64` / `-DZELDA64_SUPPORT`, with `oot/` and `mm/` referencing it. The
existing `#ifdef OOT_SUPPORT` hooks are already fall-through escape hatches
(`DisplayListFactory` tries `OoT::DListHelpers::…` first, generic path after), so
the pattern re-namespaces mechanically.

**The `OOT:` type strings must not be renamed.** They are a public contract with
Shipwright's checked-in `soh/assets/yml`.

### 9. OoT regression: one ROM per change, full matrix at the end

Per-change gate is a single pal_gc retail extraction through Shipwright's
`ExtractAssets`, compared byte-for-byte. The full ROM matrix runs once, late.
Phases 1–2 are behaviour-preserving, so byte-identity against a baseline is both
meaningful and sufficient.

### 10. No ROM data is ever committed

This is why 2ship CI publishes `2ship.o2r` (custom assets only) and never
`mm.o2r`. Committed artifacts may contain hashes, names, offsets, and counts —
never ROM bytes. `roms/` and `o2r/` are `*`-ignored with only `.gitignore` and
`README.md` whitelisted. Every new committed file is checked against this before
it goes in.

### 11. Reference archive comes from a CI build run locally against a local ROM

The `2ship-linux` AppImage bundles ZAPD plus `assets/xml` and `assets/Config_*.xml`,
so it extracts without building ZAPDTR/OTRExporter. The archive it produces stays
local. This mirrors the existing `shipwright-bin/` practice.

### 12. Version key is `ntsc_u`, following the repo's existing convention

Not `mm_n64_us` as the plan first invented, and not 2ship's own `N64_US`. The ROM
is `roms/mm/ntsc_u_d6133a.z64` (`<version>_<first 6 of sha1>.z64`, per
`tools/identify_roms.sh`), so the version is `ntsc_u` and GC US will be
`ntsc_u_gc`. Reference archive mirrors the ROM basename:
`o2r/ntsc_u_d6133a.o2r`.

### 13. 2ship submodule pinned to the commit that produced the reference

Moved *back* two commits, `4c128e4cd` → `d35196ad7`, to name the commit the CI
build came from. `mm/assets/xml` and `mm/assets/extractor` are byte-identical
across those two commits, so nothing about the inputs changes — the repin is
purely so the reference's provenance is exact rather than approximately right.

### 14. OoT data deleted from this branch

48 per-version JSONs removed: 14 manifests, 17 DMA tables, 17 supplemental
metadata files. The extraction they scored is finished and lives in Shipwright.

Deleting also cleared a collision that was coming: MM's GC US target is
`ntsc_u_gc`, which was an OoT manifest key.

*Not deleted:* `assets/yml/config.yml`, which still holds the 17 OoT ROM hashes.
It needs replacing rather than removing, and writing MM entries means choosing a
gbi version, `primary_virtual_segment`, and sort mode — values worth deriving in
Phase 4 rather than guessing now.

### 15. Reference o2r archives are disposable; the manifests are the reference

`test_assets.py` scores against `manifests/<version>.json`, not against an
archive, so the archives themselves need not be kept once hashed.
