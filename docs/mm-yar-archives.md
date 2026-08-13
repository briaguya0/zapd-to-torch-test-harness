# MM `_yar` archives (CmpDma containers)

## What they are

Seven files under `2ship/mm/assets/xml/N64_US/archives/` are not plain asset data
at their DMA offset. They are containers holding one Yaz0-compressed sub-file per
texture, which the game loads through `CmpDma_LoadFile`.

They account for exactly **520 assets**, which is exactly the number of texture
failures in the first scored MM run.

| File | Textures |
|------|---------:|
| `icon_item_static_yar` | 190 |
| `item_name_static` | 120 |
| `map_grand_static` | 98 |
| `map_i_static` | 58 |
| `schedule_dma_static_yar` | 24 |
| `map_name_static` | 16 |
| `icon_item_24_static_yar` | 14 |
| **total** | **520** |

Note the `_yar` suffix is not a reliable marker — `item_name_static`,
`map_grand_static`, `map_i_static` and `map_name_static` use the same format
without it. What they have in common is living under `archives/`.

## The format

Defined by `CmpDma_GetFileInfo` in `2ship/mm/src/code/sys_cmpdma.c`. All values
are big-endian `u32`.

```
word[0]          dataStart -- both the size of this table and the offset where data begins
word[1..n-1]     start offset of sub-file 1..n-1, RELATIVE TO dataStart
word[n]          end offset of the last sub-file (terminator)
<at dataStart>   sub-file 0, then 1, ... each an independent Yaz0 stream
```

- Sub-file count is `dataStart / 4 - 1`.
- Sub-file 0 is implicit: it starts at relative 0, and `word[1]` is its size.
  (`CmpDma_GetFileInfo` special-cases `refOff == 0` for exactly this.)
- Sub-file `i > 0` spans `[word[i], word[i+1])` relative to `dataStart`.

**The offsets are relative to `dataStart`, not absolute within the file.** This is
the detail that makes the format look wrong on a first read: `word[1]` of
`icon_item_24_static_yar` is `0x6A0`, and there is no Yaz0 magic at `0x6A0` —
the sub-file is at `0x6A0 + 0x3C`.

The XML's texture `Offset` attributes index into the **concatenation of all
decompressed sub-files**, which is what `CmpDma_LoadAllFiles` builds. Verified
across all seven archives: sub-file count equals the XML's texture count, and the
total decompressed size equals the highest XML `Offset` plus that texture's size,
exactly.

Worked example, `icon_item_24_static_yar` (DMA `phys_start` `0x009C6230`):

```
dataStart = 0x3C          -> 15 table words, 14 sub-files
sub-file  0  rel 0x00000  size 0x6A0  Yaz0 -> 0x900   (24*24*4, one RGBA32 texture)
sub-file  1  rel 0x006A0  size 0x660  Yaz0 -> 0x900
...
sub-file 13  rel 0x046C0  size 0x1C0  Yaz0 -> 0x200
word[14] = 0x4880 terminator; 0x4880 + 0x3C = 0x48BC ~ the DMA virtual size 0x48C0
total decompressed 0x7700 == highest XML offset + size
```

## Why Torch gets it wrong today

`Decompressor::GetCompressionType` (`src/utils/Decompressor.cpp:336`) identifies
compression by sniffing a magic at the segment offset — `MIO0`, `Yay0`, `Yay1`,
`Yaz0`. A CmpDma container begins with its `dataStart` word (`0000003C` here), no
magic, so it is treated as uncompressed. Torch then applies the XML offsets to the
raw container bytes and every texture in it decodes to garbage.

The DMA table agrees it is uncompressed (`phys_end == 0`), and it is — the
*container* is stored plain. The compression is one level down.

## Proposed fix

A new `CompressionType` in Torch whose decode step walks the table and
concatenates the Yaz0 sub-files. Every existing offset path then works unchanged,
because the XML offsets already address that concatenation.

It should be an **explicit opt-in in the YAML**, not auto-detection: `0000003C` is
a plausible leading word for ordinary data, so sniffing it would risk
misidentifying unrelated files. Something like:

```yaml
:config:
  segments:
    - [ 9, icon_item_24_static_yar ]
  compression: CMPDMA
```

That keeps the change additive — no existing YAML sets the key, so OoT extraction
cannot be affected.

This is Phase 5 work (a Torch feature), not a harness or config fix.
