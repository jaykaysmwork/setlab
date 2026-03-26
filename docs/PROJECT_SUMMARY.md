# SetLab — AI-Powered Virtual Production Background Generator

> 텍스트 프롬프트 하나로 영화 촬영용 3D 배경을 실시간 생성·수정하는 풀스택 파이프라인

## 프로젝트 개요

SetLab은 영화/드라마 촬영 현장(Virtual Production / XR Stage)에서 감독이 텍스트 프롬프트만으로 3D 배경을 즉시 생성하고, 촬영 중에도 실시간으로 수정할 수 있도록 설계된 시스템이다. AI 모델 조합을 통해 텍스트 → 3D 에셋 → Unreal Engine 배치까지 전 과정을 자동화한다.

**목표 품질:** 마블/디즈니 VP 스테이지에서 배경으로 즉시 투입 가능한 수준 (85-90% production-ready)

---

## 기술 스택

### Backend (Python)
| 역할 | 기술 |
|------|------|
| API 서버 | FastAPI (`server/main.py`) |
| LLM 오케스트레이션 | Claude Sonnet 4.6 via Anthropic SDK |
| 3D 생성 | Hyper3D **Rodin Gen-2** REST API (`setlab/rodin_client.py`) |
| 참조 이미지 생성 | FLUX 1.1 Pro via BFL REST API |
| 환경 생성 | World Labs Marble Plus REST API |
| 머티리얼 향상 | Hyper3D **rodin_texture_only** API (+ 참조 이미지: HD `front` 또는 FLUX) |
| 비동기 처리 | `asyncio` + `httpx` (3D 생성), `ThreadPoolExecutor` (이미지 생성) |
| JSON 파싱 | `json-repair` 라이브러리로 LLM 출력 견고하게 처리 |
| 데이터 모델 | Pydantic v2 |

### Frontend (TypeScript)
| 역할 | 기술 |
|------|------|
| 프레임워크 | Next.js 16.2, React 19 |
| 3D 뷰어 | Three.js + React Three Fiber + Drei |
| 스타일링 | Tailwind CSS v4 |
| VR 뷰어 | WebXR API |

### Unreal Engine 연동
| 역할 | 기술 |
|------|------|
| 에셋 임포트 | UE5 Python API (글TF/GLB 자동 임포트) |
| 배치 자동화 | `scripts/ue_set_watcher.py` (Slate tick callback으로 파일 감시) |
| 조명 시스템 | Lumen GI, Directional Light, Sky Atmosphere, Volumetric Clouds |
| 바닥 머티리얼 | Quixel Megascans 자동 매핑 |

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│  사용자 (웹 UI)                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │PromptPanel│  │SpecPanel │  │ Viewer3D │  │ScenePipeline     │    │
│  │          │  │          │  │ /VRViewer│  │Banner            │    │
│  └────┬─────┘  └──┬───┬──┘  └──────────┘  └──────────────────┘    │
│       │            │   │                                            │
│       └────────────┴───┴─────────────┐                              │
│                                      ▼                              │
│                            web/lib/api.ts                           │
└──────────────────────────────────────┼──────────────────────────────┘
                                       │ HTTP
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI 서버 (server/main.py)                                       │
│                                                                      │
│  /api/generate  ─→ Claude (enhance + spec) ─→ glTF export           │
│  /api/meshgen   ─→ rodin_client ─→ Rodin Gen-2 (text→3D, 동시성 RODIN_CONCURRENCY) │
│  /api/hdgen     ─→ image_gen (FLUX) + rodin_client (multiview concat→3D)          │
│  /api/envgen    ─→ marble_client ─→ World Labs Marble (환경 생성)     │
│  /api/material-enhance ─→ material_enhance (rodin_texture_only PBR)   │
│  /api/modify    ─→ modify_client (Claude 분류) ─→ tier별 디스패치     │
│  /api/deploy    ─→ UE 프로젝트로 파일 복사                             │
└──────────────────────────────────────┼──────────────────────────────┘
                                       │ 파일 시스템
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Unreal Engine 5 (scripts/ue_set_watcher.py)                         │
│                                                                      │
│  Slate tick (2초 주기) ─→ set.gltf 변경 감지                           │
│    ├─ _import_gltf()           GLB/glTF 에셋 임포트                    │
│    ├─ _import_hd_glb_folder()  HD 3D 모델 임포트                       │
│    ├─ _import_marble_env()     World Labs 환경 메시 임포트              │
│    ├─ _place_from_spec()       set_spec.json 기반 배치                 │
│    │    ├─ Megascans 바닥 머티리얼 자동 적용                             │
│    │    └─ _setup_full_lighting() 환경 블록 기반 조명 셋업               │
│    └─ _apply_modify_commands() 실시간 수정 명령 처리                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 파일 구조

