#!/usr/bin/env python3
"""Convert 2ship/ZAPD MM XML asset definitions to Torch YAML format.

Reads XML asset definitions, converts them to Torch YAML, and injects the
supplemental asset metadata (VTX arrays, child DLists, limbs, collision, Set_
alternate headers, MTX offsets, ...) from generate_supplemental.py.

Usage:
    python3 zapd_to_torch.py --xml-dir <dir> --dma-json <file> --out-dir <dir> [--supplemental-json <file>] [--types TYPE1,TYPE2,...]

Example:
    python3 tools/zapd_to_torch.py \
        --xml-dir 2ship/mm/assets/xml/N64_US \
        --dma-json dma/ntsc_u.json \
        --out-dir assets/yml/ntsc_u \
        --supplemental-json supplemental/ntsc_u.json

    # Only convert specific types (dependencies are pulled in automatically):
    python3 tools/zapd_to_torch.py \
        --xml-dir 2ship/mm/assets/xml/N64_US \
        --dma-json dma/ntsc_u.json \
        --out-dir assets/yml/ntsc_u \
        --types Texture,Blob,DList
"""

import argparse
import json
import os
import collections
import re
import sys
import xml.etree.ElementTree as ET


# Map XML element names to Torch YAML type strings.
#
# Bare names are Torch's shared factories and work today. MM:-prefixed names are
# Majora's Mask factories that do not exist in Torch yet -- emitting them is how
# we find out what still has to be written. See docs/2ship-plan.md phase 5.
TYPE_MAP = {
    # Shared factories, already in Torch
    "Blob": "BLOB",
    "Texture": "TEXTURE",
    "DList": "GFX",
    "Vtx": "VTX",
    "Array": "MM:ARRAY",
    # MM-specific, pending factories
    "Mtx": "MM:MTX",
    "Skeleton": "MM:SKELETON",
    "Limb": "MM:LIMB",
    "Animation": "MM:ANIMATION",
    "CurveAnimation": "MM:CURVE_ANIMATION",
    "KeyFrameAnimation": "MM:KEYFRAME_ANIMATION",
    "KeyFrameSkel": "MM:KEYFRAME_SKELETON",
    "PlayerAnimation": "MM:PLAYER_ANIMATION",
    "PlayerAnimationData": "MM:PLAYER_ANIMATION_DATA",
    "Scene": "MM:SCENE",
    "Room": "MM:ROOM",
    "Collision": "MM:COLLISION",
    "Cutscene": "MM:CUTSCENE",
    "TextureAnimation": "MM:TEXTURE_ANIMATION",
    "TextMM": "MM:TEXT",
    "Soundfont": "MM:SOUNDFONT",
    "Sample": "MM:SAMPLE",
    "Sequence": "MM:SEQUENCE",
    "Audio": "MM:AUDIO",
}

# XML element names that are structural, not assets. Vector/Scalar/Pointer/
# CollisionPoly describe an Array's element kind and are read by convert_array;
# they are never assets in their own right (they carry no Name or Offset).
SKIP_ELEMENTS = {
    "Root", "File", "ExternalFile", "Samples", "Sequences", "Symbol",
    "Vector", "Scalar", "Pointer", "CollisionPoly",
}


def convert_texture(elem):
    """Convert a Texture XML element to YAML dict."""
    entry = {
        "type": "TEXTURE",
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
        "format": elem.get("Format").upper(),
        "width": int(elem.get("Width")),
        "height": int(elem.get("Height")),
    }
    if elem.get("TlutOffset"):
        entry["tlut"] = hex_val(elem.get("TlutOffset"))
    if elem.get("ExternalTlut"):
        entry["external_tlut"] = elem.get("ExternalTlut")
        entry["external_tlut_offset"] = hex_val(elem.get("ExternalTlutOffset"))
    return entry


def convert_blob(elem):
    """Convert a Blob XML element to YAML dict."""
    return {
        "type": "BLOB",
        "offset": hex_val(elem.get("Offset")),
        "size": hex_val(elem.get("Size")),
        "symbol": elem.get("Name"),
    }


def convert_limb_table(elem):
    """Convert a LimbTable XML element to a 0-byte BLOB.

    OTRExporter has no exporter for LimbTable, so it writes a 0-byte file.
    """
    return {
        "type": "BLOB",
        "offset": hex_val(elem.get("Offset")),
        "size": 0,
        "symbol": elem.get("Name"),
    }


def convert_dlist(elem):
    """Convert a DList XML element to YAML dict."""
    return {
        "type": "GFX",
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
    }


def convert_vtx(elem):
    """Convert a Vtx XML element to YAML dict."""
    entry = {
        "type": "VTX",
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
    }
    if elem.get("Count"):
        entry["count"] = int(elem.get("Count"))
    return entry


def convert_mtx(elem):
    """Convert a Mtx XML element to YAML dict."""
    return {
        "type": TYPE_MAP["Mtx"],
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
    }


# Array element kinds the Torch array factory cannot build yet. MM declares four
# such arrays in total; they are skipped and tallied rather than emitted, since an
# array with no array_type aborts the whole extraction.
UNSUPPORTED_ARRAY_KINDS = collections.Counter()


