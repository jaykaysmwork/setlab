# `set.gltf` 바뀔 때 Unreal에 **자동 반영**하려면 (셋업 개요)

“터미널에서 생성만 하면 뷰포트에 바로 뜬다”는 **한 방**은 없고, 아래 중 **하나의 방식**을 골라 붙이면 됩니다.  
난이도는 **A < B < C** 입니다.

---

## 재시작까지 했다면 — **그다음은 이것만** (가장 쉬운 길)

**지금 이해하면 될 것:** Python 플러그인은 **“나중에 자동 스크립트 쓸 때”** 필요한 **도구 상자**이고, **당장** 세트를 갱신하는 가장 단순한 방법은 **파일 복사 + Reimport** 입니다.

### 1단계 — 언리얼에서 “받는 통로” 한 번 만들기

1. 에디터에서 **Content Browser** 연다.  
2. **우클릭 → New Folder** → 이름 예: `Incoming`  
   - 경로가 **`/Game/Incoming`** 처럼 보이면 OK.

### 2단계 — `set.gltf` 를 **처음 한 번만** 넣기

1. Finder에서 `3D-test/out/어떤폴더/set.gltf` 를 연다.  
2. **같은 폴더에 있는 `.bin` 파일**이 있으면 **같이** 있어야 함 (glTF가 쪼개져 있을 때).  
3. `set.gltf` (필요하면 `.bin`도) 를 **Content Browser의 `Incoming` 폴더로 드래그**한다.  
4. Interchange 창이 뜨면 **Import** 로 끝까지 진행한다.  
5. 이제 프로젝트 안에 **`set`** 이라는 애셋(또는 메시들)이 생긴다.

### 3단계 — 브리프 바꿔서 **다시 생성**할 때마다

1. 터미널에서 평소처럼:

   `python -m setlab.run my_brief.txt --out out/원하는폴더 --backend ollama --model llama3.2`

2. **새로 만들어진 `set.gltf`** 를 **언리얼 프로젝트의 같은 위치**로 **덮어쓴다**  
   - 예: `MyProject/Content/Incoming/set.gltf`  
   - 도우미: `scripts/copy_set_gltf_to_unreal.sh` (아래 README 주석 참고)

3. 언리얼로 돌아와 **Content Browser** 에서 **`set` 애셋 선택** → **우클릭 → Reimport**.  
4. 레벨에 이미 배치해 두었다면 **갱신된 모양**으로 다시 읽히는 경우가 많다 (안 되면 레벨의 액터 한 번 선택 후 확인).

**정리:** “그다음”은 **① Incoming 폴더 + 첫 임포트 한 번** → **② 이후엔 생성 → 복사 덮어쓰기 → Reimport** 이 세 줄이 전부다.  
Python은 **이걸 Reimport까지 자동으로 눌러 주려고** 나중에 쓰는 것이지, **꼭 지금 당장 써야 하는 건 아니다**.

---

## 공통 전제

- Unreal **에디터가 켜져 있어야** 임포트가 가능합니다 (백그라운드만으로는 보통 불가).  
- **Python Editor Script Plugin** 사용 시: **Edit → Plugins** 에서 활성 → 에디터 재시작.  
- **절대 경로**에 `set.gltf` 가 있으면 프로젝트 밖 파일을 읽게 되므로, 팀 정책에 맞게 **`Content/Incoming` 으로 복사**하는 패턴이 흔합니다.

---

## A. 반자동 — **같은 폴더에 덮어쓰기 + Reimport** (설정 거의 없음)

**셋업**

1. 한 번만 **Content Browser** 에서 폴더 만들기: 예 `/Game/Incoming`  
2. `set.gltf` 를 그 안에 **첫 임포트** (Interchange 완료까지).  
3. 이후 파이프라인은 **항상 같은 파일명·같은 경로**로 덮어쓰기:

```bash
cp /path/to/3D-test/out/run/set.gltf "/path/to/MyProject/Content/Incoming/set.gltf"
```

4. 언리얼에서 해당 애셋 선택 → **우클릭 → Reimport** (또는 단축키).

**자동에 가깝게:** 에디터 **매크로/에디터 유틸**로 “Reimport Incoming/set” 버튼 하나만 만들어 두는 방법도 있음.