```
3D-test/
├── server/
│   └── main.py                  # FastAPI 서버 — 전체 API 엔드포인트
│
├── setlab/                      # 핵심 파이프라인 모듈
│   ├── models.py                # Pydantic 데이터 모델 (SetSpec, ModulePlacement, EnvironmentSettings)
│   ├── prompts.py               # LLM 시스템 프롬프트 (JSON 스키마 정의)
│   ├── claude_client.py         # Claude API — 프롬프트 향상, 스펙 생성, 리파인
│   ├── ollama_client.py         # Ollama 로컬 LLM 클라이언트 (대체 백엔드)
│   ├── llm_json.py              # LLM 출력 JSON 파싱 (json-repair 폴백)
│   ├── rodin_client.py          # Hyper3D Rodin Gen-2 (text→3D, multiview→3D)
│   ├── studio3d_client.py       # (레거시/참고) Hunyuan via 3D AI Studio
│   ├── image_gen.py             # FLUX 1.1 Pro — 멀티뷰 참조 이미지 생성
│   ├── marble_client.py         # World Labs Marble — 전체 환경 생성
│   ├── material_enhance.py      # rodin_texture_only (웨더링 프롬프트 + 참조 이미지)
│   ├── modify_client.py         # 실시간 수정 분류기 (Claude tier classification)
│   ├── export_gltf.py           # SetSpec → glTF 변환
│   ├── export_usda.py           # SetSpec → USDA 변환
│   ├── layout_orient.py         # 건물 방향 자동 보정
│   ├── glb_rotation_bake.py     # GLB 회전값 베이킹
│   ├── run.py                   # CLI 파이프라인 러너
│   ├── mesh_client.py           # (레거시) Tripo text→3D
│   ├── hd_mesh_client.py        # (레거시) Tripo multiview→3D
│   └── mock_backend.py          # 테스트용 목 백엔드
│
├── scripts/
│   ├── ue_set_watcher.py        # UE5 Python — 자동 임포트/배치/조명/수정 워처
│   ├── unreal_spawn_from_spec.py# UE5 스펙 기반 스폰 (단독 실행)
│   ├── ue_auto_reimport.py      # UE5 자동 리임포트
│   ├── blender_import_set.py    # Blender 임포트 스크립트
│   ├── prompt_to_viewport.sh    # CLI 파이프라인 (프롬프트→뷰포트)
│   └── deploy_set_gltf_to_projects.sh
│
├── web/                         # Next.js 프론트엔드
│   ├── app/
│   │   ├── page.tsx             # 메인 페이지 — 전체 상태 관리 및 API 연동
│   │   ├── layout.tsx           # 루트 레이아웃
│   │   └── globals.css          # 전역 스타일
│   ├── components/
│   │   ├── PromptPanel.tsx      # 프롬프트 입력 + Enhance/Generate 버튼
│   │   ├── SpecPanel.tsx        # 스펙 표시, 3D/HD 생성, 머티리얼 향상, 실시간 수정 UI
│   │   ├── Viewer3D.tsx         # Three.js 3D 뷰어
│   │   ├── VRViewer.tsx         # WebXR VR 뷰어
│   │   ├── HistoryPanel.tsx     # 생성 히스토리
│   │   ├── SettingsPanel.tsx    # 백엔드/UE 설정
│   │   ├── ScenePipelineBanner.tsx # 파이프라인 진행 상태 배너
│   │   ├── ImportedMeshModule.tsx  # GLB 메시 뷰어 컴포넌트
│   │   ├── ViewportModulePick.tsx  # 뷰포트 모듈 선택
│   │   └── FolderBrowser.tsx    # UE 프로젝트 폴더 브라우저
│   └── lib/
│       ├── api.ts               # API 클라이언트 함수 전체
│       ├── autoPipeline.ts      # 자동 파이프라인 설정 파서
│       ├── meshOrientation.ts   # 메시 방향 보정 유틸
│       ├── meshGlbRotation.ts   # GLB 회전 유틸
│       └── modulePickThree.ts   # Three.js 모듈 피킹
│
├── out/                         # 생성된 씬 출력 (run_id별 폴더)
│   └── web_*/
│       ├── set_spec.json        # 씬 스펙 JSON
│       ├── set.gltf             # 레이아웃 glTF
│       ├── meshes/              # 생성된 GLB 3D 모델
│       │   ├── *.glb
│       │   └── _asset_urls.json # 호스팅된 에셋 URL (material enhance용)
│       ├── images/              # FLUX 참조 이미지
│       └── environment/         # World Labs Marble 환경 출력
│
├── docs/                        # 문서
├── prompts/                     # 예제 프롬프트
├── schemas/                     # JSON 스키마
├── requirements.txt             # Python 의존성
└── .env.example                 # 환경 변수 템플릿
```

