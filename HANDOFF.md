# SetLab — 코드 리뷰 수정 작업 인수인계 (Handoff)

- 작성: 2026-06-09 (Claude Code 세션) · 2차 세션: Phase 3(11·14 나머지·15~20) 완료
- 브랜치: **`code-review-fixes`** (origin = github.com/jaykaysmwork/setlab 에 푸시됨)

## 다른 컴퓨터에서 이어받기

```bash
git fetch origin
git checkout code-review-fixes
# 확인 후 main으로 합치려면:
#   git checkout main && git merge code-review-fixes

# Python (venv는 커밋 안 됨 — 재생성)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -r server/requirements.txt  # 11번 반영 완료
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

### ✅ 완료 (Phase 3 — 2026-06-09 2차 세션 · 코드검증 통과 / UI·서버 런타임 미검증)

> 검증: `py_compile`(변경 10파일) · `tests/test_rotation_math.py` · web `tsc --noEmit` **0 에러**.
> 아래 항목별 상세는 "할 일"이 아니라 "반영된 내용"이다.

**11 — 의존성 교정 `requirements.txt` [✅ — 핸드오프 대비 범위 축소]**
- 루트 `requirements.txt`: `duckduckgo-search` → **`ddgs>=9.0.0`**, **`anthropic>=0.40.0`·`python-dotenv>=1.0.0` 추가**, 미사용 `aiohttp`·`lumaapi` 제거
- `server/requirements.txt`: **`anthropic>=0.40.0` 추가**
- ⚠️ `fastapi`/`uvicorn`/`python-dotenv`는 **이미 `server/requirements.txt`에 있어** 중복 추가 안 함(핸드오프가 단일 파일 전제라 갭을 과장했었음)

**14 나머지 — 작은 정확성 묶음 [✅ 4종 모두 반영]** (아래 4개 그대로 적용; llm_json은 단일라인 펜스 포함 엣지케이스 5종 실행 검증)
- `setlab/modify_client.py` `classify()`: `message.stop_reason == "max_tokens"` 가드 추가(claude_client 패턴 그대로)
- `setlab/llm_json.py` `extract_json_object`: 한 줄 ```` ```{...}``` ```` 펜스에서 `split("\n",1)[1]` IndexError → `nl=text.find("\n"); text=text[nl+1:] if nl!=-1 else text[3:]`
- `setlab/export_usda.py`: prim 이름 `m.id`를 `re.sub(r'[^A-Za-z0-9_]','_',...)` + 유효성(숫자-시작/빈문자 방지)·중복제거로 새니타이즈(따옴표/개행/충돌이 USDA prim 파손; `m.asset`은 USDA에 미출력이라 제외)
- `setlab/rodin_client.py` `_download_glb` + `setlab/material_enhance.py`: 저장 전 GLB 매직바이트 `content[:4]==b"glTF"` 검증, 아니면 RuntimeError

**15~20 — 정리(Phase 3) [✅ 모두 반영]**
- 15 ✅ Tripo 데드코드 삭제: `setlab/mesh_client.py`, `setlab/hd_mesh_client.py` (importer 0 확인)
- 16 ✅ #3에서 이미 완료(`rotation_math.py`) — 변경 없음
- 17 ✅ `scripts/unreal_spawn_from_spec.py` 삭제 + `docs/PROJECT_SUMMARY.md`·`UNREAL_AUTO_PLACEMENT.md` 참조 갱신
- 18 ✅ 모델 ID 상수화: 실제 **22곳**(핸드오프 "12곳"은 과소) → 신규 `setlab/model_ids.py`·`web/lib/models.ts` (TS는 `:string` 명시로 협소화 방지)
- 19 ✅ 죽은 `*.bin` 복사 루프(실제 `server/main.py:654`) + api_refine의 **중복** import 1개(`orient_buildings_toward_floors`, `:567`에 동일본 존재) 제거
- 20 ✅ 성능 — 핸드오프와 다르게 판단한 부분 있음:
    - Viewer3D `frameloop="demand"` + 카메라핏 `invalidate()` 추가
    - VRViewer 클론 useMemo deps `[scene,moduleIds]`로 축소 + 명령형 가시성 effect ("매-tick 재클론"은 부정확: 원래도 메모이즈돼 있었음). **VRViewer는 `always` 유지** — WASD `useFrame` 연속 이동이라 demand면 멈춤
    - Anthropic 클라이언트 풀링: `claude_client.py`·`modify_client.py` 둘 다 timeout별 캐시
    - **큐브 공유 미적용**: `ImportedMeshModule:171`은 동적 크기 선택-아웃라인 박스(공유 불가), 유일 단위큐브는 Viewer3D Fallback(로딩 중 1회)뿐이라 실익 없음
- ➕ 로컬 훅 정리: 프로젝트 `.claude/settings.json`의 경로 오타(`projects`/단수 `project`) gpt_review 훅 제거(전역 `~/.claude` 훅이 대체)

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

## 남은 검증 (머지 전 새 머신에서)
로드맵 1~20은 **전부 반영**됐고 코드 검증(compile/tsc/test)은 통과. **단 UI·서버 런타임은 미검증**이라 `main` 머지 전에:
- `pip install -r requirements.txt && pip install -r server/requirements.txt` 후 `uvicorn`으로 부팅 + Claude 호출 1회(풀링 경로 스모크)
- 웹: Viewer3D `demand` 거동(궤도/줌·생성 중 메시 스트리밍·환경 변경 시 화면 갱신), VRViewer 메시표시·선택·WASD 이동
- Unreal(13/14a): UE 에디터에서 바닥 Plane·DirectionalLight 확인(기존 미검증분)