def convert_array(elem):
    """Convert an Array XML element to YAML dict, or None if unsupported."""
    entry = {
        "type": "MM:ARRAY",
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
        "count": int(elem.get("Count")),
    }
    # Child elements define the array's element type
    for child in elem:
        if child.tag == "Vtx":
            entry["array_type"] = "VTX"
        elif child.tag == "Scalar":
            # ZScalarType, from ZScalar.h. Only the widths MM actually uses.
            scalar_types = {"s8": 1, "u8": 2, "x8": 3, "s16": 4, "u16": 5, "x16": 6,
                            "s32": 7, "u32": 8, "x32": 9}
            st = scalar_types.get((child.get("Type") or "").lower())
            if st is not None:
                entry["array_type"] = "Scalar"
                entry["scalar_type"] = st
        elif child.tag == "Vector":
            vec_type = child.get("Type", "s16")
            dims = child.get("Dimensions", "3")
            if vec_type == "s16" and dims == "3":
                entry["array_type"] = "Vec3s"
            elif vec_type == "f32" and dims == "3":
                entry["array_type"] = "Vec3f"
        break

    if "array_type" not in entry:
        kind = elem[0].tag if len(elem) else "<no child>"
        if len(elem) and elem[0].get("Type"):
            kind += "/" + elem[0].get("Type")
        UNSUPPORTED_ARRAY_KINDS[kind] += 1
        return None
    return entry


def convert_audio(elem):
    """Convert an Audio XML element with full metadata extraction."""
    entry = {
        "type": "MM:AUDIO",
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
        "sound_font_table_offset": hex_val(elem.get("SoundFontTableOffset")),
        "sequence_table_offset": hex_val(elem.get("SequenceTableOffset")),
        "sample_bank_table_offset": hex_val(elem.get("SampleBankTableOffset")),
        "sequence_font_table_offset": hex_val(elem.get("SequenceFontTableOffset")),
    }

    # Extract sequence names
    seqs_elem = elem.find("Sequences")
    if seqs_elem is not None:
        entry["sequences"] = [s.get("Name") for s in seqs_elem.findall("Sequence")]

    # Extract sample names per bank
    samples_by_bank = []
    for samples_elem in elem.findall("Samples"):
        bank = int(samples_elem.get("Bank", "0"))
        bank_samples = []
        for sample in samples_elem.findall("Sample"):
            s = {"name": sample.get("Name"), "offset": hex_val(sample.get("Offset"))}
            if sample.get("SampleRate"):
                s["sample_rate"] = int(sample.get("SampleRate"))
            bank_samples.append(s)
        samples_by_bank.append({"bank": bank, "entries": bank_samples})
    if samples_by_bank:
        entry["samples"] = samples_by_bank

    # Extract font (soundfont) names
    fonts = []
    for child in elem:
        if child.tag == "Soundfont":
            fonts.append({"name": child.get("Name"), "index": int(child.get("Index", 0))})
    if fonts:
        entry["fonts"] = sorted(fonts, key=lambda f: f["index"])

    return entry


def convert_generic(elem):
    """Generic converter for OoT-specific types (Phase 2+)."""
    torch_type = TYPE_MAP.get(elem.tag)
    if not torch_type:
        return None
    entry = {
        "type": torch_type,
        "offset": hex_val(elem.get("Offset")),
        "symbol": elem.get("Name"),
    }
    # Preserve type-specific attributes
    if elem.get("Size"):
        entry["size"] = hex_val(elem.get("Size"))
    if elem.get("LimbType"):
        entry["limb_type"] = elem.get("LimbType")
    if elem.get("Type"):
        # `Type` means different things per element. On a Skeleton it is the
        # skeleton kind (Flex/Normal/Curve) and LimbType carries the limb kind.
        # On a Limb there is no second attribute -- Type *is* the limb kind
        # (Standard/LOD/Curve/Skin), which is what the limb factory reads.
        if elem.tag == "Limb":
            entry.setdefault("limb_type", elem.get("Type"))
        else:
            entry["skel_type"] = elem.get("Type")
    if elem.get("FrameCount"):
        entry["frame_count"] = int(elem.get("FrameCount"))
    if elem.get("NumPaths"):
        entry["num_paths"] = int(elem.get("NumPaths"))
    if elem.get("SkelOffset"):
        entry["skel_offset"] = hex_val(elem.get("SkelOffset"))
    # A KeyFrameAnimation names its skeleton with `Skel`; the animation is sized
    # by that skeleton's limb count and limb type.
    if elem.get("Skel"):
        entry["skel_offset"] = hex_val(elem.get("Skel"))
    if elem.tag == "LegacyAnimation":
        entry["anim_type"] = "legacy"
    if elem.get("CodeOffset"):
        entry["code_offset"] = hex_val(elem.get("CodeOffset"))
    if elem.get("LangOffset"):
        entry["lang_offset"] = hex_val(elem.get("LangOffset"))
    if elem.get("Language"):
        entry["language"] = elem.get("Language")
    return entry


def hex_val(v, default="0x0"):
    """Normalize a hex value: ensure 0x prefix, default if None."""
    if v is None:
        return default
    v = v.strip()
    if v.startswith("0x") or v.startswith("0X"):
        return v
    # Bare hex string from XML (e.g. "70" meaning 0x70)
    return "0x" + v


CONVERTERS = {
    "Texture": convert_texture,
    "Blob": convert_blob,
    "DList": convert_dlist,
    "Vtx": convert_vtx,
    "Mtx": convert_mtx,
    "Array": convert_array,
    "LimbTable": convert_limb_table,
    "Audio": convert_audio,
}


