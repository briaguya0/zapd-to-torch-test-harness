#!/usr/bin/env bash
# Generate YAMLs for a set of XML types, extract with torch, and score against the
# reference manifest.
#
#   tools/score.sh                 # everything the converter emits
#   tools/score.sh Texture         # one type (plus its dependencies)
#   tools/score.sh DList,Skeleton  # several
#
# ROM_VERSION selects the target (default ntsc_u).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${ROM_VERSION:-ntsc_u}"
TYPES="${1:-}"
ROM="$(ls roms/mm/${VERSION}_*.z64 2>/dev/null | head -1)"
MANIFEST="manifests/${VERSION}.json"
XML_DIR="2ship/mm/assets/xml/N64_US"
# Stamped into the archive's portVersion file. 2ship's CMake project version;
# the reference reads 01 0005 0000 0000 (endianness byte + 5.0.0).
PORT_VERSION="${PORT_VERSION:-5.0.0}"

[[ -f "$ROM" ]]      || { echo "ERROR: no ROM for $VERSION in roms/mm/" >&2; exit 1; }
[[ -f "$MANIFEST" ]] || { echo "ERROR: no manifest at $MANIFEST" >&2; exit 1; }

OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT

gen_args=(--xml-dir "$XML_DIR" --dma-json "dma/${VERSION}.json" --out-dir "assets/yml/${VERSION}")
[[ -n "$TYPES" ]] && gen_args+=(--types "$TYPES")
# Supplemental only makes sense on a full run: it declares assets across all types,
# and injecting it into a --types subset reintroduces the types being excluded.
if [[ -z "$TYPES" && -f "supplemental/${VERSION}.json" ]]; then
    gen_args+=(--supplemental-json "supplemental/${VERSION}.json")
fi

rm -rf "assets/yml/${VERSION}"
python3 tools/zapd_to_torch.py "${gen_args[@]}" || exit 1

# torch needs the distrobox toolchain; run it there if available
if command -v distrobox >/dev/null 2>&1 && [[ -z "${IN_DISTROBOX:-}" ]]; then
    distrobox enter soh -- bash -lc "cd '$ROOT' && torch/build/torch o2r -s assets/yml -d '$OUT' -u $PORT_VERSION '$ROM'" \
        > "$OUT/torch.log" 2>&1
else
    torch/build/torch o2r -s assets/yml -d "$OUT" -u "$PORT_VERSION" "$ROM" > "$OUT/torch.log" 2>&1
fi
rc=$?
# [[ -f dir/*.o2r ]] does not glob, so locate the archive explicitly
ARCHIVE="$(find "$OUT" -maxdepth 1 -name '*.o2r' | head -1)"
if [[ $rc -ne 0 || -z "$ARCHIVE" ]]; then
    echo "torch failed (exit $rc):"
    tail -20 "$OUT/torch.log"
    exit 1
fi

python3 - "$MANIFEST" "$ARCHIVE" "assets/yml/${VERSION}" <<'PY'
import collections, hashlib, json, os, re, sys, zipfile

manifest_path, o2r_path, yml_dir = sys.argv[1], sys.argv[2], sys.argv[3]
ref = json.load(open(manifest_path))
z = zipfile.ZipFile(o2r_path)
gen = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}

# asset path -> declared type, so failures can be attributed to a type.
# Keyed by vpath where the YAML gives one (supplemental entries do) and by bare
# symbol otherwise; the archive path is matched against both.
types = {}
for dirpath, _, files in os.walk(yml_dir):
    for fn in files:
        if not fn.endswith(".yml"):
            continue
        cur = cur_type = None
        for line in open(os.path.join(dirpath, fn)):
            m = re.match(r"^(\S+):\s*$", line)
            if m and m.group(1) != ":config":
                cur, cur_type = m.group(1), None
                continue
            m = re.match(r"^\s+type:\s*(\S+)", line)
            if m and cur:
                cur_type = m.group(1)
                types[cur] = cur_type
                continue
            m = re.match(r"^\s+vpath:\s*(\S+)", line)
            if m and cur_type:
                types[m.group(1)] = cur_type


def type_of(asset_path):
    return types.get(asset_path) or types.get(os.path.basename(asset_path)) or "?"

p = f = extra = 0
fail_types = collections.Counter()
pass_types = collections.Counter()
for k, h in gen.items():
    t = type_of(k)
    if k not in ref:
        extra += 1
        fail_types[t + " (EXTRA)"] += 1
    elif ref[k] == h:
        p += 1
        pass_types[t] += 1
    else:
        f += 1
        fail_types[t] += 1

print(f"\n=== {os.path.basename(manifest_path)} ===")
print(f"generated {len(gen)} of {len(ref)} reference assets")
print(f"  PASS  {p}")
print(f"  FAIL  {f}")
print(f"  EXTRA {extra}")
if pass_types:
    print("\npassing by type:")
    for t, c in pass_types.most_common():
        print(f"  {c:6d}  {t}")
if fail_types:
    print("\nfailing by type:")
    for t, c in fail_types.most_common():
        print(f"  {c:6d}  {t}")
sys.exit(1 if (f or extra) else 0)
PY
