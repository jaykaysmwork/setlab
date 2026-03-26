#!/usr/bin/env bash
# One shot: prompt → setlab (Ollama) → out/live → copy into UE/Unity if env paths set.
#
# Usage:
#   export UE_PROJECT=/path/to/UnrealFolder      # folder containing .uproject
#   export UNITY_PROJECT=/path/to/UnityFolder    # folder containing Assets/
#   ./scripts/prompt_to_engines.sh "sci-fi corridor, 12m, two columns"
#
# Optional env:
#   OUT_DIR=out/live   BACKEND=ollama   MODEL=llama3.2

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROMPT="${1:?Usage: $0 'your set brief as one prompt'}"
shift || true

PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

OUT="${OUT_DIR:-out/live}"
"$PY" -m setlab.run --prompt "$PROMPT" --out "$OUT" \
  --backend "${BACKEND:-ollama}" --model "${MODEL:-llama3.2}"

UE="${UE_PROJECT:-}"
UY="${UNITY_PROJECT:-}"

if [[ -z "$UE" && -z "$UY" ]]; then
  echo ""
  echo "Wrote ${OUT}/set.gltf — set UE_PROJECT and/or UNITY_PROJECT to auto-copy, e.g.:"
  echo "  export UE_PROJECT=/path/to/MyUE"
  echo "  export UNITY_PROJECT=/path/to/MyUnity"
  echo "  $0 \"$PROMPT\""
  exit 0
fi

"$ROOT/scripts/deploy_set_gltf_to_projects.sh" "$ROOT/$OUT" "${UE:-}" "${UY:-}"