def yaml_value(v):
    """Format a value for YAML output."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        # Keep hex values as-is
        if v.startswith("0x") or v.startswith("0X"):
            return v
        return v
    return str(v)


def _format_config(segment, seg_base, extra_segments=None, external_files=None, virtual=None, directory=None,
                   compression=None):
    """Format the :config: section of a YAML file."""
    lines = [":config:\n", "  segments:\n", f"    - [ {segment}, {seg_base} ]\n"]
    if extra_segments:
        for seg_num, seg_start in extra_segments:
            lines.append(f"    - [ {seg_num}, {seg_start} ]\n")
    if virtual:
        lines.append(f"  virtual: [ {virtual[0]}, {virtual[1]} ]\n")
    if directory:
        lines.append(f"  directory: {directory}\n")
    if compression:
        lines.append(f"  compression: {compression}\n")
    if external_files:
        lines.append("  external_files:\n")
        for ef in external_files:
            lines.append(f"    - {ef}\n")
    lines.append("\n")
    return "".join(lines)


def _format_asset(asset):
    """Format a single asset entry as YAML text."""
    name = asset.get("symbol", asset.get("type", "unknown"))
    lines = [f"{name}:\n"]
    for k, v in asset.items():
        if isinstance(v, list):
            lines.append(f"  {k}:\n")
            for item in v:
                if isinstance(item, dict):
                    # Nested dict in list (e.g., sample bank entries)
                    first = True
                    for dk, dv in item.items():
                        prefix = "    - " if first else "      "
                        first = False
                        if isinstance(dv, list):
                            lines.append(f"{prefix}{dk}:\n")
                            for sub in dv:
                                if isinstance(sub, dict):
                                    sfirst = True
                                    for sk, sv in sub.items():
                                        sp = "        - " if sfirst else "          "
                                        sfirst = False
                                        lines.append(f"{sp}{sk}: {yaml_value(sv)}\n")
                                else:
                                    lines.append(f"        - {yaml_value(sub)}\n")
                        else:
                            lines.append(f"{prefix}{dk}: {yaml_value(dv)}\n")
                else:
                    lines.append(f"    - {yaml_value(item)}\n")
        else:
            lines.append(f"  {k}: {yaml_value(v)}\n")
    lines.append("\n")
    return "".join(lines)


def _parse_existing_yaml(path):
    """Parse an existing YAML file to extract config section and existing asset names."""
    with open(path) as f:
        content = f.read()

    # Find all top-level YAML keys (non-indented lines ending with ':')
    lines = content.split("\n")
    existing_assets = set()
    config_end = 0

    for i, line in enumerate(lines):
        if line and not line.startswith(" ") and not line.startswith("\t") and line.endswith(":"):
            if line == ":config:":
                continue
            if config_end == 0:
                # First non-config key marks end of config section
                config_end = sum(len(l) + 1 for l in lines[:i])
            existing_assets.add(line[:-1])

    if config_end == 0:
        config_end = len(content)

    config_text = content[:config_end]
    assets_text = content[config_end:]
    return config_text, assets_text, existing_assets


def _asset_sort_key(asset):
    """Sort key: MM:SCENE/MM:ROOM first, then everything else.
    This ensures scene factory processes rooms before GFX DLists,
    preventing VTX auto-discovery conflicts."""
    t = asset.get("type", "")
    if t in ("MM:SCENE", "MM:ROOM"):
        return (0, asset.get("symbol", ""))
    return (1, asset.get("symbol", ""))

def write_yaml(path, segment, seg_base, assets, extra_segments=None, external_files=None, virtual=None, directory=None,
               compression=None):
    """Write a Torch YAML file, merging with existing content if the file exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    assets = sorted(assets, key=_asset_sort_key)

    new_config = _format_config(segment, seg_base, extra_segments, external_files, virtual, directory=directory,
                                compression=compression)

    if os.path.exists(path):
        old_config, old_assets, existing_names = _parse_existing_yaml(path)

        # Use the config with more segments/external_files (longer = more complete)
        config = new_config if len(new_config) >= len(old_config) else old_config

        # Append only new assets
        new_asset_text = ""
        for asset in assets:
            name = asset.get("symbol", asset.get("type", "unknown"))
            if name not in existing_names:
                new_asset_text += _format_asset(asset)

        if not new_asset_text and config == old_config:
            return  # Nothing new to add and config unchanged

        with open(path, "w") as f:
            f.write(config)
            f.write(old_assets)
            if not old_assets.endswith("\n"):
                f.write("\n")
            if new_asset_text:
                f.write(new_asset_text)
    else:
        with open(path, "w") as f:
            f.write(new_config)
            for asset in assets:
                f.write(_format_asset(asset))


def get_out_name_from_xml(xml_path):
    """Return the name an XML's first File is emitted under (OutName, else Name)."""
    try:
        tree = ET.parse(xml_path)
        for file_elem in tree.getroot().iter("File"):
            return file_elem.get("OutName", file_elem.get("Name"))
    except (ET.ParseError, FileNotFoundError):
        return None
    return None


def get_dma_name_from_xml(xml_path):
    """Return the DMA file name an XML describes, from its first File element.

    MM's archive XMLs are not named after the file they contain --
    archives/icon_item_static.xml holds <File Name="icon_item_static_yar">. An
    ExternalFile reference names the XML, so the DMA name has to be read out of it
    rather than derived from the path, or the reference is silently dropped and
    every display list pointing into that file fails to resolve.
    """
    try:
        tree = ET.parse(xml_path)
        for file_elem in tree.getroot().iter("File"):
            return file_elem.get("Name")
    except (ET.ParseError, FileNotFoundError):
        return None
    return None


