#!/usr/bin/env bash
# OoT regression gate.
#
# This branch is MM-only and deleted the OoT manifests and config (commit a20b505),
# but torch's OoT factories are shared code that MM work keeps touching. So the gate
# recovers what it needs from git history instead of requiring a Shipwright build:
#
#   - manifests/<version>.json  and  assets/yml/config.yml   from a20b505^
#   - assets/yml/<version>/     from the working tree (gitignored, produced by the
#                               old OoT pipeline or cloned from briaguya0/soh-asset-yml)
#   - roms/oot/<version>_*.z64  local, never committed
#
#   tools/oot_gate.sh              # default pal_gc
#   tools/oot_gate.sh ntsc_u_gc    # another version
#
# Exits non-zero on any mismatch. Run after every change to shared torch code.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-pal_gc}"
PRE_DELETE_REV="${OOT_GATE_REV:-a20b505^}"

ROM="$(ls roms/oot/${VERSION}_*.z64 2>/dev/null | head -1)"
if [[ -z "$ROM" ]]; then
    echo "ERROR: no ROM for $VERSION in roms/oot/" >&2
    exit 1
fi
if [[ ! -d "assets/yml/$VERSION" ]]; then
    echo "ERROR: no OoT YAMLs at assets/yml/$VERSION" >&2
    echo "       clone them: git clone git@github.com:briaguya0/soh-asset-yml.git" >&2
    exit 1
fi

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# Recover the OoT config and manifest from before this branch dropped them
git show "${PRE_DELETE_REV}:assets/yml/config.yml"        > "$WORK/config.yml"  2>/dev/null || {
    echo "ERROR: could not recover config.yml from ${PRE_DELETE_REV}" >&2; exit 1; }
git show "${PRE_DELETE_REV}:manifests/${VERSION}.json"    > "$WORK/manifest.json" 2>/dev/null || {
    echo "ERROR: could not recover manifests/${VERSION}.json from ${PRE_DELETE_REV}" >&2; exit 1; }

# torch's --src root needs config.yml alongside the version directory
SRC="$WORK/src"; mkdir -p "$SRC"
cp "$WORK/config.yml" "$SRC/config.yml"
ln -s "$ROOT/assets/yml/$VERSION" "$SRC/$VERSION"

OUT="$WORK/out"; mkdir -p "$OUT"
echo "OoT gate: $VERSION  ($(basename "$ROM"))"

# -u 9.2.3 is the portVersion the reference manifests were built with
if command -v distrobox >/dev/null 2>&1 && [[ -z "${IN_DISTROBOX:-}" ]]; then
    distrobox enter soh -- bash -lc \
        "cd '$ROOT' && torch/build/torch o2r -s '$SRC' -d '$OUT' -u 9.2.3 '$ROM'" > "$WORK/torch.log" 2>&1
else
    torch/build/torch o2r -s "$SRC" -d "$OUT" -u 9.2.3 "$ROM" > "$WORK/torch.log" 2>&1
fi
rc=$?
ARCHIVE="$(find "$OUT" -maxdepth 1 -name '*.o2r' | head -1)"
if [[ $rc -ne 0 || -z "$ARCHIVE" ]]; then
    echo "FAIL: torch exited $rc"
    tail -20 "$WORK/torch.log"
    exit 1
fi

python3 - "$WORK/manifest.json" "$ARCHIVE" <<'PY'
import hashlib, json, sys, zipfile
ref = json.load(open(sys.argv[1]))
z = zipfile.ZipFile(sys.argv[2])
gen = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}

missing = sorted(set(ref) - set(gen))
extra   = sorted(set(gen) - set(ref))
bad     = sorted(k for k in set(ref) & set(gen) if ref[k] != gen[k])

print(f"  reference {len(ref)}   generated {len(gen)}")
print(f"  matching  {len(set(ref) & set(gen)) - len(bad)}")
print(f"  mismatched {len(bad)}   not generated {len(missing)}   extra {len(extra)}")
for label, items in (("MISMATCH", bad), ("NOT GENERATED", missing), ("EXTRA", extra)):
    for k in items[:10]:
        print(f"    {label} {k}")
    if len(items) > 10:
        print(f"    ... and {len(items) - 10} more {label}")

if bad or missing or extra:
    print("\nFAIL: OoT output changed")
    sys.exit(1)
print("\nPASS: OoT output unchanged")
PY