---

## 구현 Phase별 작업 내역

### Phase 0: 기존 기반 (사전 구축)

프로젝트 시작 전에 이미 동작하던 핵심 인프라:

- **LLM 기반 레이아웃 생성:** Claude/Ollama → JSON 스펙 → glTF 내보내기
- **웹 UI:** Next.js + Three.js 3D 뷰어, 프롬프트 입력, 히스토리 관리
- **FastAPI 서버:** generate/refine/deploy API 엔드포인트
- **Tripo3D 연동:** text→3D 메시 생성 (이후 교체됨)
- **UE5 워처:** 기본적인 파일 감시 + glTF 임포트 + spec 기반 배치
- **VR 뷰어:** WebXR 기반 VR 프리뷰

### Phase 1: 3D AI Studio 통합 (Hunyuan 3D 3.5 Pro)

**목표:** Tripo3D를 고품질 Hunyuan 3D 3.5 Pro로 교체

**작업 내용:**
- `setlab/studio3d_client.py` 신규 생성 — text→3D, multiview→3D 통합 클라이언트
- REST API 기반 비동기 처리 (`httpx` + `asyncio`)
- 최대 1.5M 폴리곤, 동시 10개 태스크 처리
- `_submit_text_to_3d()`, `_submit_multiview_to_3d()`, `_poll_until_done()`, `_download_glb()` 구현
- `server/main.py`에서 import 경로를 `mesh_client` → `studio3d_client`로 변경
- `.env.example`에 `STUDIO3D_API_KEY`, `STUDIO3D_CONCURRENCY` 등 문서화

**연동 API:**
- `POST https://api.3daistudio.com/api/rest/v1/creations` — 생성 요청
- `GET https://api.3daistudio.com/api/rest/v1/creations/{task_id}` — 상태 폴링
- 완료 시 GLB URL에서 다운로드

### Phase 2: FLUX 1.1 Pro 이미지 생성

**목표:** Gemini를 FLUX 1.1 Pro로 교체하여 HD 3D 파이프라인 참조 이미지 품질 향상