def get_segment_from_xml(xml_path):
    """Parse an XML file and return the segment number from the first File element."""
    try:
        tree = ET.parse(xml_path)
        for file_elem in tree.getroot().iter("File"):
            # No Segment or Segment="0" → use ZAPD default 0x80 (virtual addresses)
            # Segment="0" is a stale ZAPD workaround, removed upstream in zeldaret/oot#1459
            seg = file_elem.get("Segment")
            if seg is None or seg == "0":
                return 0x80
            return int(seg)
    except (ET.ParseError, FileNotFoundError, ValueError):
        return None
    return None


def xml_has_asset_types(xml_path, types=None):
    """Check if an XML file has any asset elements of the given types (or any asset if types is None)."""
    if types is None:
        types = {"Texture", "Blob", "DList", "PlayerAnimationData"}
    try:
        tree = ET.parse(xml_path)
        for file_elem in tree.getroot().iter("File"):
            for elem in file_elem:
                if elem.tag in types:
                    return True
    except (ET.ParseError, FileNotFoundError):
        pass
    return False


def get_scene_prefix(xml_rel_path):
    """Determine the scene output prefix.

    MM has no Master Quest, but OTRExporter still emits under the nonmq prefix --
    the reference archive's scene paths are all scenes/nonmq/<SCENE>/<asset>, with
    no shared/ or mq/ sibling. So the prefix is constant, but it is not "scenes".
    """
    return "scenes/nonmq"


def get_output_category(xml_rel_path):
    """Map XML relative path to output category directory."""
    # xml_rel_path is like "objects/object_link_child.xml" or "scenes/SPOT00/SPOT00.xml"
    if xml_rel_path.startswith("scenes/"):
        return get_scene_prefix(xml_rel_path)
    # The reference archive does not keep these two XML directories in the asset
    # path: interface/icon_item_24_static_yar/... is emitted as
    # icon_item_24_static_yar/... . Everything else keeps its directory.
    for flattened in ("interface/", "archives/"):
        if xml_rel_path.startswith(flattened):
            return os.path.dirname(xml_rel_path[len(flattened):])
    return os.path.dirname(xml_rel_path)


def get_scene_directory(xml_rel_path):
    """Get the scene directory for a scene XML file.

    All assets from a scene XML (scene + rooms) output under the same directory,
    e.g. scenes/SPOT00/SPOT00.xml → scenes/nonmq/SPOT00. Unlike OoT there is no
    _scene suffix: the reference names the directory after the scene itself.
    """
    prefix = get_scene_prefix(xml_rel_path)
    stem = os.path.splitext(os.path.basename(xml_rel_path))[0]
    return f"{prefix}/{stem}"


