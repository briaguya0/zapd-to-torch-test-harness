# Finishing MM extraction: the last 93 assets

Supersedes the earlier phase A/B/C plan, whose phases are all complete. That
history is in `decisions.md` and the commit messages.

## Context

MM extraction is at **50403 / 50496 byte-identical (99.8%)**, with OoT held at
35386/0 throughout. What remains is **74 mismatched + 19 never generated = 93
assets, 0.18%**.

This plan exists because the last stretch went badly. Everything up to display
lists was found by reading the source that already knew the answer —
`rom_info.py` for the DMA offsets, `CmpDma_GetFileInfo` for the archive
container, `PathExporter.cpp` for the pathway fields, `ZCutscene::GetCommandMM`
for the cutscene shapes. The display-list work abandoned that and reverted to
theorising from partial evidence, which produced two dead ends:

- A **stale binary read as a segfault.** Build and measure were chained in one
  command, so a no-op build looked identical to a good one, and success was
  tested with `grep … || echo "still failing"` — which reports on grep matching,
  not on the run succeeding. Working code was parked on a branch as unfixable.
- **Enum values inferred from ordering** rather than read. Three of four cutscene
  constants were wrong; `CS_CMD_PLAYER_CUE` is 200, not 300. The symptom — runs
  of impossible "command id 0, zero entries" — was on screen a long time before
  being recognised as a desync.

It then ended mid-air on a contradiction that was stopped rather than resolved.

## Process rules for this phase

Not general advice; each is a specific lapse from the last stretch.

1. **Build and measure as separate commands.** Never chain them. Check exit
   status, never `grep … || echo "failed"`.
2. **Read values, don't infer them.** Every constant comes from ZAPD/OTRExporter
   source, quoted in the commit message.
3. **Instrument before theorising.** When an observation contradicts the code,
   add a log and run it. A long stretch of the last session went to reasoning
   about a branch a single `SPDLOG` would have settled.
4. **`./tools/oot_gate.sh pal_gc` after every torch change.** Non-negotiable —
   all of this lives inside shared OoT code.
5. One area per commit, with before/after counts.

## The remaining work

| Area | Count | State |
|------|------:|-------|
| ODLT display lists | 33 | contradiction below — resolve first |
| OSMP audio samples | 20 | undiagnosed |
| OROM scenes | 13 | undiagnosed |
| OKFA/OKFS keyframe | 12 | no factory; not generated |
| OARR arrays | 4+1 | unsupported element kinds |
| OCOL collision | 4 | undiagnosed |
| OMTX matrices | 2 | in objects; the ROM scan only walks rooms/scenes |
| OTXM MM text | 2 | MM message format |
| ODLT / OSKL | 1+1 | undiagnosed |

---

## Step 1 — Resolve the display-list contradiction (33)

25 `object_mask_*` files with one display list each, 2 in `object_dog`, 6 in
`code/`. All are an unresolved `G_VTX`: torch emits the raw opcode with
`(ptr & 0x0FFFFFFF) + 1` where the reference emits `G_VTX_OTR_HASH` plus the
vertex's CRC64.

Three observations that cannot all be true:

- The vertex **is** declared. For `object_mask_bakuretu_DL_000440` the target is
  `object_mask_bakuretuVtx_000250` — generated, `MM:ARRAY`, `offset: 0x000250`,
  `array_type: VTX`, segment 10, the same segment and file as the display list.
- The output is the signature of `ExportVtx`'s not-found branch in
  `src/factories/oot/OoTDListHelpers.cpp` (`w1 = (w1 & 0x0FFFFFFF) + 1`).
- That branch's `SPDLOG_WARN("VTX export: NOT FOUND vtx …")` **never appears** in
  a `logging: WARN` run, while 10467 successful `Found vtx` lines do — and the
  string is in the binary, which is current.

**Do not change code until this is explained.** Add a temporary `SPDLOG_CRITICAL`
at the top of `ExportVtx` and in each of its four exits, printing `ptr`,
`Companion::Instance->GetCurrentFile()` and the branch taken, then pull out the
lines for `object_mask_bakuretu`. One run answers it.

