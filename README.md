# SetLab pilot — brief → structured set → USDA / glTF

로컬에서 **세트 브리프(텍스트)** 를 **구조화 스펙(JSON)** 으로 바꾼 뒤, **USDA**와 **glTF**로 보내 Unity / Unreal / Blender / usdview 등으로 가져다 쓸 수 있는 최소 파일럿입니다.

**핵심 경로는 AI(Ollama + Llama 등)** 로 브리프에서 레이아웃 JSON을 생성하는 것입니다. `mock` 백엔드는 **파이프라인·임포트만 점검**할 때 쓰는 보조 수단입니다.

**Unreal을 먼저 잡고 처음부터 다시** 진행하려면 → [`docs/START_UNREAL_FIRST.md`](docs/START_UNREAL_FIRST.md)  
**inZOI 류 도시·거리 세트**를 목표로 단계별로 → [`docs/INZOI_STYLE_SET_STEP_BY_STEP.md`](docs/INZOI_STYLE_SET_STEP_BY_STEP.md)  
**생성된 glTF를 Unreal에 자동 반영**하려면 → [`docs/UNREAL_AUTO_IMPORT_SETUP.md`](docs/UNREAL_AUTO_IMPORT_SETUP.md)  
**처음부터 다시 — 자동/수동이 뭔지** → [`docs/FROM_ZERO_WHAT_IS_AUTOMATIC.md`](docs/FROM_ZERO_WHAT_IS_AUTOMATIC.md)  
**Unity + Unreal, 세트를 빨리 같이 보기** → [`docs/UNITY_UNREAL_LIVE_PREVIEW.md`](docs/UNITY_UNREAL_LIVE_PREVIEW.md)  
**프롬프트 한 번 → 엔진 폴더로 복사까지** → [`docs/PROMPT_TO_VIEWPORT.md`](docs/PROMPT_TO_VIEWPORT.md) (`scripts/prompt_to_engines.sh`)

## 요구 사항

- Python 3.9+
- **[Ollama](https://ollama.com/)** + 로컬 모델(예: `llama3.2`) — **AI 파일럿의 기본**

## 설치

```bash
cd /Users/jkjung/projects/setlab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

### 1) AI(Ollama) — **기본으로 쓸 명령**

```bash
ollama serve   # 별도 터미널에서 이미 떠 있으면 생략
ollama pull llama3.2
source .venv/bin/activate
python -m setlab.run my_brief.txt --out out/ue57_trailer --backend ollama --model llama3.2
```

- 브리프를 바꿀 때마다 같은 명령으로 **다시 생성**하면 레이아웃이 달라질 수 있습니다.
- `OLLAMA_HOST`가 다르면 `--ollama-url` 또는 환경 변수로 지정합니다.

### 2) 오프라인(mock) — **파이프라인만 테스트**할 때

Ollama 없이 **항상 같은 샘플 JSON**으로 glTF/USDA가 나오는지 확인할 때만 사용합니다.

```bash
source .venv/bin/activate
python -m setlab.run examples/brief_corridor.txt --out out/mock_run --backend mock
```

산출물(두 경로 공통):

- `set_spec.json` — 모듈 배치 스펙
- `set.usda` — USD Stage(큐브 프록시)
- `set.gltf` — glTF 2.0 (임베디드 버퍼)

## 엔진 쪽에서 보기

| 도구 | 방법 |
|------|------|
| **Blender** | `File → Import → glTF` 로 `set.gltf` 임포트 |
| **Unity** | [com.unity.cloud.gltfast](https://docs.unity3d.com/Packages/com.unity.cloud.gltfast@latest) 등 glTF 패키지로 임포트 |
| **Unreal** | glTF 임포터(플러그인/내장 버전에 따라 다름) 또는 Datasmith 경로 |
| **USD** | `usdview set.usda` (Pixar USD 빌드 시) |

## (선택) Blender에서 JSON으로 큐브 생성

```bash
blender --background --python scripts/blender_import_set.py -- out/mock_run/set_spec.json
```

같은 폴더에 `set_blocking.blend`가 저장됩니다.

## 스키마

`schemas/set_spec.schema.json` — `SetSpec` JSON 모양의 참고용 스키마입니다. Pydantic 모델은 `setlab/models.py`에 있습니다.

## 다음에 확장하기 좋은 지점

- 브리프 → JSON 검증 실패 시 **재시도 / 수정 루프**
- 모듈 `asset`을 실제 USD 레퍼런스나 프리팹 ID로 매핑
- **동일 브리프**로 mock vs LLM 산출을 비교하는 스크립트(A/B 파일럿)
