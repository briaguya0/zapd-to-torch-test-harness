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