def process_xml(xml_path, xml_rel_path, dma_table, out_dir, allowed_types, xml_dir=None):
    """Process a single XML file and write YAML output(s)."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"  SKIP (parse error): {xml_rel_path}: {e}", file=sys.stderr)
        return 0, 0

    root = tree.getroot()
    category = get_output_category(xml_rel_path)
    files_written = 0
    assets_written = 0

    # Collect ExternalFile references (children of Root, not File)
    extra_segments = []
    external_files = []
    out_prefix = os.path.basename(os.path.normpath(out_dir))
    for ext_elem in root.iter("ExternalFile"):
        ext_xml_path = ext_elem.get("XmlPath", "")
        ext_full_path_probe = os.path.join(xml_dir, ext_xml_path) if xml_dir else None
        ext_dma_name = None
        if ext_full_path_probe:
            ext_dma_name = get_dma_name_from_xml(ext_full_path_probe)
        if not ext_dma_name:
            ext_dma_name = os.path.splitext(os.path.basename(ext_xml_path))[0]
        if ext_dma_name in dma_table:
            ext_full_path = ext_full_path_probe
            # Only include if the external XML has texture/DList assets we can use
            if ext_full_path and not xml_has_asset_types(ext_full_path, allowed_types):
                continue
            ext_seg = get_segment_from_xml(ext_full_path) if ext_full_path else None
            if ext_seg is not None:
                extra_segments.append((ext_seg, ext_dma_name))
                ext_category = get_output_category(ext_xml_path)
                ext_out_name = get_out_name_from_xml(ext_full_path) or ext_dma_name
                ext_yml = f"{ext_category}/{ext_out_name}.yml" if ext_category else f"{ext_out_name}.yml"
                external_files.append(f"{out_prefix}/{ext_yml}")

    for file_elem in root.iter("File"):
        dma_name = file_elem.get("Name")
        out_name = file_elem.get("OutName", dma_name)
        # No Segment or Segment="0" → use ZAPD default 0x80 (virtual addresses)
        # Segment="0" is a stale ZAPD workaround, removed upstream in zeldaret/oot#1459
        seg_attr = file_elem.get("Segment")
        segment = 0x80 if seg_attr is None or seg_attr == "0" else int(seg_attr)
        base_address = file_elem.get("BaseAddress")

        if dma_name not in dma_table:
            print(f"  SKIP (no DMA entry): {dma_name}", file=sys.stderr)
            continue

        dma_entry = dma_table[dma_name]
        # Segment bases are emitted as DMA file names, not hex offsets; Torch
        # resolves them through the filelist (PR #253). See assets/yml/README.md.
        seg_base = dma_name
        # `virtual:` is still parsed as a raw uint32 by Torch (Companion.cpp:657),
        # so it keeps the literal offset rather than a name.
        phys_start = dma_entry["phys_start"]

        # Copy per-XML externals and auto-add segments for objects with DLists
        file_extra_segments = list(extra_segments)
        file_external_files = list(external_files)
        has_dlists = any(elem.tag == "DList" for elem in file_elem)
        if has_dlists:
            # Auto-add gameplay_keep (segment 4)
            gk_name = "gameplay_keep"
            if gk_name in dma_table and dma_name != gk_name:
                gk_already = any(seg == 4 for seg, _ in file_extra_segments)
                if not gk_already:
                    file_extra_segments.append((4, gk_name))
                    file_external_files.append(f"{out_prefix}/objects/{gk_name}.yml")
            # Auto-add segments 8-13 = same file (used for skeleton/limb texture references).
            # OoT uses these for eye textures, mouth textures, and limb DLists.
            #
            # Only segments ABOVE the file's own. Torch treats a segment as an alias
            # when a lower-numbered segment maps to the same file offset
            # (IsAliasSegment in OoTDListHelpers.cpp), and emits pointer+1 for
            # anything reaching it rather than resolving. That never bites OoT,
            # whose objects sit on segment 6 with all of 8-13 above it. MM puts 24
            # mask objects on segment 10 and its code files on 0x80, so adding 8 and
            # 9 underneath made every vertex reference in them look like an alias.
            for extra_seg in range(8, 14):
                if extra_seg <= segment:
                    continue
                if not any(seg == extra_seg for seg, _ in file_extra_segments):
                    file_extra_segments.append((extra_seg, seg_base))

        # Auto-add audio segments when an Audio element is present
        has_audio = any(elem.tag == "Audio" for elem in file_elem)
        if has_audio:
            for seg_name, seg_id in [("Audiobank", 1), ("Audioseq", 2), ("Audiotable", 3)]:
                if seg_name in dma_table:
                    if not any(seg == seg_id for seg, _ in file_extra_segments):
                        file_extra_segments.append((seg_id, seg_name))

        is_room_file = xml_rel_path.startswith("scenes/") and "_room_" in out_name

        # A LimbTable states how many limbs actually exist, which can be fewer than
        # the skeleton header claims (object_fsn: header says 18, table says 17,
        # and the xml comments on the discrepancy). ZAPD trusts the table.
        limb_table_count = None
        for elem in file_elem:
            if elem.tag == "LimbTable" and elem.get("Count"):
                limb_table_count = int(elem.get("Count"))
                break

        assets = []
        for elem in file_elem:
            if elem.tag in SKIP_ELEMENTS:
                continue

            # Skip DList entries in room files that will be auto-discovered by the
            # scene factory's SetMesh processing. Keep others (child DLists, scene-level).
            # All DLists MUST be ordered after MM:ROOM in the YAML (see write_yaml
            # sorting) to avoid VTX auto-discovery conflicts.
            # We can't tell which DLists are mesh vs child from XML alone, so we keep
            # all of them. The scene factory's AddAsset deduplicates: if it already
            # auto-discovered a DList at the same offset, the YAML entry is a no-op.
            # DLists at new offsets (child DLists, scene-level) get created normally.

            if allowed_types and elem.tag not in allowed_types:
                continue

            converter = CONVERTERS.get(elem.tag, convert_generic)
            entry = converter(elem)
            if entry:
                if elem.tag == "Skeleton" and limb_table_count is not None:
                    entry["limb_table_count"] = limb_table_count
                # Text assets need the code section's physical ROM address
                if elem.tag in ("Text", "TextMM") and "code" in dma_table:
                    entry["code_phys_start"] = dma_table["code"]["phys_start"]
                assets.append(entry)

        if not assets:
            continue

        yaml_path = os.path.join(out_dir, category, f"{out_name}.yml")
        virtual = (hex_val(base_address), phys_start) if base_address else None

        # Directory overrides for assets that need custom output paths.
        directory = None

        # Audio: YAML goes to audio.yml (not audio/audio.yml) so the asset
        # path audio/audio matches the YAML-derived path (dirname=audio, symbol=audio).
        if has_audio:
            yaml_path = os.path.join(out_dir, f"{out_name}.yml")

        # For scene files, room YAMLs need a directory override so their assets
        # output under the scene's directory (e.g. scenes/nonmq/bdan_scene).
        if xml_rel_path.startswith("scenes/"):
            scene_dir = get_scene_directory(xml_rel_path)
            # Room files need the directory override and the scene's segment 2 so
            # their DLists can reach scene textures. OoT detected "not a scene" by
            # the _scene suffix; MM scene files have no suffix, so that test also
            # caught the scene itself -- giving it a duplicate segment 2 and an
            # external_files entry pointing at itself. Key on being a room instead.
            if "_room_" in out_name:
                directory = scene_dir
                # Room DLists reference segment 2 textures from the scene file.
                # Add the scene's segment 2 so Torch can resolve those references.
                stem = os.path.splitext(os.path.basename(xml_rel_path))[0]
                scene_dma_name = stem
                if scene_dma_name in dma_table:
                    if not any(seg == 2 for seg, _ in file_extra_segments):
                        file_extra_segments.append((2, scene_dma_name))
                    # Add scene YAML as external file so Torch can find scene textures
                    scene_yml = f"{out_prefix}/{category}/{scene_dma_name}.yml"
                    if scene_yml not in file_external_files:
                        file_external_files.append(scene_yml)
                # OoT room DLists reference gMtxClear via a VRAM address and need
                # code/sys_matrix.yml as an external. MM has no sys_matrix XML and no
                # gMtxClear in its reference, so only add it where it exists.
                sys_matrix_xml = os.path.join(xml_dir, "code", "sys_matrix.xml") if xml_dir else None
                if sys_matrix_xml and os.path.isfile(sys_matrix_xml):
                    sys_matrix_yml = f"{out_prefix}/code/sys_matrix.yml"
                    if sys_matrix_yml not in file_external_files:
                        file_external_files.append(sys_matrix_yml)

        # Files under archives/ are MM CmpDma containers: a table of u32 offsets
        # followed by one Yaz0 stream per asset. They carry no magic, so Torch
        # cannot sniff them and the file has to say so. See docs/mm-yar-archives.md.
        compression = "CMPDMA" if xml_rel_path.startswith("archives/") else None

        write_yaml(yaml_path, segment, seg_base, assets,
                   compression=compression,
                   extra_segments=file_extra_segments or None,
                   external_files=file_external_files or None,
                   virtual=virtual,
                   directory=directory)
        files_written += 1
        assets_written += len(assets)

    return files_written, assets_written


# --- VTX discovery from reference O2R ---

def add_undeclared_to_yaml(yaml_path, entries):
    """Append undeclared asset entries to a YAML file."""
    with open(yaml_path) as f:
        content = f.read()

    # Check which entries already exist (by name) and which (offset, type)
    # slots are already claimed by an XML-declared asset. A supplemental asset
    # that lands on an offset already declared by the XML under a different name
    # is an alias (e.g. the room-relative name of a scene-declared shared DList);
    # emitting it as its own declaration would make Torch self-hash it under the
    # wrong name. Skip it and let Torch's mesh writer regenerate it as an alias.
    existing = set()
    existing_slots = set()
    cur_type = None
    cur_offset = None
    for line in content.split("\n"):
        if line and not line.startswith(" ") and line.endswith(":") and line != ":config:":
            existing.add(line[:-1])
            cur_type = None
            cur_offset = None
        elif line.strip().startswith("type:"):
            cur_type = line.split(":", 1)[1].strip()
        elif line.strip().startswith("offset:"):
            cur_offset = line.split(":", 1)[1].strip()
            if cur_type is not None:
                try:
                    existing_slots.add((int(cur_offset, 16), cur_type))
                except ValueError:
                    pass

    new_entries = []
    for entry in sorted(entries, key=lambda x: int(x["offset"], 16)):
        if entry["name"] in existing:
            continue
        if (int(entry["offset"], 16), entry["type"]) in existing_slots:
            continue

        lines = f'{entry["name"]}:\n'
        lines += f'  type: {entry["type"]}\n'
        lines += f'  offset: {entry["offset"]}\n'
        lines += f'  symbol: {entry["symbol"]}\n'
        # Type-specific fields
        if "count" in entry:
            lines += f'  count: {entry["count"]}\n'
        if "array_type" in entry:
            lines += f'  array_type: {entry["array_type"]}\n'
        # Supplemental VTX arrays are the ones ZAPD auto-discovers from display
        # lists and emits via its VTX() text round-trip. That path drops the flag
        # field and never emits a cross-file-resolvable symbol, so ZAPD zeroes the
        # flag and nulls cross-file references to them. XML-declared <Array><Vtx/>
        # arrays keep both. Tell Torch to do the same for these.
        if entry.get("array_type") == "VTX":
            lines += f'  zero_flag: true\n'
            lines += f'  null_cross_file: true\n'
        if "limb_type" in entry:
            lines += f'  limb_type: {entry["limb_type"]}\n'
        if "format" in entry:
            lines += f'  format: {entry["format"]}\n'
        if "width" in entry:
            lines += f'  width: {entry["width"]}\n'
        if "height" in entry:
            lines += f'  height: {entry["height"]}\n'
        if "size" in entry:
            lines += f'  size: {entry["size"]}\n'
        if "base_name" in entry:
            lines += f'  base_name: {entry["base_name"]}\n'
        if "segments" in entry:
            lines += f'  segments:\n'
            for seg in entry["segments"]:
                lines += f'    - [ {seg[0]}, {seg[1]} ]\n'
        new_entries.append(lines)

    if not new_entries:
        return 0

    if not content.endswith("\n"):
        content += "\n"

    with open(yaml_path, "w") as f:
        f.write(content)
        for entry in new_entries:
            f.write("\n")
            f.write(entry)

    return len(new_entries)


def _read_yaml_config(yaml_path):
    """Read :config: section from a YAML file."""
    config = {"directory": None, "external_files": [], "segments": []}
    with open(yaml_path) as f:
        in_config = False
        in_field = None
        for line in f:
            stripped = line.rstrip()
            if stripped == ":config:":
                in_config = True
                continue
            if not in_config:
                continue
            # End of config: non-indented non-empty line that's not a config field
            if stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
                break
            s = stripped.strip()
            if s.startswith("directory:"):
                config["directory"] = s.split(":", 1)[1].strip()
                in_field = None
            elif s == "external_files:":
                in_field = "external_files"
            elif s == "segments:":
                in_field = "segments"
            elif s.startswith("- ") and in_field == "external_files":
                config["external_files"].append(s[2:].strip())
            elif s.startswith("- ") and in_field == "segments":
                config["segments"].append(s[2:].strip())
            elif s and not s.startswith("-"):
                in_field = None
    return config


def _write_set_yaml(yaml_path, entry, parent_config):
    """Write a separate YAML file for a Set_ entry with its own :config."""
    os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
    with open(yaml_path, "w") as f:
        f.write(":config:\n")
        # Write segments from the entry
        if "segments" in entry:
            f.write("  segments:\n")
            for seg in entry["segments"]:
                f.write(f"    - [ {seg[0]}, {seg[1]} ]\n")
        # Copy directory and external_files from parent
        if parent_config["directory"]:
            f.write(f"  directory: {parent_config['directory']}\n")
        if parent_config["external_files"]:
            f.write("  external_files:\n")
            for ef in parent_config["external_files"]:
                f.write(f"    - {ef}\n")
        f.write("\n")
        # Write the asset entry
        f.write(f"{entry['name']}:\n")
        f.write(f"  type: {entry['type']}\n")
        f.write(f"  offset: {entry['offset']}\n")
        f.write(f"  symbol: {entry['symbol']}\n")
        if "base_name" in entry:
            f.write(f"  base_name: {entry['base_name']}\n")


def _append_external_files(yaml_path, new_external_files):
    """Add external file references to an existing YAML file's :config section."""
    with open(yaml_path) as f:
        content = f.read()

    lines = content.split("\n")
    insert_idx = None
    in_config = False
    in_external = False
    config_end = None

    for i, line in enumerate(lines):
        if line.strip() == ":config:":
            in_config = True
        elif in_config and line.strip() == "external_files:":
            in_external = True
        elif in_external and line.strip().startswith("- "):
            insert_idx = i + 1
        elif in_external and not line.strip().startswith("- ") and line.strip():
            if insert_idx is None:
                insert_idx = i
            break
        elif in_config and not in_external and line.strip() and not line.startswith(" "):
            # End of :config: section — no external_files found
            config_end = i
            in_config = False

    if insert_idx is not None:
        # Append to existing external_files section
        for ef in new_external_files:
            lines.insert(insert_idx, f"    - {ef}")
            insert_idx += 1
    elif config_end is not None:
        # No external_files section — add one before end of config
        new_lines = ["  external_files:"]
        for ef in new_external_files:
            new_lines.append(f"    - {ef}")
        for j, nl in enumerate(new_lines):
            lines.insert(config_end + j, nl)
    else:
        return  # no :config: found

    with open(yaml_path, "w") as f:
        f.write("\n".join(lines))


