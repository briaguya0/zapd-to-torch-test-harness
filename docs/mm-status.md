# MM extraction status

Measured with `./tools/score.sh` against `manifests/ntsc_u.json` (50496 assets from
the OTRExporter reference for NTSC-U 1.0).

```
generated 49354 of 50496 reference assets
  PASS  45693      (90.5%)
  FAIL   3529
  EXTRA   132
```

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
| MM:COLLISION | 286 / 290 |
| BLOB | 234 |

## Remaining failures

| Type | Failing | Diagnosis |
|------|--------:|-----------|
| MM:LIMB | 1929 | see below |
| *(untyped)* | 621 | supplemental-only entries the scorer cannot attribute; needs the scorer to read supplemental too, not a real category |
| GFX | 438 | not yet diagnosed |
| MM:ROOM | 414 | not yet diagnosed |
| MM:SCENE | 102 | not yet diagnosed |
| MM:CUTSCENE | 17 | MM's cutscene command set diverges from OoT's |
| MM:COLLISION | 4 | not yet diagnosed |
| MM:TEXT | 2 | MM's message format differs from OoT's |
| MM:ARRAY | 1 | not yet diagnosed |
| MM:SKELETON | 1 | not yet diagnosed |
| EXTRA | 132 | generated but absent from the reference |

### MM:LIMB — `skinVtxCnt` on limbs that should not have one

The whole diff is a single `uint16` at body offset 6, `skinVtxCnt`. Torch writes 0;
the reference writes a nonzero value on limbs whose type does not use the field.

Distribution across Standard limbs in the reference:

```
0x0000  x1479     <- these are the ones that pass
0x0006  x240
0x00B8  x167
0x0148  x128
0x0004  x83
0x0007  x80
...
```

The values vary rather than being one constant, and they appear in large runs. That
is consistent with **ZAPD carrying a stale member across limbs** — the same class of
behaviour the OoT work already had to reproduce for binary matching — but confirming
it needs the limbs walked in ZAPD's processing order to show each run inherits the
preceding Skin/Curve limb's count. Worth doing before writing any emulation, since
guessing here produces 1929 plausibly-wrong assets.

## Deferred, with reasons

- **MM:PATH (688 assets).** The path factory needs `num_paths`; OoT recovered it by
  scanning scene commands, which the MM supplemental generator does not do yet.
  Without it the factory reads one entry and follows a garbage pointer, aborting
  extraction. Currently in `DEFERRED_TYPES` in `generate_supplemental.py`.
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
