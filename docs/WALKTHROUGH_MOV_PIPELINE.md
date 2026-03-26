# inZOI 스타일 `.mov`까지 가는 상세 과정 (체크리스트)

`inzoi-test.mov` 같은 **실시간 3D 영상**은 한 도구가 아니라 **단계가 쌓인 결과**입니다.  
아래는 **순서대로** 진행할 때의 상세 단계입니다. ✅는 로컬에서 할 작업, 🤖은 AI/스크립트가 돕는 지점입니다.

---

## Phase 0 — 목표 고정 (**확정**)

| 항목 | 선택 |
|------|------|
| **길이** | **30초** |
| **엔진** | **Unreal Engine 5.7** |
| **형식** | **트레일러** (플레이 캡처가 아니라 연출·컷 위주) |

**UE 5.7에서 이 문서를 쓸 때**

- glTF는 **Interchange** 파이프라인(예: **Interchange Framework** 관련 플러그인)으로 들어가며, 임포트 시 **Interchange Pipeline Configuration(Import Content)** 다이얼로그가 뜨는 흐름이 일반적임.  
- 플러그인 이름은 마이너 패치에서도 바뀔 수 있으니, 막히면 **Edit → Plugins** 에서 `Interchange`, `glTF` 로 검색해 **Enabled** 인지 먼저 확인.

**트레일러로 잠그면 달라지는 점**

- **Level Sequence**가 중심이 됨 (카메라·컷·타이밍을 타임라인으로 고정).
- 최종 출력은 보통 **Movie Render Queue(MRQ)** 로 **고정 프레임** 렌더 후 `.mov`/ProRes 등 (실시간 녹화보다 품질·반복에 유리).
- 30초면 **샷 수 4~8개** 정도가 흔함 (각 3~8초); 첫 패스는 **3샷(각 ~10초)** 으로 잡고 다듬어도 됨.

---

## Phase 1 — 브리프 (사람 → 문서)

1. 한 파일에 적기: 장소, 치수 감, 시대, 조명 분위기, 피해야 할 것.
2. 예: `examples/brief_corridor.txt` 형식을 복사해 `my_brief.txt`로 저장.

🤖 *선택*: LLM으로 브리프를 다듬거나 질문 리스트로 보강.

---

## Phase 2 — 레이아웃 스펙 (**핵심: 로컬 LLM**)

이 단계의 **본래 목적**은 **브리프 → 구조화 JSON** 을 **AI(Ollama + 모델)** 가 만들게 하는 것입니다.  
`--backend mock` 은 임포트/스크립트가 도는지 볼 때만 쓰는 **우회로**로 두면 됩니다.

### 2A. 이 레포의 파일럿으로 가기 (**AI 기본**)

```bash
cd /path/to/3D-test
ollama pull llama3.2   # 최초 1회
source .venv/bin/activate
python -m setlab.run my_brief.txt --out out/ue57_trailer --backend ollama --model llama3.2
```

**파이프라인만 빠르게 점검** (브리프 무시·고정 출력):

```bash
python -m setlab.run my_brief.txt --out out/mock_run --backend mock
```

산출물:

- `set_spec.json` — 모듈 ID, 위치, 회전, 스케일
- `set.gltf` — 뷰어/엔진 임포트용 블로킹
- `set.usda` — USD 파이프용

### 2B. 검증 · 반복 (**AI 품질 루프**)

- `set_spec.json`을 열어 모듈 개수·좌표가 브리프와 맞는지 본다.
- 어긋나면 **① 브리프를 더 구체화**하거나 **② `setlab/prompts.py`의 SYSTEM 규칙**을 조정한 뒤, **같은 ollama 명령으로 재생성**.
- JSON 검증에 실패하면 터미널에 raw JSON 일부가 찍힌다 — 모델이 스키마를 어긴 것이므로 프롬프트에 “필수 필드”를 강조하거나, 더 큰/지시 따르기 좋은 모델로 바꿔 본다.

---

## Phase 3 — Unreal **5.7** 에 블로킹 올리기

**원칙**: 임포트 → 레벨에 애셋/씬 배치 → **단위(미터)·축(Y-up)** 확인.

1. **프로젝트**  
   - 템플릿: **Film / Video** 또는 **ArchVis**(정적 연출·라이팅에 익숙) 중 하나를 쓰면 MRQ·시퀀서 맥락에 잘 맞는 경우가 많음.  
   - **스타터 콘텐츠** 유무는 취향 (트레일러만이면 최소로 줄여도 됨).

2. **glTF로 가져오기** (`set.gltf`) — **UE 5.7 / Interchange**  
   Epic 문서 기준으로는 대표적으로 두 가지가 있음:  
   - **개별 애셋**: **Content Browser**에 `set.gltf` **드래그 앤 드롭** 또는 **Add → Import** 로 가져오기.  
   - **씬 전체를 레벨로**: **File → Import Into Level** 로 glTF를 넣으면 FBX “레벨 임포트”와 비슷하게 **한 번에 씬**이 들어오는 경로(프로젝트 설정에 따라 다름).  
   - 임포트 시 **Interchange Pipeline Configuration (Import Content)** 에서 **스케일·축** 확인. 이 파일럿은 **1 unit = 1m** 를 가정하므로, 메시가 너무 크거나 작으면 여기서 **스케일 팩터**만 조정.  
   - (`.gltf`는 보통 `.bin`/텍스처 파일이 같이 있음 — 같은 폴더에서 함께 두고 임포트.)

