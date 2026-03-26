#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# prompt_to_viewport.sh — 프롬프트 한 번 → Ollama → glTF → UE 프로젝트 복사
# ─────────────────────────────────────────────────────────────────────────────
# Unreal 에디터에서 ue_auto_reimport.py 가 돌고 있으면,
# 이 스크립트가 파일을 복사하는 순간 에디터가 자동으로 Reimport → 뷰포트에 반영.
#
# 사용법:
#   export UE_PROJECT="/path/to/UnrealProjectFolder"
#   ./scripts/prompt_to_viewport.sh "SF 복도 12m, 기둥 두 개, 저녁 조명"
#
# 또는 .env 파일을 두면 자동 로드:
#   echo 'UE_PROJECT=/path/to/project' > .env
#   ./scripts/prompt_to_viewport.sh "brif here"
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# .env 자동 로드
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PROMPT="${1:?Usage: $0 'your set brief'}"

PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

OUT="${OUT_DIR:-out/live}"
BACKEND="${BACKEND:-ollama}"
MODEL="${MODEL:-llama3.2}"

echo "── 1) Generating set from prompt (${BACKEND}/${MODEL}) ──"
"$PY" -m setlab.run --prompt "$PROMPT" --out "$OUT" \
  --backend "$BACKEND" --model "$MODEL"

echo ""

UE="${UE_PROJECT:-}"
if [[ -z "$UE" ]]; then
  echo "UE_PROJECT not set. glTF is at: ${OUT}/set.gltf"
  echo "Set UE_PROJECT to auto-copy, e.g.:"
  echo "  export UE_PROJECT=/path/to/MyUnrealProject"
  exit 0
fi

UE_ABS="$(cd "$UE" && pwd)"
DEST="${UE_ABS}/Content/Incoming"
mkdir -p "$DEST"

echo "── 2) Copying set.gltf → ${DEST} ──"
cp -f "${ROOT}/${OUT}/set.gltf" "$DEST/"

# .bin sidecar 복사 (있을 때만)
shopt -s nullglob
for f in "${ROOT}/${OUT}/set"*.bin "${ROOT}/${OUT}/"*.bin; do
  [[ -f "$f" ]] && cp -f "$f" "$DEST/"
done
shopt -u nullglob

echo ""
echo "── Done ──"
echo "If ue_auto_reimport.py is running in UE editor → viewport updates automatically."
echo "Otherwise: Content Browser → Incoming/set → Right-click → Reimport"
