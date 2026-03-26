#!/usr/bin/env bash
# Copy setlab glTF output into an Unreal project's Content folder, then Reimport in UE.
#
# Usage:
#   ./scripts/copy_set_gltf_to_unreal.sh /path/to/MyProject /path/to/3D-test/out/run
#
# After run: in Unreal Content Browser, select imported "set" (under Incoming/) → Reimport.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 /path/to/UnrealProject /path/to/setlab/out/dir" >&2
  exit 1
fi

UPROJECT_DIR="$(cd "$1" && pwd)"
OUT_DIR="$(cd "$2" && pwd)"
DEST="${UPROJECT_DIR}/Content/Incoming"

mkdir -p "$DEST"

if [[ ! -f "${OUT_DIR}/set.gltf" ]]; then
  echo "Missing ${OUT_DIR}/set.gltf" >&2
  exit 1
fi

cp -f "${OUT_DIR}/set.gltf" "$DEST/"
shopt -s nullglob
for f in "${OUT_DIR}/set"*.bin "${OUT_DIR}/"*.bin; do
  [[ -f "$f" ]] && cp -f "$f" "$DEST/" || true
done
shopt -u nullglob

echo "Copied into: $DEST"
echo "Next in Unreal: Content/Incoming → select set → Right-click → Reimport"
