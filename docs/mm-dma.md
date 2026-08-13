# The MM DMA table: where the offsets come from, and how to check them

## Why this document exists

The OoT side of this harness carried its DMA table offsets as bare constants in
`extract_dma.py`, ported in with no record of where they came from. One of them
was simply wrong: the N64 1.2 ROMs' table lives at `0x7960`, not `0x7430`, and
because nothing verified it, the misaligned table silently dropped the `code`
file entirely. Torch then read a different `code` than ZAPD and crashed, and the
bad DMA also corrupted the generated supplemental metadata. It went unnoticed
until louist103 spotted the missing file (harness commit `00bbf35`).

So: this records the source of the offsets, and the extractor verifies them on
every run rather than trusting them.

## Where the offsets come from

**`OTRExporter/rom_info.py`** — the authoritative source. It is what ZAPD itself
uses to locate the table, so it is by definition the same offset that produced
our reference archive. Every OoT offset in the old `extract_dma.py` traces back
to this file.

It keys on the ROM's **CRC**, read from ROM bytes `[16:20]`, not a SHA1:

| Version | CRC | Filelist | Table offset | XML dir |
|---------|-----|----------|-------------:|---------|
| `ntsc_u` (MM_US_10) | `5354631C` | `mm.txt` | `0x1A500` | `N64_US` |
| `ntsc_u_gc` (MM_US_GC) | `B443EB08` | `mm_gc.txt` | `0x1AE90` | `GC_US` |

`rom_info.py` also lists MM PAL 1.0/1.1, GC JP, and GC PAL. None are in 2ship's
`docs/supportedHashes.json`, so they are out of scope here.

The filelists ship in 2ship at `mm/assets/extractor/filelists/`. `mm.txt` has
1552 lines, one file per line in DMA order; line number *is* the table index.

## Table format

A flat array of 16-byte entries, four big-endian `u32` each:

```
virt_start  virt_end  phys_start  phys_end
```

- `phys_end != 0` → the file is Yaz0 compressed, occupying
  `phys_start .. phys_end` in the ROM.
- `phys_end == 0` → stored uncompressed at `phys_start`.
- `phys_start == phys_end == 0xFFFFFFFF` → **the file is not in the ROM at all.**
  It exists in the virtual address space but has no physical data. See below.
- An all-zero entry terminates the table.

`phys_start` is the ROM offset to use as a segment base in YAML.

## How to verify an offset

Two checks, both in `verify_table()` in `tools/extract_dma.py`, both run on every
extraction:

1. **`dmadata` self-reference.** The table is itself a file in the table, at
   index 2 (`makerom`, `boot`, `dmadata`). Its `virt_start` must equal the offset
   we read the table from. This is the strong check — it is self-validating and
   needs no external ground truth.

2. **Entry count matches the filelist.** Walk to the all-zero terminator; the
   count must equal the number of filelist lines. Catches a stale filelist, and
   catches an offset that happens to land somewhere structurally plausible.

Confirmed both reject bad input, including the subtle case: `0x1A510` (one entry
past the real table) is caught by both checks, and that misalignment-by-a-little
is precisely the `ntsc_1-2` failure mode.

For NTSC-U 1.0 the correct offset produces:

```
makerom     virt 00000000-00001060  phys 00000000-00000000
boot        virt 00001060-0001A500  phys 00001060-00000000
dmadata     virt 0001A500-00020700  phys 0001A500-00000000   <- self-reference
Audiobank   virt 00020700-00046AF0  phys 00020700-00000000
```

`boot` ends exactly where the table begins, and `dmadata` names its own location.

## What differs from OoT

**Absent files.** 17 of the 1552 entries have `phys_start == phys_end ==
0xFFFFFFFF`: declared in the virtual map, absent from the ROM. OoT's extractor
had no concept of this and would have emitted `0xFFFFFFFF` as a real segment
base. They are flagged `"absent": true` in the JSON so downstream can skip them
rather than silently generating garbage offsets.

They are: three `*_syms` entries (`icon_item_static_syms`,
`icon_item_24_static_syms`, `schedule_dma_static_syms`),
`gameplay_object_exchange_static`, and thirteen at the very end of the table —
`anime_model_1..6_static`, `anime_texture_1..6_static`, and
`softsprite_matrix_static`. The trailing ones all have a 0x10- or 0x40-byte
virtual size, i.e. placeholders.

**Almost everything is compressed.** 1513 of 1552 entries are Yaz0; only 22 are
stored plain. Torch gained Yaz0 support during the OoT work, so this is already
handled.

## Regenerating

```sh
python3 tools/extract_dma.py            # roms/mm/ -> dma/
```

Exits non-zero if any ROM is skipped, including on a failed verification. Output
is offsets and names only — no ROM data.