Leading hypothesis, from `Companion::GetNodeByAddr` (`Companion.cpp:2244`): the
lookup is scoped to `gCurrentFile` **and is an exact address match** — range
containment happens only in the overlap/`SearchVtx` path. If a display list
references an address *inside* the array rather than its first byte, the direct
lookup misses, and whether `SearchVtx` catches it depends on its own guard
(`GetGBIMinorVersion() != GBIMinorVersion::OoT` returns early). Worth checking
what MM's `gbi:` resolves that to — `assets/yml/config.yml` says `F3DEX2_OoT`,
inherited from OoT and never independently verified.

**Technique that works here: the reference's hash names its own target.** Rebuild
torch's CRC64 table from `lib/strhash64/StrHash64.cpp`, hash every manifest key,
and look up the two words the reference writes after the command. That identified
`icon_item_static_yar/gABtnSymbolTex` immediately, which is how the external-file
bug below was found.

## Step 2 — Scenes (13) and collision (4)

Both undiagnosed, both small, and scenes have the most prior context. Samples:
`scenes/nonmq/Z2_SINKAI/Z2_SINKAI`, `scenes/nonmq/Z2_OKUJOU/Z2_OKUJOUSet_012CC0`,
`objects/object_iknv_obj/object_iknv_obj_Colheader_012788`.

Method: byte-diff against the reference, find the first differing command, and
compare that command's writer in `RoomExporter.cpp` / `CollisionExporter.cpp`
against `OoTSceneCommandWriter.cpp` / `OoTCollisionFactory.cpp`. Exactly how
`SetRoomBehavior`, the room-name padding and the `0x19` reuse were found — the
divergence is a specific field and the exporter states it.

## Step 3 — The two stragglers already understood

- **2 OMTX in `object_dog`.** `extract_from_rom` in
  `tools/generate_supplemental.py` iterates rooms and scenes only, so object
  display lists are never walked for `G_MTX`. The walk itself already exists;
  extending it to objects is mechanical.
- **4+1 OARR.** Arrays of `Pointer`/`Scalar`/`CollisionPoly` element kinds, which
  `OoTArrayFactory` cannot build (it does VTX and Vec3s). Three small element
  writers; `SohArrayType`/`SohScalarType` in `OoTArrayFactory.h` already name the
  values.

## Step 4 — New factories, largest first

- **OSMP audio samples (20).** `audio/samples/sample_N_<addr>_META`. MM's audio
  differs from OoT's; read `AudioExporter.cpp` and scope it before committing.
- **OKFA/OKFS keyframe animation and skeleton (12).** No factory at all.
  `CKeyFrameExporter.cpp` and `ZCkeyFrameAnim.h` are the spec. Self-contained and
  MM-only, so zero OoT risk — the same shape as the texture-animation work, which
  landed 293/293 first try.
- **OTXM MM text (2).** Lowest value; do last.

## Already fixed in this area

**External files resolved by their declared name.** MM's archive XMLs are not
named after the file they contain: `archives/icon_item_static.xml` holds
`<File Name="icon_item_static_yar">`. An `ExternalFile` reference names the *XML*,
so deriving the DMA name from the path silently dropped the reference and every
display list pointing into that file failed to resolve. Reading `File Name` out
of the referenced XML fixed all 8 `icon_item_vtx_static` failures; the emitted yml
path has to follow `OutName`, not the XML stem.

**portVersion.** `score.sh` never passed `-u`, so the file was absent entirely. MM
stamps 5.0.0, matching 2ship's CMake project version; the reference reads
`01 0005 0000 0000`, the leading byte coming from `PORT_VERSION_ENDIANNESS=ON`.

## Verification

```sh
./tools/score.sh                # 50403 pass / 74 fail / 0 extra today
./tools/oot_gate.sh pal_gc      # 35386 matching, 0 mismatched
```

Separate commands, and read the exit status. `score.sh` attributes failures to the
declaring asset type, so a run says which factory is wrong rather than only how
many assets are.

Done is `0 failed, 0 extra, 0 not generated`. If an area costs more than it is
worth — MM audio is the likely candidate — say so and leave it documented here
rather than half-built.

## Not in scope

Adding GC US as a second target. That is the payoff for the name-based segment
work and should follow completion, not interleave with it.

---

## The last few

Standing: **50496 / 50496 — the archive is byte-identical to the reference.**
Every entry below is history now; it is kept for the reasoning, not as a to-do
list.

### Pointer and CollisionPoly arrays — fixed, and the reference rebuilt