def add_supplemental_from_json(supplemental_json_path, yaml_dir):
    """Add supplemental assets to YAML files. Keys are YAML-path keys.

    Handles BLOB entries with _skel_name/_limb_count that need offset resolved
    from the parent skeleton's offset in the same YAML file.
    """
    with open(supplemental_json_path) as f:
        assets_by_file = json.load(f)

    total_added = 0
    files_updated = 0

    for file_key, entries in sorted(assets_by_file.items()):
        yaml_path = os.path.join(yaml_dir, f"{file_key}.yml")
        if not os.path.exists(yaml_path):
            continue

        # Separate entries into normal (append to parent) and Set_ (own YAML file)
        normal_entries = []
        set_entries = []
        for entry in entries:
            if "_skel_name" in entry:
                # Resolve BLOB offset from parent skeleton
                skel_name = entry["_skel_name"]
                limb_count = entry["_limb_count"]
                skel_offset = None
                with open(yaml_path) as yf:
                    in_skel = False
                    for line in yf:
                        stripped = line.rstrip()
                        if stripped == f"{skel_name}:":
                            in_skel = True
                        elif in_skel and stripped.strip().startswith("offset:"):
                            val = stripped.split(":", 1)[1].strip()
                            skel_offset = int(val, 16) if val.startswith("0x") else int(val)
                            break
                        elif in_skel and stripped and not stripped.startswith(" "):
                            break
                if skel_offset is not None:
                    entry = dict(entry)
                    entry["offset"] = f"0x{skel_offset - (limb_count * 4):X}"
                    del entry["_skel_name"]
                    del entry["_limb_count"]
                    normal_entries.append(entry)
            elif "segments" in entry:
                set_entries.append(entry)
            elif "offset" in entry:
                normal_entries.append(entry)

        # Append normal entries to parent YAML
        added = add_undeclared_to_yaml(yaml_path, normal_entries)
        if added > 0:
            total_added += added
            files_updated += 1

        # Create separate YAML files for Set_ entries
        if set_entries:
            parent_config = _read_yaml_config(yaml_path)
            parent_dir = os.path.dirname(yaml_path)
            # If parent has no directory config (scenes), derive from file_key
            if parent_config["directory"] is None:
                parent_config["directory"] = file_key
            # Add parent YAML as external file so Set_ can reference parent's assets
            # External file paths are relative to the top-level yaml_dir parent
            # e.g. "pal_gc/scenes/nonmq/bdan_room_11.yml"
            yaml_dir_parent = os.path.basename(yaml_dir)
            parent_rel = os.path.relpath(yaml_path, os.path.dirname(yaml_dir))
            set_config = dict(parent_config)
            set_config["external_files"] = list(parent_config["external_files"])
            if parent_rel not in set_config["external_files"]:
                set_config["external_files"].insert(0, parent_rel)
            # Track Set_ files to add as external files of the parent
            set_ext_files = []
            for entry in set_entries:
                set_yaml_path = os.path.join(parent_dir, f"{entry['name']}.yml")
                _write_set_yaml(set_yaml_path, entry, set_config)
                total_added += 1
                files_updated += 1
                # Record for parent external_files update
                set_rel = os.path.relpath(set_yaml_path, os.path.dirname(yaml_dir))
                set_ext_files.append(set_rel)

            # Add Set_ files as external files of the parent so GetNodeByAddr can find them
            if set_ext_files:
                _append_external_files(yaml_path, set_ext_files)

    return total_added, files_updated


