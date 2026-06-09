# 처음부터: **Unreal 먼저** 시작 가이드

AI·Python 파이프보다 **먼저 엔진을 고정**하고, 그다음 브리프 → `set.gltf` 를 넣는 순서입니다.

---

## 0. 준비 (한 번)

- **Epic Games Launcher** 설치 → **Unreal Engine** 원하는 버전 설치 (예: 5.7 또는 설치된 최신).  
- **macOS**: 셰이더 컴파일 오류가 나면 터미널에서  
  `xcodebuild -downloadComponent MetalToolchain`  
  (이미 했다면 생략)

---

## 1. 새 Unreal 프로젝트 만들기

1. Launcher 실행 → **Unreal Engine** → **Launch** 또는 **새 프로젝트**.  
2. **템플릿**  
   - **Film / Television** 또는 **Blank** 추천.  
   - **DMX / Virtual Production** 전용 템플릿은 **이번 목적(세트 블로킹·트레일러)** 에는 피하면 화면이 단순합니다.  
3. **프로젝트 이름·경로** 지정 → **Create**.  
4. 에디터가 열리면 **레벨 저장** (File → Save Current) — 예: `Maps/Blocking`.

---

## 2. 플러그인 확인 (glTF 임포트)

1. **Edit → Plugins**  
2. 검색: `Interchange`, `glTF` — **Enabled** (필요 시 재시작).  
3. (선택) **Python Editor Script Plugin** — 나중에 JSON 자동 스폰을 쓸 때만.

---

## 3. 이 레포에서 브리프 → `set.gltf` 생성

터미널 (이 저장소):

```bash
cd /path/to/setlab
source .venv/bin/activate
# 브리프 파일을 직접 쓴 뒤:
python -m setlab.run my_brief.txt --out out/unreal_run --backend ollama --model llama3.2
```

산출물:

- `out/unreal_run/set.gltf` (+ 같은 폴더의 `.bin` 등)  
- `out/unreal_run/set_spec.json`

**Ollama**가 꺼져 있으면 안 됩니다 (`brew services start ollama` 등).

---

## 4. Unreal로 **한 번에** 넣기 (드래그 N번 X)

1. 에디터에서 **File → Import Into Level…**  
2. Finder에서 **`set.gltf`** 선택 (`.gltf`와 같은 폴더에 있는 `.bin`·텍스처가 함께 있어야 함).  
3. Interchange 창에서 **Import** — **씬이 레벨에 한 번에** 들어오는지 확인.

**안 되면**: Content Browser로 `set.gltf`만 드래그 → **메시만** 생긴 것이므로, 가능하면 **Import Into Level** 을 다시 시도하거나 `docs/UNREAL_AUTO_PLACEMENT.md` 의 Python 경로 참고.

---

## 5. 확인

- 뷰포트에서 **블로킹 메시**가 보이는지, **스케일**이 말이 되는지 (너무 크면 Interchange 스케일 조정).  
- **Save All** (Content Browser의 * 표시 없애기).

---

## 6. 그다음 (트레일러 목표)

- **Cinematics → Add Level Sequence** → 30초 카메라.  
- 고품질 출력: **Movie Render Queue** — `WALKTHROUGH_MOV_PIPELINE.md` Phase 6~7.

---

## 순서 요약

```
Unreal 새 프로젝트 → 플러그인 확인 → (터미널) 브리프 + setlab → set.gltf
    → Import Into Level → 저장 → 시퀀서/MRQ
```

이제부터는 **항상 “엔진 먼저, 데이터는 그다음”** 으로 맞추면 됩니다.
