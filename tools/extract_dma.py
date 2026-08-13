#!/usr/bin/env python3
"""Extract DMA tables from Majora's Mask ROMs and write JSON files.

Usage: python3 extract_dma.py [rom_dir] [out_dir]

Reads each ROM in rom_dir (default: roms/mm/), decodes its DMA table using the
matching 2ship filelist, and writes JSON to out_dir (default: dma/).

Each JSON maps filename -> {virt_start, virt_end, phys_start, phys_end} as hex
strings. Entries the ROM does not actually contain carry "absent": true.

The table offsets come from OTRExporter's rom_info.py, which is what ZAPD itself
uses -- see docs/mm-dma.md. They are verified against the ROM on every run rather
than trusted: a wrong offset silently yields a misaligned table, which is how the
OoT ntsc_1-2 tables were wrong for a while (see Torch harness commit 00bbf35).
"""

import json
import os
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
FILELISTS = os.path.join(ROOT, "2ship", "mm", "assets", "extractor", "filelists")

# Entries whose physical range is this are declared in the virtual address space
# but not present in the ROM.
ABSENT = 0xFFFFFFFF

# version -> (filelist, dma table offset, expected ROM CRC at bytes 16:20)
# Offsets and filelists from OTRExporter rom_info.py; CRCs are its Checksums enum.
ROM_VERSIONS = {
    "ntsc_u":    ("mm.txt",    0x1A500, "5354631C"),  # MM_US_10, XML dir N64_US
    "ntsc_u_gc": ("mm_gc.txt", 0x1AE90, "B443EB08"),  # MM_US_GC, XML dir GC_US
}

# Index of "dmadata" in the filelist. Its own entry describes the table, so its
# virt_start must equal the table offset -- the check that catches a bad offset.
DMADATA_INDEX = 2


def load_filelist(path):
    with open(path) as f:
        return [line.strip() for line in f]


def verify_table(rom, rom_data, off, filelist):
    """Confirm the table really is at off. Returns a list of problems."""
    problems = []

    vs, _, _, _ = struct.unpack_from(">IIII", rom_data, off + 16 * DMADATA_INDEX)
    if vs != off:
        problems.append(
            f"dmadata entry says the table is at 0x{vs:X}, but we read it at 0x{off:X}"
        )

    # The table is terminated by an all-zero entry; it should land exactly at the
    # end of the filelist. Short means the offset is wrong or the filelist is
    # stale; long means the filelist is missing trailing names.
    n = 0
    while off + 16 * (n + 1) <= len(rom_data):
        entry = struct.unpack_from(">IIII", rom_data, off + 16 * n)
        if entry == (0, 0, 0, 0):
            break
        n += 1
    if n != len(filelist):
        problems.append(f"table holds {n} entries but the filelist names {len(filelist)}")

    return problems


def extract_dma_table(rom_data, filelist, dma_offset):
    entries = {}
    for i, name in enumerate(filelist):
        off = dma_offset + 16 * i
        if off + 16 > len(rom_data):
            break
        virt_start, virt_end, phys_start, phys_end = struct.unpack_from(">IIII", rom_data, off)

        entry = {
            "virt_start": f"0x{virt_start:08X}",
            "virt_end": f"0x{virt_end:08X}",
            "phys_start": f"0x{phys_start:08X}",
            "phys_end": f"0x{phys_end:08X}",
        }
        if phys_start == ABSENT or phys_end == ABSENT:
            entry["absent"] = True
        entries[name] = entry

    return entries


def version_from_filename(filename):
    """'ntsc_u_d6133a.z64' -> 'ntsc_u' (strip .z64, then the _<6 char sha> tail)."""
    return filename.rsplit(".", 1)[0].rsplit("_", 1)[0]


def main():
    rom_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "roms", "mm")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dma")

    os.makedirs(out_dir, exist_ok=True)

    filelist_cache = {}
    processed = skipped = 0

    for rom_file in sorted(f for f in os.listdir(rom_dir) if f.endswith(".z64")):
        version = version_from_filename(rom_file)

        if version not in ROM_VERSIONS:
            print(f"  SKIP    {rom_file} (unknown version: {version})")
            skipped += 1
            continue

        filelist_name, dma_offset, expected_crc = ROM_VERSIONS[version]
        filelist_path = os.path.join(FILELISTS, filelist_name)
        if not os.path.exists(filelist_path):
            print(f"  ERROR   {rom_file} — filelist not found: {filelist_path}")
            skipped += 1
            continue
        if filelist_name not in filelist_cache:
            filelist_cache[filelist_name] = load_filelist(filelist_path)
        filelist = filelist_cache[filelist_name]

        with open(os.path.join(rom_dir, rom_file), "rb") as f:
            rom_data = f.read()

        crc = rom_data[16:20].hex().upper()
        if crc != expected_crc:
            print(f"  ERROR   {rom_file} — CRC {crc}, expected {expected_crc} for {version}")
            skipped += 1
            continue

        problems = verify_table(rom_file, rom_data, dma_offset, filelist)
        if problems:
            print(f"  ERROR   {rom_file} — DMA table at 0x{dma_offset:X} does not check out:")
            for p in problems:
                print(f"            {p}")
            skipped += 1
            continue

        entries = extract_dma_table(rom_data, filelist, dma_offset)

        out_path = os.path.join(out_dir, f"{version}.json")
        with open(out_path, "w") as f:
            json.dump(entries, f, indent=2)
            f.write("\n")

        compressed = sum(
            1 for e in entries.values()
            if not e.get("absent") and e["phys_end"] != "0x00000000"
        )
        absent = sum(1 for e in entries.values() if e.get("absent"))
        print(f"  OK      {rom_file} → {version}.json "
              f"({len(entries)} entries, {compressed} compressed, {absent} absent)")
        processed += 1

    print()
    print("--- Summary ---")
    print(f"Processed: {processed}")
    print(f"Skipped:   {skipped}")
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
