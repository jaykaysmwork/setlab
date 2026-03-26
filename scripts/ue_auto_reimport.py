# ─────────────────────────────────────────────────────────────────────────────
# Unreal Editor Python — 파일 감시 + 자동 Reimport
# ─────────────────────────────────────────────────────────────────────────────
# ❶ Unreal 에디터에서 한 번만 실행하면, 이후 set.gltf 가 바뀔 때마다 자동으로
#    같은 에셋을 다시 임포트합니다.
#
# 실행 방법 (에디터 안):
#   • Output Log 옆 Python 콘솔에서 실행, 또는
#   • Tools → Execute Python Script → 이 파일 선택
#
# 멈추려면 에디터를 닫거나, Python 콘솔에서:
#   ue_auto_reimport.stop()
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import os
import time

import unreal

# ── 설정 ──────────────────────────────────────────────────────────────────
# 감시할 glTF 파일의 절대 경로.
# prompt_to_viewport.sh / deploy 스크립트가 여기에 복사합니다.
# 본인 프로젝트에 맞게 수정하세요.
WATCH_FILE = os.path.join(
    unreal.Paths.project_content_dir(), "Incoming", "set.gltf"
)

# Reimport 시 glTF 를 넣을 Content 경로 (첫 임포트와 같은 위치).
DEST_PATH = "/Game/Incoming"

# 몇 초마다 파일 변경을 확인할지.
POLL_SECONDS = 2.0

# ── 내부 상태 ─────────────────────────────────────────────────────────────
_last_mtime: float = 0.0
_last_check: float = 0.0
_handle = None
_first_run: bool = True


def _reimport_gltf() -> None:
    """AssetImportTask 로 기존 에셋을 덮어쓰는(replace) 방식의 재임포트."""
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", WATCH_FILE)
    task.set_editor_property("destination_path", DEST_PATH)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    unreal.log("[SetLab] Auto-reimported set.gltf → %s" % DEST_PATH)


def _tick(delta_time: float) -> None:
    """매 에디터 프레임마다 호출되지만, POLL_SECONDS 간격으로만 실제 검사."""
    global _last_mtime, _last_check, _first_run

    now = time.time()
    if now - _last_check < POLL_SECONDS:
        return
    _last_check = now

    if not os.path.isfile(WATCH_FILE):
        return

    mtime = os.path.getmtime(WATCH_FILE)

    if _first_run:
        _last_mtime = mtime
        _first_run = False
        unreal.log("[SetLab] Watcher started — watching: %s" % WATCH_FILE)
        return

    if mtime <= _last_mtime:
        return

    _last_mtime = mtime
    unreal.log("[SetLab] File changed — reimporting…")
    _reimport_gltf()


def start() -> None:
    """감시 시작. 에디터에서 이 스크립트를 실행하면 자동으로 호출됨."""
    global _handle, _first_run
    if _handle is not None:
        unreal.log("[SetLab] Watcher already running.")
        return
    _first_run = True
    _handle = unreal.register_slate_post_tick_callback(_tick)
    unreal.log("[SetLab] Watcher registered (poll=%.1fs, file=%s)" % (POLL_SECONDS, WATCH_FILE))


def stop() -> None:
    """감시 중단."""
    global _handle
    if _handle is not None:
        unreal.unregister_slate_post_tick_callback(_handle)
        _handle = None
        unreal.log("[SetLab] Watcher stopped.")
    else:
        unreal.log("[SetLab] Watcher was not running.")


# 스크립트 실행 시 자동으로 감시 시작.
start()
