# Unity + Unreal, **3D 세트**를 **거의 실시간**으로 보기

## 먼저 맞춰 둘 기대치

- **한 번의 클릭으로 Unity·Unreal 뷰포트가 동시에 같은 프레임으로 갱신**되는 “완전 실시간 링크”는 **이 레포 기본만으로는 없음**. 보통은 **중간 산출물 하나**(`set.gltf` 등)를 두 엔진이 **각각 읽는** 구조입니다.
- **“실시간에 가깝게”** = `setlab` 이 파일을 갱신한 뒤 **수 초 안에** 양쪽에서 다시 보이게 **루프를 짧게** 만드는 것 (자동 복사 + Reimport / 에디터 스크립트).

---

## 추천 구조: **하나의 진실 소스 → 두 엔진**

```
my_brief.txt → setlab.run → out/live/set.gltf  (+ set_spec.json)
                              ↓                        ↓
                    Unreal (Import/Reimport)    Unity (Import/Reimport)
```

- **포맷:** **glTF 2.0** 이 Unity/Unreal 둘 다 받기 쉬운 **공통어**에 가깝습니다.  
- **USD** 를 쓰면 언리얼 쪽은 강하지만, Unity는 **패키지·버전**에 따라 한 단계 더 필요할 수 있습니다. **처음엔 glTF 고정**을 추천합니다.

---

## Unreal 쪽 (짧은 루프)

1. **Import Into Level** 또는 `Content/Incoming/set.gltf` 첫 임포트.  
2. 웹 **Deploy** 는 `set.gltf` + `Saved/SetLab/set_spec.json` 와 함께 **`Content/Incoming/SetLab/meshes/*.glb`**(Tripo HD)까지 복사합니다. `scripts/ue_set_watcher.py` 가 이 GLB들을 임포트한 뒤 스펙으로 배치합니다.  
3. `setlab` 이 `set.gltf` 를 덮어쓸 때마다:  
   - `scripts/copy_set_gltf_to_unreal.sh` 로 프로젝트 `Content` 로 복사 → **Reimport**  
   - 또는 `docs/UNREAL_AUTO_IMPORT_SETUP.md` 의 **Python 폴링**으로 Reimport 자동화.

**에디터가 켜져 있어야** 갱신이 보입니다.

---

## Unity 쪽 (필요한 것)

1. **glTF 임포트**  
   - Unity 버전에 맞는 패키지 설치 (예: 프로젝트 문서에 나온 **glTFast** 등).  
2. `set.gltf` 를 **Assets** 아래 폴더(예: `Assets/Incoming/`)에 넣고 임포트.  
3. 씬에 프리팹/모델을 배치.  
4. 파일이 바뀌면:  
   - 해당 에셋 **Reimport**, 또는  
   - **에디터 스크립트**로 `AssetDatabase.ImportAsset` 호출 (자동화 시).

Unity 쪽 복사용 셸 예시 (경로만 본인 것으로):

```bash
cp /path/to/3D-test/out/live/set.gltf "/path/to/MyUnityProject/Assets/Incoming/set.gltf"
```

---

## “실시간”을 더 당기려면 (같은 방향)

| 아이디어 | 효과 |
|----------|------|
| **한 스크립트가 glTF 를 UE·Unity 폴더에 동시에 복사** | 터미널 한 번 → 두 프로젝트에 파일만 동시 갱신 |
| **각 에디터에서 Reimport 자동화** | 클릭 제거, 체감이 “거의 실시간”에 가까워짐 |
| **Play 모드에서 런타임 glTF 로드** | 에디터 임포트 없이 보기 — 구현 난이도↑, 디버깅↑ |

---

## Ollama vs Gemini 와의 관계

- **엔진에서 바로 보이게 하는 것**과 무관하게, **누가 JSON/설계 텍스트를 쓰느냐**는 별층입니다.  
- **실시간 프리뷰**를 막는 병목은 보통 **“파일 임포트 루프”**이지 Ollama 자체가 아닙니다.

---

## 요약

- **Unity + Unreal 동시** = **`set.gltf` 하나를 두 프로젝트가 공유**하는 게 현실적입니다.  
- **바로 보기** = **짧은 재임포트 루프**(복사 + Reimport 또는 에디터 자동화)까지 포함해 설계해야 합니다.  
- 이 레포는 **`set.gltf` 생성까지**가 본업이고, **양쪽 동시 복사 스크립트**는 원하면 `copy_set_gltf_to_unreal.sh` 와 같은 식으로 Unity 경로를 한 줄 더 추가하면 됩니다.
