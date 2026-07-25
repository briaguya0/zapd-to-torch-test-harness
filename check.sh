#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
O2R_DIR="$SCRIPT_DIR/o2r"
REFERENCE="$O2R_DIR/reference.o2r"
TORCH="$O2R_DIR/torch.o2r"

if [[ ! -f "$REFERENCE" ]]; then
    echo "ERROR: reference.o2r not found at $REFERENCE"
    exit 1
fi

if [[ ! -f "$TORCH" ]]; then
    echo "ERROR: torch.o2r not found at $TORCH"
    exit 1
fi

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

REF_DIR="$WORK_DIR/reference"
TORCH_DIR="$WORK_DIR/torch"
mkdir -p "$REF_DIR" "$TORCH_DIR"

# -o (overwrite, never prompt) is REQUIRED, not just tidiness: torch writes 25
# entries under a path that already exists in the archive -- 24 duplicated names in
# pal_mq, all copies byte-identical. Without -o, unzip stops to ask "replace?",
# reads EOF from a non-interactive stdin, and exits non-zero into set -e, so the
# comparison below never runs at all. Benign for the game (libultraship indexes by
# CRC64 of the path, so repeat inserts are idempotent); tracked upstream as item 5
# of HarbourMasters/Torch#233. Counted and reported below so it can't go quiet.
echo "Extracting reference.o2r..."
unzip -qo "$REFERENCE" -d "$REF_DIR"

echo "Extracting torch.o2r..."
unzip -qo "$TORCH" -d "$TORCH_DIR"

echo "Building file lists..."
(cd "$REF_DIR" && find . -type f | sort) > "$WORK_DIR/reference_files.txt"
(cd "$TORCH_DIR" && find . -type f | sort) > "$WORK_DIR/torch_files.txt"

# Hash files as "hash\tfile" for easier joining
echo "Hashing reference files..."
(cd "$REF_DIR" && while read -r f; do
    printf '%s\t%s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
done < "$WORK_DIR/reference_files.txt") > "$WORK_DIR/reference_hashes.txt"

echo "Hashing torch files..."
(cd "$TORCH_DIR" && while read -r f; do
    printf '%s\t%s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
done < "$WORK_DIR/torch_files.txt") > "$WORK_DIR/torch_hashes.txt"

echo ""
echo "=== Results ==="

REF_COUNT=$(wc -l < "$WORK_DIR/reference_files.txt")
TORCH_COUNT=$(wc -l < "$WORK_DIR/torch_files.txt")
echo "Reference files: $REF_COUNT"
echo "Torch files:     $TORCH_COUNT"

# Duplicate archive entries collapse onto one path once extracted, so the file-by-file
# comparison below structurally cannot see them. Report them explicitly. Informational:
# every copy observed so far is byte-identical to its siblings (Torch#233 item 5).
dup_names() { zipinfo -1 "$1" | sort | uniq -d | wc -l; }
REF_DUPS=$(dup_names "$REFERENCE")
TORCH_DUPS=$(dup_names "$TORCH")
echo "Duplicate entry names (reference / torch): $REF_DUPS / $TORCH_DUPS"

# Find missing and extra files
comm -23 "$WORK_DIR/reference_files.txt" "$WORK_DIR/torch_files.txt" > "$WORK_DIR/missing.txt"
comm -13 "$WORK_DIR/reference_files.txt" "$WORK_DIR/torch_files.txt" > "$WORK_DIR/extra.txt"

MISSING_COUNT=$(wc -l < "$WORK_DIR/missing.txt")
EXTRA_COUNT=$(wc -l < "$WORK_DIR/extra.txt")

# Compare hashes for common files
# Hash files are "hash\tfile", so build a lookup from file->hash for each, then compare
awk -F'\t' 'NR==FNR { ref[$2]=$1; next } ($2 in ref) && ref[$2] != $1 { print $2 }' \
    "$WORK_DIR/reference_hashes.txt" "$WORK_DIR/torch_hashes.txt" > "$WORK_DIR/mismatched.txt"
MISMATCH_COUNT=$(wc -l < "$WORK_DIR/mismatched.txt")

COMMON_COUNT=$(comm -12 "$WORK_DIR/reference_files.txt" "$WORK_DIR/torch_files.txt" | wc -l)
MATCH_COUNT=$((COMMON_COUNT - MISMATCH_COUNT))

echo "Missing (in reference, not in torch): $MISSING_COUNT"
echo "Extra (in torch, not in reference):   $EXTRA_COUNT"
echo "Matching:                             $MATCH_COUNT"
echo "Mismatched content:                   $MISMATCH_COUNT"

FAIL=0

if [[ $MISSING_COUNT -gt 0 ]]; then
    FAIL=1
    echo ""
    echo "=== Missing files (first 50) ==="
    head -50 "$WORK_DIR/missing.txt"
fi

if [[ $EXTRA_COUNT -gt 0 ]]; then
    FAIL=1
    echo ""
    echo "=== Extra files (first 50) ==="
    head -50 "$WORK_DIR/extra.txt"
fi

if [[ $MISMATCH_COUNT -gt 0 ]]; then
    FAIL=1
    echo ""
    echo "=== Mismatched files (first 50) ==="
    head -50 "$WORK_DIR/mismatched.txt"
fi

if [[ $FAIL -eq 0 ]]; then
    echo ""
    echo "PASS: All $MATCH_COUNT files match!"
else
    echo ""
    echo "FAIL"
    exit 1
fi