3. **USD로 가져오기** (`set.usda`) — 선택  
   - **Edit → Plugins** 에서 **Universal Scene Description (USD)** 계열 플러그인 활성 후 재시작.  
   - **USD Stage** 워크플로(에디터 메뉴는 빌드에 따라 `Window` 쪽)로 열거나, 프로젝트에 맞는 USD 임포트 절차 사용.  
   - 블로킹만 빠르게 보려면 **glTF 경로만** 써도 됨.

4. **검증**  
   - **World Settings / 레벨**에서 **World Origin** 근처에 바닥·벽이 보이는지.  
   - **1인칭 임시 Pawn**으로 들어가 스케일이 “사람 크기”와 맞는지 10초만 확인.

✅ 여기까지면 **“트레일러용 레벨 안에 블로킹 세트가 있다”** 상태.

---

## Phase 4 — 세트를 ‘게임처럼’ 보이게 (대부분 수작업 + 라이브러리)

1. **블로킹 큐브를 실제 메시로 교체** (모듈 프리팹, 메가스캔, 내부 에셋).
2. **머티리얼·데칼** (벽면, 바닥, 금속/콘크리트 등).
3. **라이팅**: 스카이, 포그, 반사 프로브, 시간대.
4. **소품** 배치.

🤖 *선택*: 절차적 배치 파라미터 제안, 이미지→PBR 실험 등 (별도 툴·정책).

---

## Phase 5 — 캐릭터·애니 (트레일러)

1. **캐릭터**를 레벨에 배치하거나 **스켈레탈 메시** + **애니메이션 시퀀스** 준비.  
2. **Level Sequence** 안에서 **Skeletal Mesh Actor**에 애니를 넣거나, **Control Rig / 시퀀서 트랙**으로 타이밍 맞춤.  
3. 30초 트레일러 **첫 파일럿**이면 캐릭터 없이 **환경 + 카메라만**으로도 충분히 “트레일러 구조” 연습 가능.

---

## Phase 6 — 카메라·컷 (Unreal: Level Sequence)

1. **Cinematics → Add Level Sequence** 로 시퀀서 생성.  
2. 시퀀스에 **Cine Camera Actor** 추가 (또는 기존 카메라를 바인딩).  
3. **30초 타임라인**에 맞춰:  
   - **컷 A**: 와이드 establishing (예: 0~8s)  
   - **컷 B**: 푸시 인 / 패닝 (예: 8~18s)  
   - **컷 C**: 디테일 or 리빌 (예: 18~30s)  
4. **렌즈·포커스·조위**는 시퀀서 트랙에서 키프레임.  
5. **서브시퀀스**로 샷 나누기(선택) — 나중에 MRQ에 넣기 편함.

---

## Phase 7 — `.mov` 출력 (Movie Render Queue)

**트레일러 권장 경로: MRQ** (반복 렌더·안티앨리어싱·모션블러 제어에 유리).

1. **Window → Cinematics → Movie Render Queue** 열기.  
2. **+ Render** 로 잡 추가 → **Map** = 현재 레벨, **Sequence** = 위 Level Sequence.  
3. **출력 설정**  
   - **해상도**: 1920×1080(또는 4K 테스트는 나중에).  
   - **프레임레이트**: 24fps(영화) 또는 30fps(웹 트레일러 흔함).  
   - **포맷**: **ProRes** 또는 **PNG 시퀀스** → 후편에서 `.mov`로 래핑.  
     - macOS에서 **직접 `.mov`** 를 쓰는 프리셋이 있으면 그걸로도 가능(UE/플러그인 버전 의존).  
4. **프리셋 저장** 후 짧은 구간(예: 5초)만 **테스트 렌더** → 깨짐 없으면 풀 30초.  

**빠른 대안**: 품질보다 속도면 **시퀀서 뷰포트 + 화면 녹화**도 가능하지만, **납품형 트레일러**에는 MRQ 쪽이 맞는 경우가 많음.

---

## Phase 8 — 30초 트레일러 후반 (편집·사운드)

1. MRQ가 **이미지 시퀀스**면 Premiere / DaVinci 등에서 **30초 타임라인**으로 모으고 **`.mov`보내기**.  
2. **사운드**: 임시로도 **환경음 + 한 번 붙는 히트(8~12초)** 정도만 있어도 “트레일러” 체감이 크게 올라감.  
3. **컬러**: 첫 패스는 엔진 **Post Process** 로 맞추고, 편집에서는 미세 조정만.

---

## 이 레포가 담당하는 구간

**Phase 1 → 2 → 3의 “블로킹 입성”**까지가 `setlab`과 직접 맞닿습니다.  
`inzoi-test.mov` 수준의 최종 화면은 **Phase 4~8** 비중이 훨씬 큽니다.

---

## 다음에 같이 할 수 있는 것

- **UE 5.7** 에디터 스크린 기준으로 **Import Into Level vs Content Browser 임포트** 중 어떤 걸 썼는지에 맞춰, 다음 단계(레벨에 루트 액터 정리 등)만 더 촘촘히 적기.
- `set_spec.json` → **Unreal 모듈 에셋 경로 매핑 테이블** (블로킹 큐브를 진짜 세트 메시로 바꾸는 단계).

**공식 참고 (5.7)**  
- [Importing glTF Files into Unreal Engine](https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-gltf-files-into-unreal-engine) (Epic Developer Documentation)
