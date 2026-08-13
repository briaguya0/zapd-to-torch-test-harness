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

### 15. DMA offsets are sourced from OTRExporter and verified, not hardcoded

`OTRExporter/rom_info.py` is the authoritative source — it is what ZAPD uses to
locate the table, so it is by construction the offset that produced our
reference. MM NTSC-U 1.0 is `0x1A500` with `mm.txt`; GC US is `0x1AE90` with
`mm_gc.txt`. It keys on ROM CRC (bytes `[16:20]`), not SHA1.

`extract_dma.py` now **verifies** the offset on every run rather than trusting
it: the `dmadata` entry must self-reference the table's location, and the entry
count must match the filelist length. The OoT side had neither check, and its
`ntsc_1-2` offset was wrong for a while — the misaligned table dropped `code`
entirely and corrupted the generated supplemental (harness commit `00bbf35`).
Both checks reject a one-entry misalignment, which is that exact failure mode.

Full write-up in `mm-dma.md`.

*Rejected:* locating the table by structural scan. Written and nearly run before
finding `rom_info.py` — self-validating, but it reinvents a lookup that already
exists in the toolchain that produced the reference. The self-reference check
keeps the useful half of the idea.

### 16. Absent DMA entries are flagged, not dropped or silently emitted

17 of MM's 1552 entries have `phys_start == phys_end == 0xFFFFFFFF`: present in
the virtual map, absent from the ROM. OoT has no such entries and its extractor
had no concept of them — it would have emitted `0xFFFFFFFF` as a real segment
base. They carry `"absent": true` so downstream can skip them deliberately, and
so the 17 names aren't quietly lost either.

### 17. The filelist emits `phys_start`, and omits absent entries

`phys_start` is the ROM offset a segment base points at, so that is what the
`Files:` map carries. The 17 absent entries are **left out** rather than emitted
with their `0xFFFFFFFF`: naming one then fails loudly at extraction instead of
silently producing a segment pointed at `0xFFFFFFFF`.

Lives at `assets/yml/<version>.filelist.yml`, whitelisted in
`assets/yml/.gitignore`. `filelist:` in the rom config is a sibling of `path:`,
resolved against the `-s` directory — not inside `config:`.

### 18. PR #253 verified against a real ROM before anything depends on it

Rather than assume it works, a control test: the same BLOB addressed by DMA file
name versus by hex ROM address, extracted from the MM ROM, must be byte-identical.
It is — both for an uncompressed file (`dmadata`) and a Yaz0-compressed one
(`object_link_child`, the 1513-of-1552 case).

The bare-`0` fix (decision 7) was verified the same way, by reverting it and
rebuilding: `offset: 0` aborts with `std::out_of_range` from
`unordered_map::at` and produces no archive at all. Restoring it reproduces the
correct output byte-for-byte. So the fix guards a case that genuinely breaks,
which was previously only a claim.

### 19. `zapd_to_torch.py` converted in place to MM, not rewritten

Most of the 968 lines are game-agnostic (XML walking, YAML formatting, external
file resolution, supplemental injection). What changed: the type map, the removal
of Master Quest handling, the scene path rules, and segment bases becoming DMA
names.

MM-specific types are emitted with an `MM:` prefix even though **no MM factory
exists in Torch yet**. That is deliberate — emitting them is how we find out what
still has to be written. Only the shared factories (TEXTURE, BLOB, GFX, VTX)
produce anything today.

`--types` now pulls in only the dependencies the request actually needs
(`DList`→Vtx/Array/Mtx, `Skeleton`→Limb). It used to add all of them
unconditionally, which made a texture-only run also emit `MM:MTX` and abort.
Partial runs additionally prune `external_files` entries pointing at YAMLs that
run didn't generate; on a full run they are left alone, since a dangling
reference there is a real bug worth seeing.

### 20. Two MM path conventions had to be read off the reference, not assumed

Both were initially wrong in the obvious-looking direction:

- **Scenes keep the `nonmq` prefix.** MM has no Master Quest, so dropping it
  looked right. The reference emits `scenes/nonmq/<SCENE>/<asset>` with no
  `shared/` or `mq/` sibling. The scene directory is also the bare scene name —
  no `_scene` suffix as in OoT.
- **`interface/` and `archives/` are flattened away.** `interface/parameter_static/X`
  in the XML tree is `parameter_static/X` in the archive. This accounted for all
  4941 "extra" assets in the first scored run; every one had its basename in the
  reference under a different directory.

### 21. `_yar` archives need a Torch container format, not a config tweak

The 520 remaining texture failures are exactly the `archives/*_yar` files. They
are not plain data at their DMA offset: the file opens with a table of u32
offsets to sub-files, the first of which carries a `Yaz0` magic and a
decompressed size of `0x900` — exactly one 24×24 RGBA32 texture. The DMA entry
reports the file uncompressed (`phys_end == 0`), so Torch reads the container
bytes directly and every texture in it comes out as garbage.

This is an MM-specific container Torch has no concept of, so it is Phase 5 work,
not a YAML or config fix.

### 22. Reference o2r archives are disposable; the manifests are the reference

`test_assets.py` scores against `manifests/<version>.json`, not against an
archive, so the archives themselves need not be kept once hashed.
