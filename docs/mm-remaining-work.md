# Plan for the remaining 1600 failures

Standing: **48892 pass, 780 fail, 0 extra** of 50496. Phase A is done except
cutscenes: paths 688/688, rooms 414/414, scenes 168/181, and nothing is emitted
that the reference does not have.
Every figure below is measured, and each diagnosis names the source line it came
from. See `mm-status.md` for the scoreboard and `decisions.md` for how we got here.

## The shape of what's left

| Reference type | Failing | Size relationship | Cause |
|----------------|--------:|-------------------|-------|
| OROM (rooms) | 595 | 414 are **ours −1 byte**, rest vary | MM room commands torch does not implement |
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

### A2. Paths — DONE (688/688)

Implemented in torch `aaa70f5`. Two changes, the second only visible after the
first:

1. MM carries `unk1`/`unk2` per pathway where OoT has padding — the three bytes
   that made every failure short by a multiple of 3.
2. OoT's alternate headers export only the first pathway of a shared list; MM
   exports all. Instrumenting showed exactly 19 truncations against exactly 19
   remaining failures.

Both gated on a new `game:` key in the rom config (`OOT` default, `MM`), declared
rather than sniffed. That key is now available for phases A1/A3/A4.

`MM:PATH` stays in `DEFERRED_TYPES`, and that is now the correct permanent state
rather than a workaround: all 688 paths come from the scene command writer as
companion files, so declaring them from supplemental would be redundant.

<details><summary>Original diagnosis</summary>

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

</details>

### A1/A3 — DONE (rooms 414/414, scenes 168/181)

Implemented in torch `d1f22c6` and `7405193`. Five divergences, none of which was
the one the plan guessed at:

- **`SetRoomBehavior`** — OoT writes `gameplayFlags2` whole; MM unpacks it into the
  five fields it encodes, six bytes against five. This was the entire "ours is one
  byte short" on all 414 rooms.
- **Room names** — MM zero-pads the index, `_room_00` not `_room_0`.
- **`0x19`** — MM writes *no body*; torch was writing OoT's five bytes.
- **`0x1A`/`0x1B`/`0x1C`/`0x1E`** — four commands OoT lacks. `SetMinimapList`
  carries no count and takes one entry per room, so `SetRoomList` now records the
  room count in the write context.
- **`SetCutscenes`** — MM carries a list where OoT carries one pointer, and ZAPD
  rewrites the opcode to `0x1F`. Entries name their cutscene off the scene's base
  name, and a declared cutscene keeps its declared name.

13 scenes remain, undiagnosed.

### A4. Cutscene contents — 318 failing, now the largest category

The naming half is fixed and extras are at zero, so every cutscene the reference
has is now generated under the right name and compared. Their *contents* are still
serialized with OoT's command set.

The count rose from 17 as a direct result: those cutscenes previously had no
correct name, so they counted as extras or as not-generated rather than as
mismatches. This is progress made visible, not a regression.

MM's command set is in `ZAPD/OtherStructs/CutsceneMM_Commands.h`, separate from
`CutsceneOoT_Commands.h`. Torch's `CutsceneSerializer` implements OoT's.

**Remaining phase A: cutscene contents (318) and 13 undiagnosed scenes.**

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

1. ~~**A2 paths.**~~ Done — and it established the `game:` config key and the
   branch-don't-fork pattern the rest of phase A should follow.
2. ~~**A1 + A3.**~~ Done. **A4** (cutscene contents) is what remains of phase A.
3. **B**, after A, since some DList failures sit inside rooms and may move.
4. **C** last.

Run `./tools/oot_gate.sh pal_gc` after every torch change — all of this touches
`OoTSceneCommandWriter` and `OoTPathFactory`, which OoT depends on. The shared code
should learn MM's variants behind a game check rather than being forked, following
the `kArrayTypes`/`kMtxTypes` precedent in `OoTDListHelpers.cpp`.
