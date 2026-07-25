#!/usr/bin/env bash
# Run the full ROM matrix against a given torch binary.
#
#   TORCH_BIN=<binary> tools/matrix.sh <label>
#   TORCH_BIN=<binary> tools/matrix.sh --pair <romA> <romB> <label>
#
# Every ROM dump in roms/ is mapped to its version directory via its SHA1 in
# assets/yml/config.yml -- the same lookup torch itself does -- so adding a dump
# needs no change here.
#
# Results land in logs/matrix-<label>/<rom>.log; a PASS/FAIL table is printed and
# the exit status is non-zero if any target failed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TORCH_BIN="${TORCH_BIN:-$ROOT/torch/build/torch}"
if [[ ! -x "$TORCH_BIN" ]]; then
    echo "ERROR: torch binary not found or not executable: $TORCH_BIN" >&2
    exit 1
fi
export TORCH_BIN

PAIR_MODE=0
if [[ "${1:-}" == "--pair" ]]; then
    PAIR_MODE=1
    PAIR_A="$2"; PAIR_B="$3"; shift 3
fi

LABEL="${1:-run}"
LOG_DIR="$ROOT/logs/matrix-$LABEL"
mkdir -p "$LOG_DIR"

# rom basename -> version dir, via SHA1 lookup in config.yml
version_for() {
    local sha
    sha="$(sha1sum "$1" | cut -d' ' -f1)"
    python3 - "$sha" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open("assets/yml/config.yml"))
entry = cfg.get(sys.argv[1].lower())
print(entry["path"] if entry else "")
PY
}

echo "torch:  $TORCH_BIN"
echo "label:  $LABEL"
echo "logs:   $LOG_DIR"
echo

if [[ $PAIR_MODE -eq 1 ]]; then
    # Two extractions in ONE process (Gate A2). test_assets.py cannot drive this
    # -- it execs the binary once per ROM -- so call the driver directly and
    # compare each output with check.sh.
    DEST_A="$(mktemp -d)"; DEST_B="$(mktemp -d)"
    trap 'rm -rf "$DEST_A" "$DEST_B"' EXIT
    echo "== pair run: $PAIR_A then $PAIR_B in one process =="
    "$TORCH_BIN" o2r -s assets/yml -d "$DEST_A" -u 9.2.3 "roms/$PAIR_A.z64" \
                 --second "roms/$PAIR_B.z64" "$DEST_B" >"$LOG_DIR/pair.log" 2>&1
    rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FAIL driver exited $rc -- see $LOG_DIR/pair.log"
        exit 1
    fi
    fails=0
    for pair in "$DEST_A:$PAIR_A" "$DEST_B:$PAIR_B"; do
        dest="${pair%%:*}"; rom="${pair##*:}"
        # config.yml names the output per ROM (oot-mq.o2r for master quest)
        cp "$dest"/*.o2r o2r/torch.o2r
        cp "o2r/$rom.o2r"  o2r/reference.o2r
        if ./check.sh >"$LOG_DIR/$rom.log" 2>&1; then
            printf '  %-28s PASS\n' "$rom"
        else
            printf '  %-28s FAIL\n' "$rom"; fails=$((fails + 1))
        fi
    done
    exit $((fails > 0))
fi

FAILED=()
declare -A RESULT
ROMS=(roms/*.z64)

for rom in "${ROMS[@]}"; do
    base="$(basename "$rom" .z64)"
    ver="$(version_for "$rom")"
    if [[ -z "$ver" ]]; then
        printf '%-32s %-24s SKIP (sha1 not in config.yml)\n' "$base" "-"
        RESULT["$base"]="SKIP"
        continue
    fi
    log="$LOG_DIR/$base.log"
    if python3 tools/test_assets.py "$rom" --rom-version "$ver" --failures-only >"$log" 2>&1; then
        RESULT["$base"]="PASS"
    else
        RESULT["$base"]="FAIL"
        FAILED+=("$base")
    fi
    summary="$(grep -E '^[0-9]+ passed,' "$log" | tail -1)"
    printf '%-32s %-24s %-4s  %s\n' "$base" "$ver" "${RESULT[$base]}" "$summary"
done

echo
echo "=== $LABEL ==="
pass=0; fail=0
for k in "${!RESULT[@]}"; do
    [[ "${RESULT[$k]}" == "PASS" ]] && pass=$((pass + 1))
    [[ "${RESULT[$k]}" == "FAIL" ]] && fail=$((fail + 1))
done
echo "$pass passed, $fail failed, of ${#ROMS[@]} ROM dumps"
if [[ $fail -gt 0 ]]; then
    printf 'failed: %s\n' "${FAILED[*]}"
    exit 1
fi