def prune_missing_external_files(out_dir):
    """Drop external_files entries whose target YAML does not exist.

    Paths are relative to the srcdir root (one level above out_dir), e.g.
    "ntsc_u/objects/gameplay_keep.yml".
    """
    src_root = os.path.dirname(os.path.normpath(out_dir))
    removed = 0
    for dirpath, _, filenames in os.walk(out_dir):
        for fn in filenames:
            if not fn.endswith(".yml"):
                continue
            path = os.path.join(dirpath, fn)
            with open(path) as f:
                lines = f.readlines()

            out = []
            in_ext = False
            for line in lines:
                if line.strip() == "external_files:":
                    in_ext = True
                    out.append(line)
                    continue
                if in_ext:
                    m = re.match(r"^\s+- (.+)$", line)
                    if m:
                        if not os.path.isfile(os.path.join(src_root, m.group(1).strip())):
                            removed += 1
                            continue
                        out.append(line)
                        continue
                    in_ext = False
                out.append(line)

            # An external_files: header with nothing left under it is invalid YAML.
            cleaned = []
            for i, line in enumerate(out):
                if line.strip() == "external_files:":
                    nxt = out[i + 1] if i + 1 < len(out) else ""
                    if not re.match(r"^\s+- ", nxt):
                        continue
                cleaned.append(line)

            if cleaned != lines:
                with open(path, "w") as f:
                    f.writelines(cleaned)
    return removed


