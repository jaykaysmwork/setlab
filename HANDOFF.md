# SetLab — 작업 인수인계 (Handoff)

- 갱신: **2026-06-09**
- 브랜치: **`main`** — 모든 작업이 머지·푸시 완료 상태. (`code-review-fixes` 브랜치는 머지 후 삭제됨)
- origin: `github.com/jaykaysmwork/setlab` (Private)

> 한 줄 현황: 코드리뷰 수정(phase 1~20) 전부 main 반영 완료. 이미지 검색을 **Serper.dev**로 교체하고, **프롬프트의 제약을 그대로 따르는** 검색 쿼리 빌더를 붙였다. 런타임 코어(서버·Claude·검색·레이아웃 출력)는 검증됨. 무거운 3D(Rodin)·환경(Marble)·브라우저 UI는 미실행(비용/UI 필요).

---

## 🚀 다른 컴퓨터에서 이어받기

### 1) 코드
```bash
git clone https://github.com/jaykaysmwork/setlab.git   # 처음이면
# 또는 기존 클론이면:  git checkout main && git pull origin main
cd setlab
```

### 2) Python (venv는 **머신마다 새로 생성** — 복사·이동 금지)
```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r server/requirements.txt   # 둘 다 설치
```

### 3) 웹
```bash
cd web && npm install && cd ..
```

### 4) `.env` (gitignore — 새 머신엔 없으므로 직접 마련)
**가장 쉬운 방법**: 원본 머신의 `.env`를 **안전한 경로로 직접 복사**(AirDrop/USB/scp 등 — git·이메일·슬랙 금지). 없으면 아래 키를 새로 채운다:

| 변수 | 용도 | 필수도 | 발급처 / 값 |
|------|------|--------|------------|
| `ANTHROPIC_API_KEY` | Claude (레이아웃·Enhance·수정·**검색 쿼리 빌더**) | ⭐ 필수 | console.anthropic.com |
| `SERPER_API_KEY` | 이미지 검색 (Serper Google Images) | 검색 쓸 때 | serper.dev (무료 2,500, **카드 불필요**) |
| `IMAGE_SEARCH_BACKEND` | 검색 백엔드 | | `serper` (미설정 시 `duckduckgo` 기본) |
| `RODIN_API_KEY` *(= `HYPER3D_API_KEY`)* | 3D 메시/HD/머티리얼 | 3D 쓸 때 | developer.hyper3d.ai |
| `GOOGLE_API_KEY` | Gemini 이미지 **생성** | 이미지생성 쓸 때 | Google AI Studio |
| `GOOGLE_IMAGE_MODEL` | Gemini 모델 | | `gemini-3.1-flash-image` (flash·저렴) |
| `WORLDLABS_API_KEY` | Marble 환경 생성 | 선택 | worldlabs.ai *(이전 노출키는 폐기됨 — 쓰려면 재발급)* |
| `BACKEND` / `MODEL` | LLM 백엔드/모델 | | `claude` / `claude-sonnet-4-6` |

**비용 제어 (현재 설정):**
```
NEXT_PUBLIC_AUTO_PIPELINE_AFTER_GENERATE=false   # Generate = 레이아웃만 (초·저비용)
NEXT_PUBLIC_AUTO_STUDIO_COMPLETE=                # 머티리얼/Deploy/Marble 자동 끔
```
메시·HD·머티리얼·환경은 **버튼으로 수동** 실행. (`mesh+hd` / `full` 로 바꾸면 Generate 한 번에 전부 자동 = 느리고 비쌈)

### 5) 실행 (터미널 2개)
```bash
# 터미널 A — 서버
source .venv/bin/activate && cd server && uvicorn main:app --reload --port 8000
# 터미널 B — 웹
cd web && npm run dev      # http://localhost:3000
```

---

## 🩹 환경 셋업에서 실제로 겪은 함정 (꼭 읽기)

| 증상 | 원인 | 해결 |
|------|------|------|
| `command not found: pip`/`python` (venv 활성화해도) | venv가 깨졌거나 다른 머신에서 복사됨 | `rm -rf .venv` 후 **재생성** (위 2번) |
| `command not found: uvicorn` | venv 비활성 (프롬프트에 `(.venv)` 없음) | `source .venv/bin/activate` |
| 웹 `library load disallowed by system policy` (`@next/swc-darwin-arm64`) | `node_modules`가 브라우저(Chrome) 다운로드라 **격리(quarantine)** 플래그 | `xattr -dr com.apple.quarantine web/node_modules` |
| `[Errno 48] Address already in use` (:8000) | 이전 uvicorn 잔존 | `lsof -ti:8000 \| xargs kill -9` |
| `localhost:3000 refused` | 웹 dev 서버 안 켜짐 | `cd web && npm run dev` |

---

