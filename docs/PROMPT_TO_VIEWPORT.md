# 프롬프트 → 뷰포트 (Prompt-to-Viewport)

**프롬프트만 치면 Unreal 뷰포트에 세트가 자동으로 뜬다** — 전체 파이프.

---

## 전체 흐름 (한 눈에)

```
터미널                             Unreal 에디터
──────                             ──────────────
프롬프트 입력                       ue_auto_reimport.py 가 돌고 있음
    ↓                                    ↓
Ollama(llama3.2)가 JSON 생성       (2초마다 파일 변경 감시 중)
    ↓
Python이 set.gltf 로 변환
    ↓
UE 프로젝트 Content/Incoming 에 복사 →  파일 변경 감지!
                                        ↓
                                   자동 Reimport
                                        ↓
                                   뷰포트에 반영
```

---

## 세팅 (한 번만)

### 1) `.env` 파일 만들기

```bash
cd /path/to/3D-test
cp .env.example .env
```

`.env` 를 열고 **본인 Unreal 프로젝트 경로**를 넣습니다:

```
UE_PROJECT=/Users/jkjung/Unreal_Projects/MyProject
```

### 2) 첫 임포트 (에디터에서 1회)

- Unreal 에디터에서 **Content Browser** → **`Incoming` 폴더** 만들기 (없으면).
- 한 번 **Import** 또는 **Import Into Level** 로 `set.gltf` 넣기.
  → 이후부터는 **같은 위치에 덮어쓰면** Reimport 로 갱신됩니다.

### 3) 자동 감시 켜기 (에디터에서 1회)

Unreal 에디터에서 **Tools → Execute Python Script** → `scripts/ue_auto_reimport.py` 선택.

또는 **Output Log** 옆 **Cmd** 드롭다운을 **Python** 으로 바꾸고:

```python
exec(open("/path/to/3D-test/scripts/ue_auto_reimport.py").read())
```

터미널에 `[SetLab] Watcher started` 로그가 뜨면 성공.  
**에디터를 닫을 때까지** 2초마다 `Content/Incoming/set.gltf` 변경을 감시합니다.

---

## 사용 (매번)

터미널에서 **프롬프트 한 줄**:

```bash
./scripts/prompt_to_viewport.sh "SF 복도 12m, 기둥 두 개, 저녁 조명"
```

**이게 전부입니다.** 스크립트가:

1. Ollama 에 프롬프트를 보내 JSON 생성  
2. `set.gltf` 로 변환  
3. UE 프로젝트 `Content/Incoming/` 에 복사  

→ 에디터의 watcher 가 파일 변경을 감지 → **자동 Reimport** → **뷰포트에 반영**.

---

## 프롬프트 바꿔 가며 반복

```bash
./scripts/prompt_to_viewport.sh "중세 성 안의 대연회장 20m, 기둥 네 개"
# 몇 초 후 → 뷰포트가 바뀜

./scripts/prompt_to_viewport.sh "현대 사무실 복도 8m, 유리벽"
# 또 바뀜
```

---

## 파일 정리

| 파일 | 역할 |
|------|------|
| `scripts/prompt_to_viewport.sh` | **터미널 진입점** — 프롬프트 → glTF → UE 복사 |
| `scripts/ue_auto_reimport.py` | **에디터 안 watcher** — 파일 변경 시 자동 Reimport |
| `.env` | `UE_PROJECT` 등 경로 설정 (`.gitignore` 에 포함) |
| `.env.example` | `.env` 템플릿 |

---

## 감시 멈추기

에디터 Python 콘솔에서:

```python
import ue_auto_reimport
ue_auto_reimport.stop()
```

또는 에디터를 닫으면 자동 종료.

---

## Unity 도 같이 하려면

`.env` 에 `UNITY_PROJECT` 추가 → `prompt_to_engines.sh` 사용.  
Unity 쪽 자동 Reimport 는 `AssetDatabase.ImportAsset` 기반 에디터 스크립트로 같은 패턴 적용 가능.

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| `[SetLab] Watcher started` 안 뜸 | Python Editor Script Plugin 활성? 에디터 재시작? |
| 파일 복사 됐는데 Reimport 안 됨 | `WATCH_FILE` 경로가 프로젝트의 `Content/Incoming/set.gltf` 와 맞는지 |
| Ollama 연결 실패 | `brew services list` 에서 ollama 상태 / `ollama list` |
| glTF 가 너무 작거나 큼 | `setlab/prompts.py` 의 단위(미터) 규칙 확인 |