**장점:** 추가 플러그인·코드 최소.  
**단점:** 완전 무인은 아님.

---

## B. 에디터 **Python** — 주기적으로 폴더를 보고 **자동 임포트** (중간 난이도)

**셋업**

1. **Edit → Plugins**  
   - **Python Editor Script Plugin** ✓  
   - (권장) **Editor Scripting Utilities** ✓  
2. **Project Settings → Plugins → Python**  
   - **Enable Remote Execution** (원격에서 에디터에 명령 보낼 때만 필요 — 아래 C와 함께 쓸 때)  
3. 프로젝트에 스크립트 저장: 예 `Content/Python/import_incoming.py`  
   - 내용: `set.gltf` 의 **mtime** 이 바뀌었는지 검사 → 바뀌면 **Interchange 또는 AssetImportTask** 로 임포트 또는 **reimport** API 호출.

**실행 방법 (한 번 에디터 연 다음)**

- **Output Log** 옆 **Python** 창에서 스크립트 실행하거나  
- **Tools → Execute Python Script** 로 위 파일 실행.

**주의**

- UE에 내장 Python에는 `watchdog` 이 없을 수 있어 **타이머(몇 초마다 폴링)** 가 단순합니다.  
- **임포트 API** 는 UE 버전마다 이름이 조금 다릅니다 — Interchange 문서를 본인 **5.x**에 맞춰 확인.

**장점:** 덮어쓰기만 하면 **버튼 없이** 갱신 가능(폴링 중일 때).  
**단점:** 스크립트 작성·디버깅 필요.

---

## C. 터미널 → 에디터 **원격 실행** (고급)

**아이디어:** 셸에서 “지금 임포트해” 를 Unreal에 보냄.

**셋업 (개략)**

1. **Python Remote Execution** 켜기 (위 B).  
2. Epic 문서 기준으로 **원격 클라이언트** 또는 **소켓으로 Python 명령 전송** — 구현 방식은 OS·UE 버전에 따라 다름.  
3. 또는 **UnrealEditor 커맨드라인**으로 `-ExecutePythonScript=` / `-run=pythonscript` 를 지원하는 빌드면 **배치 스크립트**에서 에디터를 띄워 실행 (보통 **헤드리스 자동화**에 가깝고, **뷰포트 즉시 반영**용으로는 무겁다).

**장점:** CI·스크립트와 연동.  
**단점:** 설정·방화벽·보안·버전 차이로 **가장 손이 많이 감**.

---

## D. **CI / 빌드 머신** (팀·야간 배치용)

**셋업**

1. 소스에 `set.gltf` 생성 단계(Job)  
2. 아티팩트를 **프로젝트 `Content/Incoming`** 에 복사하는 Job  
3. (선택) **Unreal Automation** 또는 **커맨드라인 쿠킹**으로 임포트까지

**장점:** 재현 가능·팀 공유.  
**단점:** 로컬 “내가 타이핑하고 바로 보기” 용도에는 과함.

---

## 이 레포(`setlab`)와 맞물리는 최소 조합 (추천)

1. 파이프라인은 그대로:  
   `python -m setlab.run ... --out out/run`  
2. **빌드/복사 한 줄** 추가:  
   `out/run/set.gltf` → `MyProject/Content/Incoming/set.gltf`  
3. 처음은 **A (Reimport)** 로 익히고, 익숙해지면 **B (폴링 Python)** 로 올리기.

---

## 요약 표

| 방식 | 필요한 셋업 | 자동화 수준 |
|------|-------------|-------------|
| **A** Reimport | 폴더 고정 + 첫 임포트 1회 | 수동 클릭 1번 |
| **B** 에디터 Python | Python 플러그인 + 스크립트 | 덮어쓰기 후 자동(폴링) |
| **C** 원격/CLI | Remote Execution 또는 CLI 지원 확인 | 외부에서 트리거 |
| **D** CI | 러너 + Unreal 자동화 | 배치 단위 |

완전한 “말만 하면 뜬다”에 가장 가까운 건 **B 또는 C**이고, **지금 레포만으로는 ②까지 만든 뒤 ③을 위 셋업으로 붙이는 것**이 다음 작업입니다.
