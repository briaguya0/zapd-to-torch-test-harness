# MM extraction status

Measured with `./tools/score.sh` against `manifests/ntsc_u.json` (50496 assets from
the OTRExporter reference for NTSC-U 1.0).

```
generated 50496 of 50496 reference assets
  PASS  50496
  FAIL      0
  EXTRA     0
```

**Complete.** Every asset in the reference archive is reproduced byte for byte.

OoT is unaffected throughout: `./tools/oot_gate.sh pal_gc` → 35386 matching, 0
mismatched, 0 not generated, 0 extra.

## The reference is not stock

Built from `briaguya0/2ship2harkinian` `deterministic-extraction` (`95a0b33eb`).
Two ZAPD fixes are load-bearing, because without them the reference is not
reproducible at all — it contains uninitialized memory:

| Fix | What it was | Affected |
|-----|-------------|---------:|
| ZAPDTR `be1c68a` (#37) | `ZLimb`'s `SkinAnimatedLimbData::totalVtxCount` had no initializer, and `SkeletonLimbExporter` writes it for every limb regardless of type | 1929 limbs |
| `briaguya0/OTRExporter` `deterministic-arrays` | `ZArray` sends any non-Vertex/Vector element through a branch that casts it to `ZScalar` and writes the uninitialized `scalarType` | 3 arrays |

Both were found the same way: our output was stable and the reference's was not.
No amount of matching fixes that — see [decisions.md](decisions.md) 38.

## Final scoreboard

| Type | Passing |
|------|--------:|
| TEXTURE | 13542 |
| GFX | 13462 |
| MM:ARRAY | 10481 |
| *(undeclared type)* | 3690 |
| MM:LIMB | 3495 |
| MM:ANIMATION | 1755 |
| BLOB | 1029 |
| MM:PLAYER_ANIMATION_DATA | 695 |
| MM:PLAYER_ANIMATION | 695 |
| MM:ROOM | 414 |
| MM:CUTSCENE | 301 |
| MM:COLLISION | 290 |
| MM:SKELETON | 214 |
| MM:TEXTURE_ANIMATION | 191 |
| MM:MTX | 122 |
| MM:SCENE | 102 |
| MM:KEYFRAME_ANIMATION | 6 |
| MM:KEYFRAME_SKELETON | 6 |
| MM:CURVE_ANIMATION | 3 |
| MM:TEXT | 2 |
| MM:AUDIO | 1 |
| **Total** | **50496** |

`score.sh` attributes each asset to the type that declared it. The 3690 with no
declared type are assets Torch creates during extraction rather than from a YAML
declaration — scene `Set_` alternate headers and the paths the scene factory
discovers from scene commands, mostly. They are compared like everything else.

## What needed what

Nothing here is a separate MM factory tree. MM runs the same engine and shares
most formats with OoT, which is the argument for a shared `zelda64/` namespace
rather than MM copies.

**Passed on OoT's factories with no changes:** TEXTURE, MM:ANIMATION,
MM:PLAYER_ANIMATION and its data, MM:CURVE_ANIMATION, MM:AUDIO.

**Needed MM behaviour inside the shared factory:** scenes and rooms (MM's command
set diverges — `SetRoomBehavior` field packing, `_room_00` padding, the reused
`0x19` opcode, commands `0x1A`–`0x1F`), cutscenes (a different command set and
different entry sizes), collision (surface types always emitted), skeletons
(header limb count vs table length), display lists, and arrays (Scalar,
CollisionPoly and Pointer element kinds).

**Needed a new factory:** MM:TEXTURE_ANIMATION (`OTAN`), MM:KEYFRAME_SKELETON and
MM:KEYFRAME_ANIMATION (`OKFS`/`OKFA`), MM:TEXT (`OTXM`).

## Two quirks reproduced on purpose

Matching means reproducing what ZAPD does, including where it is arguably wrong:

- **gSunDL's vertices disagree with the ROM by design.** ZAPD rewrites the `t`
  coordinate of every vertex that display list loads —
  `vtx.t = (((vtx.t >> 5) - 1) / 2) << 5` — to compensate for sun textures it
  cannot extract whole. See [decisions.md](decisions.md) 39.
- **A display list is exported twice under two names.**
  `object_horse_link_child`'s skin-limb DL ships as a byte-identical duplicate
  whose self-hash names the *original*. Torch's `duplicate_of` key says so
  explicitly. See [decisions.md](decisions.md) 37.

## Reproducing

```sh
python3 tools/extract_dma.py                                    # dma/ntsc_u.json
python3 tools/make_filelist.py dma/ntsc_u.json assets/yml/ntsc_u.filelist.yml
python3 tools/generate_supplemental.py \
    o2r/ntsc_u_d6133a.o2r roms/mm/ntsc_u_d6133a.z64 \
    dma/ntsc_u.json supplemental/ntsc_u.json
./tools/score.sh                    # full run
./tools/score.sh Texture            # one type
./tools/oot_gate.sh pal_gc          # OoT regression
```
