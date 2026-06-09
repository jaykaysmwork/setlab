# 처음부터 다시 — **뭐가 자동이고 뭐가 수동인지**

## 솔직한 정리

| 단계 | 자동? | 설명 |
|------|--------|------|
| 브리프 → AI가 JSON 스펙 생성 | ✅ (터미널 명령 한 번) | Ollama + `setlab.run` |
| JSON → `set.gltf` / `set.usda` 파일 쓰기 | ✅ | 같은 명령 안에서 |
| 그 파일이 **Unreal 안으로 들어감** | ❌ (기본) | **임포트 / 복사 / Reimport** 는 사람 손 |
| 레벨에 배치·이동 | ❌ (기본) | **드래그** 또는 **Import Into Level** |
| 브리프 바뀔 때마다 뷰포트가 **저절로** 갱신 | ❌ | **폴더 감시 + Python** 등을 **추가로** 붙이지 않는 한 안 됨 |

**그래서** “자동으로 Unreal에 뜬다”가 아니라 **“자동으로 디스크에 glTF가 생긴다”** 까지가 이 레포의 기본 범위입니다.

---

## 처음부터 다시 할 때 추천 순서 (깔끔한 버전)

### 1) Unreal — **DMX 말고 Blank**

1. Epic Launcher → **새 프로젝트**  
2. 템플릿: **Blank** (또는 Film 계열, **DMX/VP 템플릿 아님**)  
3. 프로젝트 이름 정하고 **Create**

### 2) 레벨

1. **File → New Level → Empty Level**  
2. **Save As** → 예: `Maps/Blocking`  
3. **Project Settings → Maps & Modes** 에서 **Editor Startup Map** 을 `Blocking` 으로 (선택이지만 재실행 시 편함)

### 3) 이 레포 — 브리프 + 생성

```bash
cd /path/to/setlab
source .venv/bin/activate
python -m setlab.run my_brief.txt --out out/clean_run --backend ollama --model llama3.2
```

→ `out/clean_run/set.gltf` 생성 (여기까지가 **자동**)

### 4) Unreal — **씬 한 번에** (수동이지만 조각 드래그 최소화)

1. **File → Import Into Level…**  
2. `out/clean_run/set.gltf` 선택 → Import  

→ 레벨에 액터가 **한 번에** 생기는 경우가 많음 (**수동 클릭은 “파일 고르기” 수준**).

### 5) 이후 반복할 때 (여전히 수동이지만 짧게)

- 터미널에서 `setlab.run` 다시 → `set.gltf` 덮어쓰기  
- 언리얼에서 **해당 애셋 Reimport** (또는 **Import Into Level** 다시)  
→ **완전 무인은 아님**. 자동에 가깝게 하려면 `docs/UNREAL_AUTO_IMPORT_SETUP.md` 의 Python 폴링 등 **추가 작업**.

---

## 이전 프로젝트(MyProject + DMX)와 헷갈리지 않으려면

- **세트 실험용**은 위 **Blank 새 프로젝트**만 쓰는 편이 정신 건강에 좋음.  
- DMX 프로젝트는 **조명 무대**용으로 남겨 두고 분리.

---

## 한 문장

**AI = “파일과 숫자를 빨리 만든다”. Unreal에 “붙는 것”은 기본적으로 사람이 한두 번 눌러 준다.**  
**Import Into Level** 까지 쓰면 **조각을 하나하나 드래그하는 수동**은 크게 줄어든다.
