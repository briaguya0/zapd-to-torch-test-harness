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

The 520 remaining texture failures are exactly the seven files under
`archives/`. They are CmpDma containers: a table of `u32` offsets followed by one
Yaz0 stream per texture, loaded in-game by `CmpDma_LoadFile`. The format is
defined by `CmpDma_GetFileInfo` in `2ship/mm/src/code/sys_cmpdma.c` — found by
looking for who already knows the format rather than reverse-engineering it, the
same move that found the DMA offsets in `rom_info.py`.

The DMA entry correctly says the container is uncompressed; the compression is one
level down, so Torch's magic-sniffing sees no header and reads raw container
bytes. Verified across all seven: sub-file count equals XML texture count and total
decompressed size equals the highest XML offset plus its size, exactly.

Fix is a new `CompressionType` that walks the table and concatenates the sub-files
— every existing offset path then works unchanged, because the XML offsets already
address that concatenation. It must be an **explicit YAML opt-in, not
auto-detection**: a container starts with its `dataStart` word (`0000003C`), which
is plausible leading data for an unrelated file. Explicit opt-in also keeps the
change additive, so OoT extraction cannot be affected.

**Implemented** in torch `mm-support` `3256012` as `CompressionType::CMPDMA`,
opt-in via `compression: CMPDMA`. MM textures went 9495/10014 → 10014/10014
byte-identical. Full write-up in `mm-yar-archives.md`.

*Rejected:* Torch's existing `preprocess:` hook. It decompresses the whole ROM
(`mio0-comptool`), which is the wrong layer for a per-file container.

### 22. Reference o2r archives are disposable; the manifests are the reference

`test_assets.py` scores against `manifests/<version>.json`, not against an
archive, so the archives themselves need not be kept once hashed.

### 23. MM: types resolve to the OoT factories, and that is measured not assumed

MM runs on the same engine as OoT and declares the same formats, so `MM:` names
were registered against the existing OoT factories and the result scored per type.
TEXTURE (13542/13542), MM:ANIMATION (1755/1755), MM:PLAYER_ANIMATION (695/695) and
MM:MTX (11/11) come out byte-identical with no MM code at all.

That is the evidence for phase 2: those factories move to a shared `zelda64/`
namespace rather than being copied. Types that do *not* match — limbs, cutscenes,
text — are the ones that earn real MM implementations. Current standing:
`mm-status.md`.

Shared code had to learn both prefixes: `OoTDListHelpers` hardcoded `OOT:ARRAY`
and `OOT:MTX`. `ExportMtx` could not simply try each candidate, because
`GetSafeStringByAddr` throws when a node exists with a different type instead of
returning nullopt — it resolves the node once and checks its type against the
accepted set.

### 24. An OoT regression gate that needs no Shipwright build

Shared torch code is now being changed for MM, so OoT needs a gate. Rather than
build Shipwright, `tools/oot_gate.sh` recovers the OoT manifest and config from
git history (they were deleted in a20b505), uses the OoT YAML trees already in the
working tree, and the ROMs in `roms/oot/`. Nothing recovered is committed.

pal_gc: 35386 matching, 0 mismatched. Every torch change since has been checked
against it.

### 25. Four MM conventions the ported converter got wrong, each found by a crash

Recorded because all four look correct when reading the OoT code:

- `Limb` carries its kind in `Type`; OoT used `Type` for the *skeleton* kind, so
  limbs emitted `skel_type` and the factory found no `limb_type`.
- MM has no `code/sys_matrix.xml` and no `gMtxClear`, but room DLists were given it
  as an external file unconditionally.
- MM scene files have no `_scene` suffix, so the "is this a room" test matched
  scenes too, giving each a duplicate segment 2 and an `external_files` entry
  pointing at itself.
- The text element is `TextMM`, so it never received `code_phys_start`.

### 26. Deferring beats emitting something plausible but wrong

`MM:PATH` (688 assets) has a working factory but needs `num_paths`, which OoT got
from a scene-command scan that does not exist for MM. Emitting paths without it
makes the factory follow a garbage pointer and abort. It sits in `DEFERRED_TYPES`
with the reason attached, rather than being emitted and quietly producing garbage.