**작업 내용:**
- `setlab/image_gen.py` 전면 재작성 — BFL FLUX 1.1 Pro API 연동
- 모듈당 4개 뷰(front, left, back, right) 생성
- `ThreadPoolExecutor` 사용으로 병렬 이미지 생성 → 총 생성 시간 대폭 단축
- `_build_prompt()` 함수를 FLUX 특성에 맞게 최적화
- `.env.example`에 `FLUX_API_KEY` 문서화

**연동 API:**
- `POST https://api.bfl.ai/v1/flux-pro-1.1` — 이미지 생성 요청
- `GET https://api.bfl.ai/v1/get_result?id={task_id}` — 결과 폴링

### Phase 3: World Labs Marble 환경 생성

**목표:** 텍스트 프롬프트로 전체 탐험 가능한 3D 환경 생성

**작업 내용:**
- `setlab/marble_client.py` 신규 생성 — World Labs Marble Plus API 클라이언트
- GLB 콜라이더 메시, Gaussian Splat (SPZ 500K/2M), 파노라마 이미지 다운로드
- `server/main.py`에 `/api/envgen/{run_id}` POST/GET 엔드포인트 추가
- `scripts/ue_set_watcher.py`에 Marble 환경 메시 임포트/배치 로직 추가
- Deploy 시 `environment/` 폴더 자동 복사

**연동 API:**
- `POST https://api.worldlabs.ai/v1/worlds/generate` — 환경 생성 요청
- `GET https://api.worldlabs.ai/v1/worlds/{generation_id}` — 상태 폴링

### Phase 4: AI 머티리얼 향상 (웨더링/에이징)

**목표:** 생성된 3D 모델의 PBR 텍스처에 자동 웨더링/에이징 효과 적용

**작업 내용:**
- `setlab/material_enhance.py` — Hyper3D `rodin_texture_only`로 재텍스처
  - 5가지 웨더링 프리셋: `medieval_stone`, `aged_wood`, `rusty_metal`, `worn_brick`, `generic_weathered`
  - 참조 이미지: `images/<id>/front.png` 우선, 없으면 FLUX 1장
  - `rodin_client`가 저장한 `_asset_urls.json`으로 GLB URL 폴백(로컬 GLB 없을 때)
- `rodin_client.py` — GLB 다운로드 후 hosted URL을 `_asset_urls.json`에 저장
- `server/main.py`에 `/api/material-enhance/{run_id}` POST/GET 엔드포인트 추가
- 프론트엔드: `MaterialEnhanceStatus` 타입, `startMaterialEnhance()`/`pollMaterialEnhanceStatus()` API 함수
- `SpecPanel.tsx`에 스타일 프리셋 드롭다운 + Enhance Materials 버튼 + 진행 바

**연동 API:**
- `POST https://api.hyper3d.com/api/v2/rodin_texture_only` — 모델(GLB) + 참조 이미지 + 프롬프트
- `POST /v2/status`, `POST /v2/download` — Rodin 메시 생성과 동일 패턴
- 완료 시 새 GLB 다운로드하여 원본 덮어쓰기

### Phase 5: Megascans 바닥 머티리얼 자동화

**목표:** 바닥(mod_floor) 모듈에 고해상도 Quixel Megascans 타일링 텍스처 자동 적용

**작업 내용:**
- `setlab/prompts.py` — 스펙 스키마에 `ground_material` 필드 추가 (13종: cobblestone, asphalt, grass, concrete 등)
- `setlab/models.py` — `SetSpec`에 `ground_material: str = ""` 필드 추가
- `scripts/ue_set_watcher.py` 수정:
  - `_GROUND_KEYWORDS` 매핑 (ground_material → Megascans 검색어)
  - `_find_megascans_material()` — `MEGASCANS_ROOT` 하위에서 Material Instance 검색
  - `_apply_ground_material()` — 머티리얼 적용 + UV 타일링 파라미터 설정
  - `_place_from_spec()` — `mod_floor` 모듈은 Plane 메시 + Megascans 머티리얼로 배치
- `.env.example`에 `MEGASCANS_ROOT` 문서화

