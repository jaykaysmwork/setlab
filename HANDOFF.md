# SetLab — 코드 리뷰 수정 작업 인수인계 (Handoff)

- 작성: 2026-06-09 (Claude Code 세션)
- 브랜치: **`code-review-fixes`** (origin = github.com/jaykaysmwork/setlab 에 푸시됨)

## 다른 컴퓨터에서 이어받기

```bash
git fetch origin
git checkout code-review-fixes
# 확인 후 main으로 합치려면:
#   git checkout main && git merge code-review-fixes

# Python (venv는 커밋 안 됨 — 재생성)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # ⚠️ 11번(아래) 먼저 반영하면 더 좋음
# 웹
cd web && npm install
```

> `.claude/` 는 커밋에서 제외(.gitignore에 추가함). 로컬 도구 설정이며, 특히
> `.claude/hooks/gpt_review.py` 는 파일 편집 시 git diff를 OpenAI로 전송하는 훅이라
> 의도적으로 빼뒀다. 필요하면 새 머신에서 재설정.

## 개요

이 브랜치는 SetLab 전체 멀티에이전트 코드리뷰에서 도출한 우선순위 수정 로드맵(1~20)을
순서대로 적용 중인 WIP다. 세션 시작 시점에 이미 사용자의 미커밋 작업(`image_gen.py`,
`web_image_search.py`, `run.py`, 일부 web 컴포넌트 등)이 트리에 있었고 그 위에 리뷰
수정이 얹혔다. 이 커밋은 그 전체를 포함한다(`.claude/`, `.venv/`, `inzoi-test.mov` 제외).

---

## 진행 상태

### ✅ 완료 · 검증됨 (1~10)

| # | 내용 | 주요 파일 | 검증 |
|---|------|----------|------|
| 1 | 경로 탐색 가드(`/api/outputs`,`/api/web-refs`) | `server/main.py` | 인증 로직 10케이스 시뮬 |
| 2 | 선택적 토큰 인증 + 엔드포인트 하드닝 | `server/main.py`, `web/lib/api.ts`, `web/app/api/enhance-prompt/route.ts`, `web/components/FolderBrowser.tsx`, `.env.example` | 미들웨어 10케이스, `tsc` 0 |
| 3 | 회전 순서 XYZ 통일 + 공유 모듈 추출 | `setlab/rotation_math.py`(신규), `export_gltf.py`, `glb_rotation_bake.py` | `tests/test_rotation_math.py` 통과 |
| 4 | enhance SSE 줄바꿈 유실 | `server/main.py`, `web/lib/api.ts` | `"A\nB"` 보존 추적 |
| 5 | refine가 ground_material/environment 삭제 | `server/main.py`, `setlab/claude_client.py` | merge `{**existing,**raw}` |
| 6 | 빈 jobs 폴링 무한루프 | `setlab/rodin_client.py`, `setlab/material_enhance.py` | timeout-at-top |
| 7 | rodin_texture_only 멀티파트 bare 문자열 | `setlab/material_enhance.py` | `(None,value)` 튜플 |
| 8 | hdgen 0-이미지인데 'completed' | `server/main.py` | 반환값 `not any()` 가드 |
| 9 | job dict 동시성(중복 스폰) | `server/main.py` | `_jobs_lock` 6곳 원자화 |
| 10 | `_asset_urls.json` 경합/torn-read | `setlab/_asset_urls.py`(신규), `rodin_client.py`, `material_enhance.py` | 50스레드 0손실 실측 |

### ✅ 완료 (tsc/parse 통과 — Unreal/서버 런타임 미검증)

| # | 내용 | 파일 |
|---|------|------|
| 12 | 프론트 메시 캐시(`useGLTF.clear` + URL 버스트, 재생성/HD 경로) | `web/components/ImportedMeshModule.tsx`, `web/app/page.tsx` |
| 13 | UE 바닥이 HD 스케일로 Plane 교체되던 버그(plane 규약으로) | `scripts/ue_set_watcher.py` |
| 14a | DirectionalLight 색 이중 적용(use_temperature만 사용) | `scripts/ue_set_watcher.py` |

