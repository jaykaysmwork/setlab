"""Shared, synchronized read/modify/write for ``meshes/_asset_urls.json``.

Multiple daemon threads / event loops (Rodin mesh generation, material
enhancement) write the same ``_asset_urls.json``. Without coordination this
causes lost updates and torn-read ``JSONDecodeError``s.

This module owns the *single* process-wide lock and performs every mutation as
a locked read-modify-write with an atomic ``os.replace`` swap.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict

# The one and only lock guarding _asset_urls.json mutations across the process.
_LOCK = threading.Lock()


def _urls_path_from_meshes_dir(meshes_dir: Path) -> Path:
    return Path(meshes_dir) / "_asset_urls.json"


def _read_urls(urls_file: Path) -> Dict[str, str]:
    try:
        return json.loads(urls_file.read_text())
    except (OSError, ValueError):
        return {}


def load_asset_urls(out_dir: Path) -> Dict[str, str]:
    """Read ``out_dir/meshes/_asset_urls.json`` (returns ``{}`` on any error)."""
    urls_file = Path(out_dir) / "meshes" / "_asset_urls.json"
    with _LOCK:
        return _read_urls(urls_file)


def save_asset_url(meshes_dir: Path, module_id: str, asset_url: str) -> None:
    """Atomically merge ``{module_id: asset_url}`` into ``meshes_dir/_asset_urls.json``."""
    urls_file = _urls_path_from_meshes_dir(meshes_dir)
    with _LOCK:
        existing = _read_urls(urls_file)
        existing[module_id] = asset_url
        directory = urls_file.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="_asset_urls.", suffix=".tmp", dir=str(directory)
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(existing, indent=2))
            os.replace(tmp_path, urls_file)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
