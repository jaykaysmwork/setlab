#!/usr/bin/env bash
# Copy set.gltf (+ sibling .bin if any) into Unreal Content/Incoming and/or Unity Assets/Incoming.
#
# Usage:
#   ./scripts/deploy_set_gltf_to_projects.sh /path/to/setlab/out/dir [/path/to/UnrealUProject] [/path/to/UnityProject]
#
# Omit Unreal or Unity path with "" to skip that engine, e.g. only Unity:
#   ./scripts/deploy_set_gltf_to_projects.sh out/live "" /path/to/Unity

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 OUT_DIR [UE_PROJECT_DIR] [UNITY_PROJECT_DIR]" >&2
  exit 1
fi

OUT_DIR="$(cd "$1" && pwd)"
UE_DIR="${2:-}"
UNITY_DIR="${3:-}"

if [[ ! -f "${OUT_DIR}/set.gltf" ]]; then
  echo "Missing ${OUT_DIR}/set.gltf" >&2
  exit 1
fi

copy_sidecar_bins() {
  local dest="$1"
  shopt -s nullglob
  for f in "${OUT_DIR}/set"*.bin "${OUT_DIR}/"*.bin; do
    [[ -f "$f" ]] && cp -f "$f" "$dest/" || true
  done
  shopt -u nullglob
}

if [[ -n "$UE_DIR" ]]; then
  UE_ABS="$(cd "$UE_DIR" && pwd)"
  UDEST="${UE_ABS}/Content/Incoming"
  mkdir -p "$UDEST"
  cp -f "${OUT_DIR}/set.gltf" "$UDEST/"
  copy_sidecar_bins "$UDEST"
  echo "Unreal: copied to $UDEST → Reimport 'set' in Content Browser (or use auto script)."
fi

if [[ -n "$UNITY_DIR" ]]; then
  UY_ABS="$(cd "$UNITY_DIR" && pwd)"
  YDEST="${UY_ABS}/Assets/Incoming"
  mkdir -p "$YDEST"
  cp -f "${OUT_DIR}/set.gltf" "$YDEST/"
  copy_sidecar_bins "$YDEST"
  echo "Unity: copied to $YDEST → focus Editor to refresh or Reimport."
fi

if [[ -z "$UE_DIR" && -z "$UNITY_DIR" ]]; then
  echo "No UE or Unity path given; nothing copied." >&2
  exit 1
fi