def main():
    parser = argparse.ArgumentParser(description="Convert 2ship/ZAPD MM XML to Torch YAML")
    parser.add_argument("--xml-dir", required=True, help="Path to XML directory (e.g. 2ship/mm/assets/xml/N64_US)")
    parser.add_argument("--dma-json", required=True, help="Path to DMA table JSON")
    parser.add_argument("--out-dir", required=True, help="Output YAML directory")
    parser.add_argument("--supplemental-json", help="Path to supplemental JSON from generate_supplemental.py")
    parser.add_argument("--types", help="Comma-separated list of XML types to convert (default: all)")
    args = parser.parse_args()

    with open(args.dma_json) as f:
        dma_table = json.load(f)

    allowed_types = set(args.types.split(",")) if args.types else None

    # Auto-include dependency types, but only the ones the request actually needs.
    # Pulling in all of them unconditionally means a --types Texture run also emits
    # Mtx/Limb/PlayerAnimation, whose MM factories do not exist yet, and torch
    # aborts on the first one.
    if allowed_types:
        deps = {
            # DLists reference textures by pointer; without the Texture
            # declarations torch cannot resolve them into OTR hash references and
            # emits the raw command instead, so every such DList mismatches.
            "DList": {"Array", "Vtx", "Mtx", "Texture"},
            "Skeleton": {"Limb"},
            "PlayerAnimationData": {"PlayerAnimation"},
        }
        for requested, extra in deps.items():
            if requested in allowed_types:
                allowed_types.update(extra)

    # Step 1: Convert XML to YAML
    total_files = 0
    total_assets = 0

    for dirpath, _, filenames in sorted(os.walk(args.xml_dir)):
        for fn in sorted(filenames):
            if not fn.endswith(".xml"):
                continue
            xml_path = os.path.join(dirpath, fn)
            xml_rel_path = os.path.relpath(xml_path, args.xml_dir)
            files, assets = process_xml(xml_path, xml_rel_path, dma_table, args.out_dir, allowed_types, xml_dir=args.xml_dir)
            total_files += files
            total_assets += assets

    print(f"Wrote {total_files} YAML files with {total_assets} assets")

    if UNSUPPORTED_ARRAY_KINDS:
        detail = ", ".join(f"{k}x{v}" for k, v in sorted(UNSUPPORTED_ARRAY_KINDS.items()))
        print(f"Skipped {sum(UNSUPPORTED_ARRAY_KINDS.values())} arrays of unsupported "
              f"element kinds ({detail}) -- no Torch array factory for these yet")

    # A --types run generates only some of the YAMLs, so external_files can point
    # at files that were never written and torch aborts with YAML::BadFile. Drop
    # those references. On a full run nothing should dangle, so leave them be --
    # a dangling reference there is a real bug worth seeing.
    if allowed_types:
        pruned = prune_missing_external_files(args.out_dir)
        if pruned:
            print(f"Pruned {pruned} external_files references to ungenerated YAMLs")

    # Step 2: Add supplemental assets (consolidated JSON with YAML-path keys)
    if args.supplemental_json:
        supp_added, supp_files = add_supplemental_from_json(args.supplemental_json, args.out_dir)
        print(f"Added {supp_added} supplemental assets to {supp_files} YAML files")
    else:
        print("Skipping supplemental injection (no --supplemental-json provided)")


if __name__ == "__main__":
    main()