### Phase 6: UE5 조명 자동화

**목표:** LLM이 생성한 environment 블록으로 UE5 조명/대기 시스템 전체 자동 구성

**작업 내용:**
- `setlab/prompts.py` — 스펙 스키마에 `environment` 블록 추가:
  - `time_of_day`: dawn/morning/noon/afternoon/golden_hour/sunset/dusk/night
  - `weather`: clear/overcast/cloudy/foggy/rainy/stormy/snowy
  - `fog_density`: 0.0~1.0
  - `sun_intensity`: 0.0~100.0
  - `sun_color_temp`: 2000K~10000K
- `setlab/models.py` — `EnvironmentSettings` Pydantic 모델 + `SetSpec.environment` 필드
- `scripts/ue_set_watcher.py` — `_setup_full_lighting(env)` 구현:
  - **Directional Light** — `time_of_day`별 sun pitch 매핑, `sun_color_temp` → RGB 변환
  - **Sky Atmosphere** — 사실적 하늘 렌더링
  - **Exponential Height Fog** — `fog_density` × `weather` 배수
  - **Volumetric Cloud** — 동적 구름 레이어
  - **Sky Light** — Captured Scene 기반, 야간 감쇠
  - **Post Process Volume** — Lumen GI/Reflection, 히스토그램 자동 노출
  - 모든 액터에 `SETLAB_LIGHT` 태그 → 재실행 시 자동 정리

### Phase 7: 실시간 수정 시스템

**목표:** 촬영 중 감독의 프롬프트("조명을 노을로 바꿔", "왼쪽 벽 더 거칠게")를 즉시 반영

**작업 내용:**
- `setlab/modify_client.py` 신규 생성 — Claude가 수정 요청을 3단계 tier로 분류:
  - **instant** (< 1초): 조명/안개/대기 파라미터 변경 → UE에서 1프레임 내 적용
  - **fast** (30-60초): 특정 모듈 텍스처 재생성 (rodin_texture_only)
  - **moderate** (3-6분): 특정 모듈 3D 에셋 완전 재생성

- `server/main.py` — `POST /api/modify/{run_id}` 엔드포인트:
  - Claude로 instruction 분류 → tier별 디스패치
  - instant: `set_spec.json` environment 업데이트 + `modify_commands.json` 작성
  - fast: material enhancement 스레드 실행
  - moderate: 스펙 description/scale 업데이트 + mesh 재생성 스레드 실행

- `scripts/ue_set_watcher.py` — 수정 명령 워처 추가:
  - `modify_commands.json` 파일 변경 감지 (매 tick)
  - `_apply_instant_modify()`: lighting 액터 재배치
  - `_apply_fast_modify()`: retexture 진행 로깅

- 프론트엔드: `sendModification()` API 함수 + SpecPanel 내 "실시간 수정" 입력란
  - Enter 또는 "적용" 버튼으로 전송
  - tier별 색상 코드 결과 표시 (instant=초록, fast=노랑, moderate=파랑, error=빨강)
  - instant 시 spec 자동 재로드, fast/moderate 시 기존 폴링 루프 활용

---

## 핵심 데이터 흐름

### 1. 씬 생성 파이프라인

```
사용자 프롬프트
    │
    ▼
Claude Enhance (프롬프트 → 상세 영문 씬 브리프)
    │
    ▼
Claude Generate (브리프 → JSON SetSpec)
    │  ├─ title, era_style, ground_material
    │  ├─ environment (time_of_day, weather, fog, sun)
    │  └─ modules[] (id, asset, description, position, rotation, scale)
    ▼
glTF Export (SetSpec → set.gltf + set_spec.json)
    │
    ├─→ 3D Model Generation (Hunyuan 3D 3.5 Pro, 10개 동시)
    │     └─ 모듈별 description → GLB 파일
    │
    ├─→ HD 3D Generation
    │     ├─ FLUX 1.1 Pro → 모듈별 4뷰 참조 이미지
    │     └─ Hunyuan 3D multiview→3D → HD GLB 파일
    │
    ├─→ Environment Generation (World Labs Marble)
    │     └─ 전체 씬 프롬프트 → GLB + SPZ + 파노라마
    │
    └─→ Material Enhancement (Hyper3D rodin_texture_only)
          └─ GLB + 웨더링 프롬프트 → 향상된 PBR GLB
```