### ⬜ 남은 작업 (여기서부터 이어서)

**11 — 의존성 교정 `requirements.txt` [미착수, 5분]**
- `duckduckgo-search>=6.0.0` → **`ddgs>=9.0.0`** (코드는 `from ddgs import DDGS`)
- 추가: `anthropic>=0.40.0`, `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `python-dotenv>=1.0`
- (선택) 미사용 제거: `aiohttp`, `lumaapi`

**14 나머지 — 작은 정확성 묶음 [미착수, 파일별 병렬 가능]**
- `setlab/modify_client.py` `classify()`: `message.stop_reason == "max_tokens"` 가드 추가(claude_client 패턴 그대로)
- `setlab/llm_json.py` `extract_json_object`: 한 줄 ```` ```{...}``` ```` 펜스에서 `split("\n",1)[1]` IndexError → `nl=text.find("\n"); text=text[nl+1:] if nl!=-1 else text[3:]`
- `setlab/export_usda.py`: `m.id`/`m.asset`를 `re.sub(r'[^A-Za-z0-9_]','_', ...)`로 새니타이즈(따옴표/개행이 USDA prim 파손)
- `setlab/rodin_client.py` `_download_glb` + `setlab/material_enhance.py`: 저장 전 GLB 매직바이트 `content[:4]==b"glTF"` 검증, 아니면 RuntimeError

**15~20 — 정리(Phase 3) [미착수]**
- 15 Tripo 데드코드 삭제: `setlab/mesh_client.py`, `setlab/hd_mesh_client.py`(import 시 ImportError 지뢰)
- 16 회전수학 단일화 → **#3에서 이미 완료**(`rotation_math.py`)
- 17 `scripts/unreal_spawn_from_spec.py` 삭제(좌표 틀린 데드코드, 워처가 대체)
- 18 모델 ID 상수화(`claude-sonnet-4-6`/`claude-haiku-4-5-20251001` 12곳 하드코딩 → 상수)
- 19 죽은 `*.bin` 복사 루프(`server/main.py:631`, 셸 3종) + `api_refine`의 미사용 import 제거
- 20 성능: `frameloop="demand"`(Viewer3D/VRViewer), VRViewer 매-tick 재클론 제거, glTF 큐브 공유, Anthropic 클라이언트 풀링

---

## 환경 · 검증 메모

- **회전 테스트**: `python3 tests/test_rotation_math.py` (순수 stdlib, 의존성 불필요)
- **웹 타입체크**: `web/node_modules/.bin/tsc -p web/tsconfig.json --noEmit`
- ⚠️ **서버 런타임은 어시스턴트 샌드박스에서 부팅 못 했음**: 이 `.venv`의 `pydantic_core`
  네이티브 `.so`가 macOS 코드서명 정책으로 로드 차단됨(샌드박스 한정; 일반 실행은 정상).
  그래서 `server/main.py` 변경은 구문·로직 검증만 됨 → **새 머신에서 `uvicorn`으로 스모크 테스트 권장.**
- **인증 켜기(2번)**: `.env`에 `SETLAB_API_TOKEN=<랜덤>` + `NEXT_PUBLIC_SETLAB_API_TOKEN=<같은 값>`
  (둘 다 비우면 기존 로컬 동작 그대로). browse 제한은 옵션 `SETLAB_BROWSE_ROOTS`(`:` 구분).
- **Unreal 변경(13/14a)**: `import unreal` 필요라 여기서 실행 불가 — UE 에디터에서 확인 필요.

## 권장 순서
새 머신에서 **11(requirements)** → **14 나머지(병렬)** → **15~20 정리**. 각 항목의 정확한
file:line·수정안은 위에 명시. 막히면 세션의 코드리뷰 보고서(채팅) 근거 참조.
