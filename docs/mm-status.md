# MM extraction status

Measured with `./tools/score.sh` against `manifests/ntsc_u.json` (50496 assets from
the OTRExporter reference for NTSC-U 1.0).

```
generated 49354 of 50496 reference assets
  PASS  50455      (99.9%)
  FAIL     24
  EXTRA     0
  not generated  20
```

Reference rebuilt from `briaguya0/2ship2harkinian` `deterministic-extraction`
(`a4a426c6f`), which bumps ZAPDTR past `be1c68a` (#37). That changed 2181 assets in
the reference itself — 1929 limbs, 251 rooms, 1 array — and the 1929 is exactly the
set of limbs that had been unmatchable.

OoT is unaffected throughout: `./tools/oot_gate.sh pal_gc` → 35386 matching, 0
mismatched, 0 not generated, 0 extra.

## Passing outright

These types come out byte-identical using the **Ocarina of Time factories,
unmodified**. Majora's Mask runs on the same engine and shares the formats, which
is the evidence for moving them to a shared `zelda64/` namespace (plan phase 2)
rather than writing MM copies.

| Type | Passing |
|------|--------:|
| TEXTURE | 13542 / 13542 |
| MM:ANIMATION | 1755 / 1755 |
| MM:PLAYER_ANIMATION | 695 / 695 |
| MM:PLAYER_ANIMATION_DATA | 695 / 695 |
| MM:MTX | 11 / 11 |
| MM:CURVE_ANIMATION | 3 / 3 |
| MM:AUDIO | 1 / 1 |
| GFX | 13023 / 13461 |
| MM:ARRAY | 10476 / 10477 |
| MM:SKELETON | 213 / 214 |
| MM:LIMB | 3495 / 3495 |
| MM:PATH | 688 / 688 |
| MM:TEXTURE_ANIMATION | 293 / 293 |
| MM:CUTSCENE | 421 / 421 |
| MM:ROOM | 582 / 595 |
| MM:COLLISION | 286 / 290 |
| BLOB | 234 |

## Remaining failures

| Type | Failing | Diagnosis |
|------|--------:|-----------|
| GFX | 438 | not yet diagnosed |
| MM:ROOM | 13 | scenes only; all 414 rooms pass |
| MM:SCENE | 102 | MM's scene command set diverges from OoT's; see paths below |
| MM:CUTSCENE | 318 | MM cutscene command set differs from OoT's; they are correctly named now and therefore compared, where before they were extras or missing |
| MM:COLLISION | 4 | not yet diagnosed |
| MM:TEXT | 2 | MM's message format differs from OoT's |
| MM:ARRAY | 1 | not yet diagnosed |
| MM:SKELETON | 1 | not yet diagnosed |

### MM:LIMB — resolved

`SkinAnimatedLimbData::totalVtxCount` had no initializer, and `SkeletonLimbExporter`
writes it for every limb regardless of type, so a Standard limb — which never
populates `segmentStruct` — emitted whatever was in memory. ZAPDTR `be1c68a` (#37)
gives it `= 0`.

The old reference's Standard limbs carried 0 on 1479 of 3495 (those matched) and
varying values in runs on the rest. With the rebuilt reference **MM:LIMB is
3495/3495**. Nothing in torch changed — the reference was non-deterministic, and no
amount of matching would have fixed it.

The whole diff is a single `uint16` at body offset 6, `skinVtxCnt`. Torch writes 0;
the reference writes a nonzero value on limbs whose type does not use the field.

## Deferred, with reasons

- **MM:PATH (688 assets).** Declaring them from supplemental aborts extraction: the
  factory needs `num_paths`, which OoT recovered by scanning scene commands, and
  without it follows a garbage pointer. They are in `DEFERRED_TYPES` in
  `generate_supplemental.py`.

  Deferring does **not** remove them from the output — the scene factory discovers
  paths from scene commands on its own, and 522 of those come out wrong. So paths
  are not a supplemental problem so much as a scene-command problem, and they land
  with the MM:ROOM / MM:SCENE work rather than beside it.
- **Arrays of unsupported element kinds (4 in XML, 2 in the reference).**
  `Pointer/Gfx`, `Scalar/x8`, `CollisionPoly` — the array factory builds only VTX
  and Vec3s. Skipped and tallied at both ends.
- **Types with no Torch factory at all**, present in the reference and listed in
  `UNSUPPORTED_RESOURCE_TYPES`: `OTAN` texture animation (293), `OKFA`/`OKFS`
  keyframe animation and skeleton (6 each), `OTXM` MM text (2), and the audio set
  `OSMP`/`OSEQ`/`OSFT`/`OAUD`.

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
