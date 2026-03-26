# Unreal에서 모듈을 **하나씩 드래그하지 않기**

`set_spec.json` / `set.gltf` 둘 다 **“한 번에 배치”**가 가능합니다. 수동 드래그는 **임시 확인용**이지 유일한 방법이 아닙니다.

---

## 방법 A — glTF를 **레벨 전체**로 넣기 (코드 없음)

1. 에디터에서 **File → Import Into Level…**  
2. `set.gltf` 선택.  
3. Interchange가 **씬 그래프대로 액터를 한 번에** 스폰하는 경우가 많습니다.

**Content Browser에 StaticMesh만 생기고** 레벨은 비어 있었다면, 보통 **일반 Import(드래그)** 만 해서 **메시 자산만** 들어온 상태일 수 있습니다. 그때는 **Import Into Level**을 한 번 시도해 보세요.

---

## 방법 B — `set_spec.json`으로 **에디터 Python** 자동 스폰

이미 `Content/set/StaticMeshes` 아래에 **모듈 메시**가 있다면, JSON의 `position` / `rotation_deg` / `scale` 로 **StaticMeshActor**를 루프로 찍을 수 있습니다.

1. **Edit → Plugins** 에서 **Python Editor Script Plugin** (및 필요 시 **Editor Scripting Utilities**) 활성 → 에디터 재시작.  
2. 프로젝트에 `set_spec.json` 을 복사해 두거나, **절대 경로**를 스크립트에 넣습니다.  
3. 에디터 하단 **Output Log** 옆 **Python** 또는 **Tools → Execute Python Script** 로 아래 스크립트 실행.

**중요**

- Unreal 에디터 트랜스폼은 기본이 **센티미터(cm)** 인 경우가 많습니다. 스크립트는 **미터 → cm (`* 100`)** 를 적용합니다. 프로젝트가 **미터**로 통일돼 있으면 그에 맞게 `SCALE_M_TO_UU` 만 조정하세요.  
- `ASSET_MAP` 의 키는 JSON의 **`asset`** 문자열과 맞추고, 값은 **본인 프로젝트의 Static Mesh 소프트 오브젝트 경로**로 바꿉니다. (Content Browser에서 메시 **우클릭 → Copy Reference**)

스크립트: `scripts/unreal_spawn_from_spec.py`

---

## 방법 C — **블루프린트 / C++ 빌더**

`set_spec.json`을 **런타임 또는 에디터**에서 읽어 스폰하는 전용 **Builder** 블루프린트를 두는 방식. 팀·반복이 많을 때 선호됩니다.

---

## AI의 역할과 자동 배치

- **AI(LLM)** 는 **“어디에 무엇을 둘지”** 를 JSON으로 빠르게 바꿉니다.  
- **자동 배치**는 그 JSON을 소비하는 **엔진 쪽 루프(Import Into Level / Python / BP)** 가 담당합니다.  
- 둘을 붙이면 **브리프만 바꿔도 전체 레이아웃을 다시 깔 수 있는** 흐름이 됩니다.