### 2. Unreal Engine 배치 파이프라인

```
Deploy 클릭
    │
    ▼
서버가 out/<run_id>/ → UE_PROJECT/Content/Incoming/SetLab/ 파일 복사
    │
    ▼
ue_set_watcher.py (2초 주기 tick)
    ├─ set.gltf 변경 감지
    ├─ GLB 에셋 임포트 (Interchange + metallic 패치)
    ├─ 기존 SETLAB_AUTO 태그 액터 제거
    ├─ set_spec.json 기반 StaticMeshActor 배치
    │   ├─ HD GLB 있으면 HD 메시 사용, 없으면 기본 Cube
    │   ├─ mod_floor → Plane + Megascans 머티리얼
    │   └─ 좌표 변환: Y-up meters(glTF) → Z-up cm(UE)
    ├─ environment 블록 기반 조명 셋업
    │   └─ DirectionalLight + SkyAtmosphere + HeightFog + ...
    └─ modify_commands.json 감지 → 실시간 수정 적용
```

### 3. 실시간 수정 흐름

```
감독: "조명을 노을로 바꿔"
    │
    ▼
웹 UI → POST /api/modify/{run_id}
    │
    ▼
Claude 분류 → { tier: "instant", commands: { environment: { time_of_day: "sunset", ... } } }
    │
    ├─→ set_spec.json environment 업데이트
    └─→ UE_PROJECT/Saved/SetLab/modify_commands.json 작성
          │
          ▼
        ue_set_watcher.py _apply_modify_commands()
          └─ lighting 액터 재배치 (< 1프레임)
```

---

## API 엔드포인트 요약

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/generate` | 프롬프트 → SetSpec + glTF 생성 |
| POST | `/api/enhance` | 프롬프트 향상 (Claude art director) |
| POST | `/api/refine/{run_id}` | 기존 스펙 수정 (전체) |
| POST | `/api/refine-module/{run_id}` | 단일 모듈 수정 |
| POST | `/api/meshgen/{run_id}` | 3D 모델 생성 시작 |
| GET | `/api/meshgen/{run_id}/status` | 3D 생성 상태 폴링 |
| POST | `/api/hdgen/{run_id}` | HD 3D 생성 시작 |
| GET | `/api/hdgen/{run_id}/status` | HD 생성 상태 폴링 |
| POST | `/api/envgen/{run_id}` | 환경 생성 시작 (Marble) |
| GET | `/api/envgen/{run_id}/status` | 환경 생성 상태 폴링 |
| POST | `/api/material-enhance/{run_id}` | 머티리얼 향상 시작 |
| GET | `/api/material-enhance/{run_id}/status` | 머티리얼 향상 상태 폴링 |
| POST | `/api/modify/{run_id}` | 실시간 수정 (tier 자동 분류) |
| POST | `/api/deploy/{run_id}` | UE 프로젝트로 배포 |
| POST | `/api/orient-buildings/{run_id}` | 건물 방향 자동 보정 |
| POST | `/api/save-edits/{run_id}` | 뷰어 편집 저장 |
| GET | `/api/history` | 생성 히스토리 목록 |
| GET | `/api/config` | 서버 설정 조회 |
| POST | `/api/config` | 서버 설정 변경 |
| GET | `/api/browse` | UE 프로젝트 폴더 탐색 |

---

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API 키 |
| `RODIN_API_KEY` (또는 `HYPER3D_API_KEY`) | ✅ | Hyper3D Rodin 메시 생성 + 머티리얼 향상(rodin_texture_only) |
| `FLUX_API_KEY` | ✅ | HD 멀티뷰 이미지; 머티리얼 향상 시 `front` 없으면 참조 1장 생성 |
| `WORLDLABS_API_KEY` | ✅ | World Labs Marble API 키 |
| `UE_PROJECT` | ✅ | Unreal Engine 프로젝트 경로 |
| `RODIN_CONCURRENCY` | | Rodin 메시/텍스처 동시성 (기본 10 / 머티리얼은 MATERIAL_RODIN_CONCURRENCY) |
| `WORLDLABS_MODEL` | | Marble 모델 (기본 "Marble 0.1-plus") |
| `MEGASCANS_ROOT` | | Megascans 콘텐츠 경로 (기본 /Game/Megascans/Surfaces) |
| `MATERIAL_ENHANCE_STYLE` | | 머티리얼 향상 기본 프리셋 |

---

## 실행 방법

### 서버 시작
```bash
# 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 가상환경 + 의존성
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn python-dotenv anthropic