Same reasoning for the 1929 failing limbs: the diff is a single `skinVtxCnt` field
that the reference fills on limbs that have no such field, most likely ZAPD
residue. Reproducing residue is guessable, and guessing wrong yields 1929
plausible-looking wrong assets, so it waits for the ordering analysis that would
confirm it.

### 27. The ZAPD non-determinism fix already existed upstream

The plan was to branch ZAPDTR/OTRExporter on the forks and fix the
non-determinism ourselves. Checking first showed 2ship's pins are 4 and 3 commits
behind their upstream `develop` branches, and one of those commits is exactly the
fix: ZAPDTR `be1c68a` "initialize some uninitialized things" (#37), which gives
`SkinAnimatedLimbData::totalVtxCount` a `= 0` default and does the same for
`RoomShapeImageMultiBgEntry::unk_00`/`id` and `SetMesh::data`.

So **no fork branches for ZAPDTR or OTRExporter were needed**. Only
`briaguya0/2ship2harkinian` branch `deterministic-extraction`, which bumps both
pins. Keeping our own fork of an already-fixed upstream would be divergence for
nothing.

Branched from `d35196ad7` — the commit the current reference was built from —
rather than from develop tip, so a rebuilt reference differs by these fixes and
nothing else and the re-measurement is attributable.

*Not done:* a blanket sweep adding initializers to every uninitialized POD member
in ZAPD. An audit found ~55 headers with them, but most are assigned during
parsing and are not bugs. Fixing what the diffs actually evidence, then
re-measuring against a clean reference, beats 200 speculative edits that would
mask the real ones.

### 28. Some room mismatches are ours, not ZAPD's

Failing rooms differ in two ways at once: the reference contains garbage (`0xB8`
where a zero belongs — ZAPD's, fixed by 27) *and* our output is one byte shorter,
which is torch writing one fewer field. Only the first is addressed by the
submodule bump. MM's room command set diverging from OoT's is still real work,
and the rebuilt reference is what will separate the two.

### 29. The determinism fix landed, and the numbers confirm the diagnosis exactly

Reference rebuilt from `a4a426c6f` (CI run 31719199796). Diffing the old manifest
against the new one: **2181 assets changed in the reference itself** — 1929 limbs,
251 rooms, 1 array. The 1929 is precisely the set of limbs that had been failing.

MM:LIMB went 1566/3495 → **3495/3495** with no torch change at all. Overall
45693 → **47622** passing, 3529 → 1600 failing.

Rooms did *not* improve (still 414 + 79). Both problems were real, as decision 28
said: ZAPD's uninitialized fields are now fixed, and what remains is ours.

`supplemental/ntsc_u.json` is byte-identical across the rebuild, which is the
expected result — it captures names, offsets, types and counts, and the fix changed
field *values*, not structure.

### 30. `game:` is declared in the config, not sniffed from the cartridge

MM and OoT diverge in enough places that shared code needs to tell them apart, and
torch had no notion of which Zelda 64 title a rom was — only a `gGameTitle` string
from the cartridge header.

Added `game:` to the rom config (`OOT` default, `MM`) rather than matching on that
title, for the same reason CMPDMA is opt-in (7, 21): an explicit declaration cannot
misfire on a rom nobody anticipated, and it keeps the OoT path untouched by
construction.

Shared code branches on `Companion::Instance->IsMajorasMask()` rather than being
forked, following the `kArrayTypes`/`kMtxTypes` precedent from decision 23. Every
MM divergence so far — pathways, `SetRoomBehavior`, room name padding, `0x19`,
the cutscene list — is a branch inside the existing OoT writer, and OoT stays at
35386/0 throughout.

### 31. Instrument rather than guess when a diagnosis stops being obvious

Paths were predicted to be one fix (the three bytes per pathway MM carries and OoT
treats as padding). That fixed 503 of 522. The remaining 19 were only visible once
the size deltas stopped dominating, and rather than theorise, a one-line log in the
alternate-header branch gave **exactly 19 truncations against exactly 19 failures**
— OoT exports only the first pathway of a shared list, MM exports all.

The same approach settled rooms. The plan had guessed `SetMesh`'s leading `data`
byte was the missing one; it was not, torch already wrote it. Walking a failing
room against OTRExporter's switch found `SetRoomBehavior` instead, where MM unpacks
`gameplayFlags2` into the five fields it encodes. That one diagnosis accounted for
all 414 room failures.

### 32. A category getting worse can be progress; say which it is

Fixing MM's cutscene naming took `MM:CUTSCENE` from 17 failures to 318, and extras
from 132 to 0. Nothing regressed: those cutscenes previously had no correct name,
so they counted as *extras* or as *not generated* rather than as mismatches. They
are now generated under the right name and therefore actually compared.

Worth recording because the headline number moved the wrong way while the work was
sound, and a scoreboard that only tracks "failures" would have read it as a
regression. Extras reaching zero is the same change seen from the other side: torch
no longer emits anything the reference does not have.

Supersedes the open question in decision 28 — the room half of that split is
resolved, and every remaining room-shaped failure is a scene.

### 33. Two self-inflicted debugging failures worth not repeating

The MM cutscene work cost far more than it should have, twice for reasons
that were mine rather than the code's.

**A stale binary read as a segfault.** Build and score were chained in one
command several times. One build ran with the wrong working directory and
silently did nothing, so `score.sh` kept measuring an older broken binary. The
same source ran clean once actually rebuilt. Compounding it, success was tested
with `grep … || echo "still failing"`, which reports on *grep* matching, not on
the run succeeding — so a passing run with unexpected output read as a failure.
The work was parked on a branch as unfixable on that basis, wrongly.

*Apply:* build and measure as separate steps, and check exit status rather than
grepping for a string.

**Enum values written from ordering rather than read.** Four cutscene command
constants were inferred from where they sat in the enum; three were wrong.
`CS_CMD_PLAYER_CUE` is 200, not 300, and carries 0x30-byte entries — reading it
as an 8-byte generic desynced the rom walk by 40 bytes each time. The runs of
impossible "command id 0, zero entries" in the parse were the middle of an actor
cue being read as a command header, and were visible for a long time before
being recognised as the symptom they were.

*Apply:* the same rule that has worked everywhere else here — read the value
from the source, do not infer it. `rom_info.py`, `CmpDma_GetFileInfo` and
`PathExporter.cpp` were all found that way; this was the one place it was
skipped, and it was the one place that went badly.

### 34. Deriving facts from names failed three times in one area; read the source instead

The display-list endgame turned up three separate bugs with one shape: a fact was
derived from a file *name* that MM does not encode the way OoT does.

- **External files.** `archives/icon_item_static.xml` holds
  `<File Name="icon_item_static_yar">`, so deriving the DMA name from the XML path
  silently dropped the reference and every display list pointing into that file
  failed to resolve. Read `File Name` from the referenced XML; the emitted yml path
  follows `OutName`, not the XML stem.
- **Segment number.** `generate_supplemental` used `"_scene" in dma_name` to pick
  segment 2 vs 3. MM scene files carry no `_scene` suffix, so every scene was
  scanned on the room segment.
- **Which files to scan at all.** The same name test skipped every object, so
  object display lists were never walked for matrices.

All three now read the XML, which states each outright. This is the same rule that
found the DMA offsets in `rom_info.py` and the pathway fields in
`PathExporter.cpp`, and the same rule that was skipped when the cutscene command
ids were inferred from enum ordering (33).

*Corollary:* a matrix is named after the display list that reaches it, so roots
have to carry their **declared** symbol. Synthesizing `<file>DL_<offset>` for
XML-declared lists produced two extras rather than the two the reference has.

### 35. Segment auto-adds must respect the file's own segment

Torch treats a segment as an alias when a **lower-numbered** segment maps to the
same file offset (`IsAliasSegment`, `OoTDListHelpers.cpp`), and emits `pointer + 1`
rather than resolving. The converter auto-added segments 8–13 pointing at the file
itself — an OoT convention for eye and mouth textures, harmless there because OoT
objects sit on segment 6 with all of 8–13 above it.

MM puts 24 mask objects on segment 10, so the auto-added 8 and 9 sat *underneath*
the primary and made every vertex reference in those files look like an alias.
Only segments above the file's own are added now.

Worth recording for how long it hid: the answer was the **first branch** of
`ExportVtx`, and its log line is `SPDLOG_INFO`, not `WARN`. The earlier
investigation started in the middle of the function and worked outward, so that
branch was never read, and its silence was taken as evidence the not-found branch
was to blame. Read a function from the top before theorising about its middle.

### 36. Virtual addresses were being resolved twice

`ExportVtx` looked the vertex up with `GetNodeByAddr(ptr)` where `ptr` had already
been through `PatchVirtualAddr`. `PatchVirtualAddr` *is* `ResolveVirtualAddr`, and
`GetNodeByAddr` resolves again, so any file with a `virtual:` mapping had its vram
base subtracted twice — turning a correct address into a miss that fell through to
the unresolved-virtual-segment path. Look up the unpatched address.

*Rejected first:* that `BaseAddress` corresponds to `RangeStart` rather than to
file offset 0, so the virtual base needed `RangeStart` subtracted. Both attributes
are present on every file that has either, which made it plausible. It broke
overlays on the first run and was reverted — `BaseAddress` is the vram address of
file offset 0 and `RangeStart` merely bounds what to extract.

Instrumenting settled it in one line: `w1=0x801BA550` resolved to `ptr=0x80114A90`,
exactly where the array is registered, immediately followed by `direct lookup
miss`. That is rule 3 of the endgame plan working as intended, after rule 3 was
written *because* the previous stretch ignored it.

### 37. A duplicate asset is declared as a duplicate, not as a second asset

ZAPD emits `object_horse_link_child`'s skin-limb display list twice: as
`object_horse_link_child_DL_00D500` from the XML, and again under the limb's own
name from the skin-limb exporter. Both archive entries are byte-identical, and
the copy's self-hash — the CRC64 a display list writes of its own path — names
the *original*. The limb that references offset 0xD500 also resolves to the
original.

The supplemental injector had been dropping any entry landing on an
already-declared offset, on the theory that it was an alias Torch regenerates.
That rule is right for the 7 rom-scan matrix guesses it drops and wrong for this
one, so entries read out of the reference archive — names the reference provably
contains — are now let through.

Declaring it plainly gets both halves wrong: it hashes itself under its own name,
and being registered second it takes over the address map and steals the limb's
reference. So Torch grew `duplicate_of: <path>`: the node is skipped when the
address map is populated, and the display list exporter hashes the named path
instead of its own. Both halves, one key.

*Diagnosis note:* the differing bytes looked like an unresolved `G_VTX` hash and
were nearly chased as one. They are the marker at the top of every exported
display list — `G_MARKER`, `0xBEEFBEEF`, then `CRC64(own path)`. Reading the word
as big-endian rather than little-endian is what made it look like an opcode; the
writer at `OoTDListHelpers.cpp:690` says plainly what it is.

### 38. Non-scalar array elements: fix the exporter, don't guess the memory

`ArrayExporter.cpp` handles Vertex and Vector explicitly and casts everything
else to `ZScalar` to write `scal->scalarType`. For MM's three Pointer and
CollisionPoly arrays that cast is invalid, so the reference carries four bytes of
stale memory per element — not reproducible, and nothing to match against.

Same treatment as the ZLimb `totalVtxCount` residue: fix it at the source and
rebuild the reference. `briaguya0/OTRExporter` branch `deterministic-arrays`
writes `ZSCALAR_NONE` for element kinds with no exporter — same stream layout,
one type word and no payload, but a defined value — and
`briaguya0/2ship2harkinian` `deterministic-extraction` points the submodule at
it. That branch needs a CI build to produce a new reference.

Torch builds the arrays now regardless, since everything but those words is
already known: `SohArrayType` mirrors `ZResourceType`, so CollisionPoly is 28 and
Pointer 29, which is what the reference's own header words say. Against today's
reference the three match in length, type and count and differ only where the fix
zeroes.