## 📦 이번 세션에 한 일 (전부 main 반영·푸시)

1. **코드리뷰 phase 1~20** → main 머지 (아래 "이력" 참고)
2. **README** 영어 프로젝트 소개로 재작성 (Mermaid 다이어그램 포함, 외부 독자용)
3. **보안**: `.env.example`에 커밋돼 있던 실제 키(FLUX·WORLDLABS) 제거 + **해당 키 폐기**
4. **이미지 검색 대수술**:
   - Google Custom Search 시도 → **신규 고객에게 폐쇄됨(영구 403)** 확인 → 포기. (이를 위해 만든 GCP 프로젝트 `setlab-studio`는 **삭제함**)
   - **Serper.dev**로 안착: 안정적 Google Images, 카드 불필요, `IMAGE_SEARCH_BACKEND=serper`. **DuckDuckGo 폴백** 유지.
   - **프롬프트 인지 검색**: `setlab/web_image_search.py`의 `build_image_query()`(Claude Haiku)가 프롬프트의 제약을 **그대로** 반영 — "내부만"→`interior`, "gif 제외"→`exclude_animated`. 하드코딩 기본값 0.
5. **비용 절감**: auto-pipeline off, Gemini 이미지 모델을 `gemini-3.1-flash-image`(flash)로 변경

---

## 🧠 검증 상태

**🟢 실제로 돌려서 확인됨**
- 서버 부팅 · Claude(Enhance + 커넥션 풀링) · `/api/config`
- Generate(mock) → 레이아웃 → `set.gltf`+`set.usda` 생성 → `/api/outputs` 서빙
- **Serper 이미지 검색**(실 호출 200, 진짜 이미지 URL) · **프롬프트 빌더**(내부/ gif제외 반영)
- web `tsc --noEmit` 0 에러 · Python `py_compile` · `tests/test_rotation_math.py`

**🟡 아직 미실행 (비용/UI 필요 — 고장 아님)**
- Rodin **3D 메시 / HD / 머티리얼** (유료, 분 단위) · **Marble 환경** (유료) · **UE Deploy**(에디터 필요) · 브라우저 fog/VR 시각 확인

---

## ⏭️ 다음에 할 것 · 주의

- [ ] **프롬프트 인지 검색 브라우저 재검증**: "Beverly Center 내부... 내부사진만, gif 제외" Enhance → 헤더가 `Beverly Center interior ...`로 깔끔, 외부/gif 안 섞이는지
- [ ] Rodin 3D 메시 1개 + Marble 1회 **소액 런타임 스모크** (auto off 상태라 버튼으로 개별 실행)
- [ ] (선택) Unreal 에디터에서 바닥 Plane·DirectionalLight(13/14a) 확인
- ⚠️ **Google Custom Search 재시도 금지** — 신규 고객 폐쇄라 어떤 새 프로젝트로도 영구 403. (Serper로 끝.)
- ⚠️ **서버 런타임은 어시스턴트 샌드박스에서 부팅 불가**(pydantic_core `.so` 코드서명 차단) — 본인 터미널에선 정상. 그래서 AI가 못 돌린 런타임은 위 🟡 항목.

---

## 📜 코드리뷰 로드맵 1~20 — 전부 main 반영 (이력 요약)

- **1~10** 보안·동시성·정확성: 경로탐색 가드, 토큰인증, 회전 XYZ 통일(`rotation_math.py`), SSE 줄바꿈, refine 키보존, 폴링 무한루프, 멀티파트 튜플, hdgen 0-이미지 가드, `_jobs_lock` 동시성, `_asset_urls.py` 원자화
- **11** 의존성: `ddgs` 교체, `anthropic`/`python-dotenv` 추가, 미사용 제거
- **12·13·14a** 프론트 메시 캐시버스트, UE 바닥 Plane, DirectionalLight 이중적용
- **14** 정확성 4종: modify_client max_tokens 가드, llm_json 단일라인 펜스 IndexError, export_usda prim 이름 새니타이즈(+유효성·중복제거), GLB 매직바이트 검증
- **15·17** 데드코드 삭제(mesh_client·hd_mesh_client·unreal_spawn_from_spec)
- **18** 모델ID 상수화(22곳 → `setlab/model_ids.py`·`web/lib/models.ts`)
- **19** 죽은 `*.bin` 루프 + 중복 import 제거
- **20** 성능: Viewer3D `frameloop=demand`+invalidate, VRViewer 클론 deps 축소, Anthropic 풀링. (VRViewer는 WASD 때문에 `always` 유지; 큐브공유는 부적합으로 스킵)

> `.claude/`는 gitignore(로컬 도구 설정). 프로젝트 로컬 gpt_review 훅은 경로 오타로 제거됨; 전역 `~/.claude` 훅이 대체.