# 서버 시작
cd server && uvicorn main:app --reload --port 8000
```

### 프론트엔드 시작
```bash
cd web && npm install && npm run dev
```

### UE5 워처 연결
```
# Unreal Editor Python 콘솔에서:
exec(open('/path/to/scripts/ue_set_watcher.py').read())
```

---

## 사용된 외부 AI 서비스 및 비용 참고

| 서비스 | 용도 | 비용 모델 |
|--------|------|-----------|
| Anthropic Claude Sonnet 4.6 | 프롬프트 향상, 스펙 생성, 수정 분류 | 토큰 기반 |
| Hyper3D Rodin | text→3D, multiview→3D, **rodin_texture_only** | 크레딧 기반 |
| BFL FLUX 1.1 Pro | 포토리얼 참조 이미지 생성 | API 호출 기반 |
| World Labs Marble Plus | 전체 3D 환경 생성 | API 호출 기반 |
| Quixel Megascans | 고해상도 타일링 PBR 텍스처 | UE 내 무료 |

---

## 예상 씬 생성 시간

| 단계 | 소요 시간 | 비고 |
|------|-----------|------|
| Enhance + Generate (Claude) | ~5-10초 | 프롬프트 향상 + JSON 스펙 |
| 3D Model Generation | ~2-4분 | 10개 모듈 동시 처리 |
| HD 3D (FLUX + Hunyuan) | ~3-5분 | 이미지 병렬 생성 → multiview→3D |
| Material Enhancement | ~1-2분 | 텍스처 재생성 |
| **전체 파이프라인** | **~7-12분** | 최고 품질 기준 |
| 실시간 수정 (instant) | < 1초 | 조명/안개 파라미터 |
| 실시간 수정 (fast) | ~30-60초 | 텍스처 변경 |
| 실시간 수정 (moderate) | ~3-6분 | 에셋 재생성 |

---

## 디즈니/마블 VP 활용 적합성

이 프로젝트는 Walt Disney Company의 StudioLAB에서 수행하는 Virtual Production / XR 기술 연구와 높은 부합도를 보인다:

- **AI 기반 3D 셋 구축:** 텍스트 프롬프트 → 3D 환경 자동 생성 파이프라인
- **XR/VP 기술:** Unreal Engine 5 + Lumen GI + nDisplay 연동 설계
- **실시간 수정:** 촬영 중 감독의 지시를 프롬프트로 즉시 반영
- **프로토타이핑:** Phase 1~7까지 신속한 구현으로 R&D 프로토타입 완성
- **AI 모델 통합:** 여러 최신 AI 모델 (Claude, Hunyuan, FLUX, Marble)을 하나의 파이프라인으로 통합

배경 전용 사용 시 85-90% production-ready 품질 달성 가능하며, 나머지 10-15%는 아티스트의 최종 폴리싱(커스텀 셰이더, 디테일 프롭 배치, 라이팅 미세 조정)으로 보완한다.