`ArrayExporter.cpp` handled Vertex and Vector arrays explicitly and sent
everything else through an `else` branch that cast the element to `ZScalar` and
wrote `scal->scalarType`. For a Pointer or CollisionPoly element that member is
uninitialized, so the current reference contains 4 bytes of stale memory per
element and no value at all:

```
sTurtleGreatBayTempleColPolygons   19 elements x 4 bytes: 7b09e07a 23b40967 1307...
object_hanareyama_obj_DLArray_004638  54 x 4:             e8a2641b 48765e1b d849...
```

None of those are valid `ZScalarType` values. Same class as the limb
`totalVtxCount` residue ZAPDTR #37 fixed, but with no upstream fix yet, so:

- `briaguya0/OTRExporter` branch **`deterministic-arrays`** writes
  `ZSCALAR_NONE` for element kinds with no exporter — same stream layout, defined
  value.
- `briaguya0/2ship2harkinian` branch **`deterministic-extraction`** (`95a0b33eb`)
  points the submodule at it, so a CI build of that commit produces a reference
  with zeros there.

Torch builds these arrays (`CollisionPoly` = 28, `Pointer` = 29, mirroring
`ZResourceType`). The reference was rebuilt from that branch and **all three now
match**: `sTurtleGreatBayTempleColPolygons`,
`sTurtleGreatBayTempleColPolygons2`, `object_hanareyama_obj_DLArray_004638`.

The rebuild changed those three assets and *nothing else* — 3 hashes out of
50496, no additions, no removals — which is as clean a confirmation as the fix
could have asked for.

### `gameplay_keepVtx_07ACF8` — fixed

Two of twelve vertices differed in `t`: ours 992 and 512, the reference 480 and
224. Ours matched the rom exactly, and the reference's values appear nowhere in
any of the 1535 decompressed files — so ZAPD computed them.

It does. `ZDisplayList.cpp`, `GfxdCallback_Vtx`:

```cpp
if (self->GetName() == "gSunDL")
    vtx.t = (((vtx.t >> 5) - 1) / 2) << 5;
```

31 texels becomes 15, 16 becomes 7. `gameplay_keep.xml` states the reason above
`gSunSunsetTex`: the sun textures "should be 64x64, but they get broken into
pieces in gSunDL, and ZAPD cannot currently handle that."

The rule is the display list's *name*, so the harness applies the same rule —
walk the list named gSunDL, mark the vertex arrays it loads with `sun_tc` — and
Torch reproduces the arithmetic verbatim.

Two earlier searches had concluded the data "is not in the rom", and both were
wrong in ways worth recording:

- The first read the o2r blobs as big-endian when Torch writes little-endian, so
  every value compared was byte-swapped. It made ours look wrong against the rom
  when ours was exactly right.
- The second searched only files with `phys_end > phys_start`. In dmadata an
  uncompressed file has `phys_end == 0`, so that test skipped most of the rom.

The conclusion happened to survive both bugs, but it was not evidence.

### `object_horse_link_child_Skinlimb_00A138SkinLimbDL_00D500` — fixed

ZAPD emits this display list twice: once from the XML as
`object_horse_link_child_DL_00D500`, and again from the skin-limb exporter under
the limb's name. The two archive entries are byte-identical *including the
self-hash*, which names the original — and the limb that points at offset 0xD500
resolves to the original, not the copy.

The supplemental injector had been dropping it as an alias. Declaring it plainly
gets both halves wrong: it would hash itself under its own name, and being
registered second it would take over the address map and steal the limb's
reference. `duplicate_of: <path>` on the node says both — skip address
registration, hash the named path.

### MM text — done

`MM:TEXT` had been registered to `OoTTextFactory`, so it wrote OoT's format:
86637 bytes against the reference's 448796. MM's format differs throughout —
message offset at table entry +4 with the segment in the top byte, an 11-byte
per-message header, terminator 0xBF, and its own set of argument-taking control
codes. `staff_message_data_static` is a third format again, selected by file
name exactly as ZAPD selects it.

Spec: `ZAPDTR/ZAPD/ZTextMM.cpp` for the layout and control codes,
`OTRExporter/TextMMExporter.cpp` for the field order. Landed byte-identical on
the first run, which is what reading the source rather than inferring the format
buys.
