# Plan for the remaining 1600 failures

Standing at the time of writing: **47622 pass, 1600 fail, 132 extra** of 50496.
Every figure below is measured, and each diagnosis names the source line it came
from. See `mm-status.md` for the scoreboard and `decisions.md` for how we got here.

## The shape of what's left

| Reference type | Failing | Size relationship | Cause |
|----------------|--------:|-------------------|-------|
| OROM (rooms) | 595 | 414 are **ours −1 byte**, rest vary | MM room commands torch does not implement |
| OPTH (paths) | 522 | ours short by an exact **multiple of 3** | MM writes 3 bytes per pathway torch omits |
| ODLT (dlists) | 438 | 295 same size, 143 **ours −8** | two distinct issues, see below |
| OSMP (samples) | 20 | — | audio; no MM factory |
| OCVT (cutscenes) | 17 | — | MM cutscene commands |
| OCOL (collision) | 4 | — | undiagnosed |
| OTXM (MM text) | 2 | — | MM message format |
| OARR / OSKL | 1 / 1 | — | undiagnosed |
| **EXTRA** | 132 | all `CutsceneData` | we generate cutscenes the reference does not |

Rooms + paths + scenes + cutscenes + extras are **~1270 of the 1732 problems and
they are one body of work**: MM's scene/room command set. That is the whole first
phase.

---

## Phase A — MM scene and room commands

The single highest-value change. Torch has OoT's command set; MM's differs at both
ends.

### A1. The commands OoT does not have

From `ZAPDTR/ZAPD/ZRoom/ZRoomCommand.h`:

```
SetWorldMapVisited      = 0x19   // OoT uses 0x19 for SetCameraSettings
SetAnimatedMaterialList = 0x1A
SetActorCutsceneList    = 0x1B
SetMinimapList          = 0x1C
SetMinimapChests        = 0x1E
SetCutscenesMM          = 0x1F   // not a real opcode; ZAPD invents it for OTRs
```

`0x19` is a **reuse, not an addition** — writing OoT's `SetCameraSettings` there
produces silent garbage rather than an error, so this needs care.

### A2. Paths — 522 assets, fully diagnosed

`OTRExporter/PathExporter.cpp`:

```cpp
writer->Write((uint32_t)path->pathways[k].points.size());
if (Globals::Instance->game == ZGame::MM_RETAIL) {
    writer->Write(path->pathways[k].unk1);   // int8
    writer->Write(path->pathways[k].unk2);   // int16
}
```

Three extra bytes per pathway, which is exactly why every path is short by a
multiple of 3 (a 24-pathway path is −72, a 9-pathway one is −27, and so on).

Torch's `OoTPathFactory::parse` reads the 8-byte entry as
`numPoints(u8) + 3 bytes padding + pointsAddr(u32)`. In MM those three "padding"
bytes are `unk1` and `unk2`, and `ZPath.cpp:123-126` confirms they are read
straight from ROM, so they are deterministic and simply need carrying through.

Also needs `num_paths`, which is why paths are currently in `DEFERRED_TYPES` — the
count comes from the scene's path command, so it falls out of A1 for free.

### A3. Rooms

414 of 595 are short by exactly one byte, at a position that varies with command
order, so it is per-command rather than one global field. Torch already writes
`SetMesh`'s leading `data` byte (`OoTSceneCommandWriter.cpp:341-345`), so it is not
that one — identify the specific commands by walking a failing room against
`RoomExporter.cpp`'s switch.

### A4. Cutscenes — 17 failing and all 132 extras

We emit 132 `CutsceneData` assets the reference does not, 72 of them under `Set_`
alternate-header names. The reference does contain `Set_` assets (2162 of them), so
this is not a blanket naming rule — our discovery is finding cutscenes at offsets
ZAPD does not emit. `SetCutscenesMM = 0x1F` being a synthetic opcode is the likely
reason and should be read first.

**Expected yield: ~1270 assets, taking the total to roughly 98%.**

---

## Phase B — Display lists (438)

Two unrelated problems sharing a type:

**295 same-size, differing commands.** Example, `gElegyShellDekuDL`, three commands
differ identically:

```
ours 000000de 1100000c
ref  0000003d 0200000c
```

`0xDE` is `G_DL` in F3DEX2; the reference emits `0x3D`. Both words differ, so this
is a whole-command substitution, not a pointer that failed to resolve.

**143 short by exactly 8**, i.e. one missing command. First divergence in
`sDebugDisplay1DL`:

```
ours 00000032 00000000
ref  40000232 00000000
```

Worth checking whether these are the same root cause before splitting the work.

---

## Phase C — The tail (28)

`OSMP` 20 (audio samples — needs the MM audio factories, which do not exist),
`OCOL` 4, `OTXM` 2, `OARR` 1, `OSKL` 1. Small enough to leave until A and B land,
since some may resolve as side effects.

---

## Not in scope here

Still deferred, unchanged, and tracked in `mm-status.md`:

- Arrays of `Pointer`/`Scalar`/`CollisionPoly` element kinds (4 in XML, 2 in the
  reference) — the array factory builds only VTX and Vec3s.
- Types with no Torch factory: `OTAN` texture animation (293 in the reference),
  `OKFA`/`OKFS` keyframe animation and skeleton, and the audio set. These are
  absent from the generated archive entirely rather than wrong, so they show up as
  "not generated", not as failures.

## Order and rationale

1. **A2 paths first.** Fully diagnosed, self-contained, 522 assets, and it
   validates the MM-vs-OoT divergence pattern on the smallest possible surface.
2. **A1 + A3 + A4**, which are one change to the scene/room command writer.
3. **B**, after A, since some DList failures sit inside rooms and may move.
4. **C** last.

Run `./tools/oot_gate.sh pal_gc` after every torch change — all of this touches
`OoTSceneCommandWriter` and `OoTPathFactory`, which OoT depends on. The shared code
should learn MM's variants behind a game check rather than being forked, following
the `kArrayTypes`/`kMtxTypes` precedent in `OoTDListHelpers.cpp`.
