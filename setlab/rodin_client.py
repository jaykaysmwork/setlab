"""Hyper3D Rodin Gen-2 client — text-to-3D and multi-image-to-3D via REST API.

``setlab.studio3d_client`` is a thin forwarder to this module for old imports only.

Docs:
  https://developer.hyper3d.ai/api-specification/rodin-generation
  https://developer.hyper3d.ai/get-started/minimal-example
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

API_BASE = os.environ.get("RODIN_API_BASE", "https://api.hyper3d.com/api/v2")
MAX_CONCURRENT = int(os.environ.get("RODIN_CONCURRENCY", "10"))
POLL_INTERVAL = float(os.environ.get("RODIN_POLL_INTERVAL", "2.0"))
GENERATE_TIMEOUT = float(os.environ.get("RODIN_TIMEOUT", "900"))

# Gen-2 defaults (see Hyper3D minimal Gen-2 example)
RODIN_TIER = os.environ.get("RODIN_TIER", "Gen-2")
RODIN_MESH_MODE = os.environ.get("RODIN_MESH_MODE", "Raw")
RODIN_MATERIAL = os.environ.get("RODIN_MATERIAL", "PBR")
RODIN_GEOMETRY_FORMAT = os.environ.get("RODIN_GEOMETRY_FORMAT", "glb")
# API doc: quality_override typically 2000–200000; Gen-2 examples may allow higher — cap via env.
RODIN_QUALITY_OVERRIDE_RAW = os.environ.get("RODIN_QUALITY_OVERRIDE", "").strip()
RODIN_QUALITY_CAP = int(os.environ.get("RODIN_QUALITY_OVERRIDE_MAX", "200000"), 10)


def _api_key() -> str:
    key = os.environ.get("RODIN_API_KEY") or os.environ.get("HYPER3D_API_KEY", "")
    if not key:
        raise RuntimeError(
            "RODIN_API_KEY (or HYPER3D_API_KEY) not set. "
            "Get one at https://developer.hyper3d.ai/"
        )
    return key


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_api_key()}"}


def _quality_override_for_request() -> Optional[str]:
    """Return clamped quality_override string, or None to omit (API default quality)."""
    if not RODIN_QUALITY_OVERRIDE_RAW:
        return None
    try:
        n = int(RODIN_QUALITY_OVERRIDE_RAW, 10)
    except ValueError:
        logger.warning("Invalid RODIN_QUALITY_OVERRIDE=%r, omitting", RODIN_QUALITY_OVERRIDE_RAW)
        return None
    lo = 2000
    hi = max(lo, RODIN_QUALITY_CAP)
    n = max(lo, min(n, hi))
    return str(n)


def _rodin_plain_multipart_fields() -> List[Tuple[str, Tuple[None, str]]]:
    """Non-file parts as (name, (None, value)) — matches Hyper3D requests/httpx examples."""
    out: List[Tuple[str, Tuple[None, str]]] = [
        ("tier", (None, RODIN_TIER)),
        ("mesh_mode", (None, RODIN_MESH_MODE)),
        ("material", (None, RODIN_MATERIAL)),
        ("geometry_file_format", (None, RODIN_GEOMETRY_FORMAT)),
    ]
    q = _quality_override_for_request()
    if q is not None:
        out.append(("quality_override", (None, q)))
    return out


def _raise_for_rodin_response(resp: httpx.Response, context: str) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        err = body.get("error")
        msg = body.get("message")
        detail = f"{err or 'HTTP'}: {msg or body}"
    except Exception:
        detail = (resp.text or "")[:1200] or resp.reason_phrase
    logger.error("[%s] Rodin HTTP %s — %s", context, resp.status_code, detail)
    raise RuntimeError(f"Rodin {context}: HTTP {resp.status_code} — {detail}")


async def _submit_text_to_3d(client: httpx.AsyncClient, prompt: str) -> Tuple[str, str]:
    """POST /rodin (text-only multipart). Returns (task_uuid, subscription_key)."""
    from setlab.image_gen import clean_description_for_3d

    clean_prompt = clean_description_for_3d(prompt, max_len=200)
    files: List[Any] = [
        ("prompt", (None, clean_prompt)),
    ]
    files.extend(_rodin_plain_multipart_fields())
    resp = await client.post(
        f"{API_BASE}/rodin",
        headers=_auth_headers(),
        files=files,
        timeout=120.0,
    )
    _raise_for_rodin_response(resp, "submit text")
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"Rodin submit failed: {data.get('error')} — {data.get('message', '')}")
    task_uuid = data.get("uuid")
    jobs = data.get("jobs") or {}
    sub_key = jobs.get("subscription_key")
    if not task_uuid or not sub_key:
        raise RuntimeError(f"Rodin submit: missing uuid or subscription_key: {data}")
    return str(task_uuid), str(sub_key)


async def _submit_multiview_to_3d(
    client: httpx.AsyncClient, image_dir: Path, description: str = ""
) -> Tuple[str, str]:
    """POST /rodin with multiple views (concat mode). Returns (task_uuid, subscription_key)."""
    from setlab.image_gen import clean_description_for_3d

    multipart: List[Any] = []
    order = ["front", "left", "back", "right"]
    for name in order:
        for ext, mime in ((".png", "image/png"), (".jpg", "image/jpeg")):
            p = image_dir / f"{name}{ext}"
            if p.exists():
                multipart.append(("images", (p.name, p.read_bytes(), mime)))
                break

    if not multipart:
        raise FileNotFoundError(f"No view images in {image_dir}")

    if description:
        clean = clean_description_for_3d(description, max_len=200)
        multipart.append(("prompt", (None, clean)))

    multipart.append(("condition_mode", (None, "concat")))
    multipart.extend(_rodin_plain_multipart_fields())

    resp = await client.post(
        f"{API_BASE}/rodin",
        headers=_auth_headers(),
        files=multipart,
        timeout=180.0,
    )
    _raise_for_rodin_response(resp, "submit multiview")
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"Rodin submit failed: {data.get('error')} — {data.get('message', '')}")
    task_uuid = data.get("uuid")
    jobs = data.get("jobs") or {}
    sub_key = jobs.get("subscription_key")
    if not task_uuid or not sub_key:
        raise RuntimeError(f"Rodin submit: missing uuid or subscription_key: {data}")
    return str(task_uuid), str(sub_key)


async def _poll_until_done(
    client: httpx.AsyncClient, subscription_key: str, timeout: float = GENERATE_TIMEOUT
) -> None:
    import time

    start = time.monotonic()
    while True:
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"Rodin timed out after {timeout:.0f}s")

        resp = await client.post(
            f"{API_BASE}/status",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json={"subscription_key": subscription_key},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Rodin status error: {data.get('error')}")

        jobs = data.get("jobs") or []
        if not jobs:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        statuses = [j.get("status", "") for j in jobs]
        if any(s == "Failed" for s in statuses):
            raise RuntimeError("Rodin generation failed (job status Failed)")
        if all(s == "Done" for s in statuses):
            return

        await asyncio.sleep(POLL_INTERVAL)


async def _download_results(
    client: httpx.AsyncClient, task_uuid: str
) -> List[dict]:
    resp = await client.post(
        f"{API_BASE}/download",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json={"task_uuid": task_uuid},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"Rodin download error: {data.get('error')}")
    return list(data.get("list") or [])


def _pick_glb_url(items: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    """Return (url, filename) for the best GLB in the download list."""
    glbs = [it for it in items if str(it.get("name", "")).lower().endswith(".glb")]
    if not glbs:
        return None, None
    # Prefer main model over preview-ish names if multiple
    for it in glbs:
        n = str(it.get("name", "")).lower()
        if "preview" not in n and "low" not in n:
            return it.get("url"), it.get("name")
    return glbs[0].get("url"), glbs[0].get("name")


async def _download_glb(client: httpx.AsyncClient, url: str, dest: Path) -> Path:
    resp = await client.get(url, timeout=300.0, follow_redirects=True)
    resp.raise_for_status()
    if resp.content[:4] != b"glTF":
        raise RuntimeError(
            f"GLB 다운로드 검증 실패: 응답이 glTF 매직바이트로 시작하지 않습니다 "
            f"({len(resp.content)} bytes, url={url})."
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def _save_asset_url(meshes_dir: Path, module_id: str, asset_url: str) -> None:
    # Delegate to the shared, locked, atomic writer (one process-wide lock).
    from setlab._asset_urls import save_asset_url

    save_asset_url(meshes_dir, module_id, asset_url)


async def _generate_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    module_id: str,
    description: str,
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[str]:
    async with semaphore:
        try:
            if on_progress:
                on_progress(module_id, "queued", 0)

            task_uuid, sub_key = await _submit_text_to_3d(client, description)
            logger.info("[Rodin] %s → task %s", module_id, task_uuid)

            if on_progress:
                on_progress(module_id, "generating", 10)

            await _poll_until_done(client, sub_key)

            items = await _download_results(client, task_uuid)
            url, _name = _pick_glb_url(items)
            if not url:
                logger.warning("[Rodin] %s: no GLB in download list", module_id)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            meshes_dir = out_dir / "meshes"
            target = meshes_dir / f"{module_id}.glb"
            await _download_glb(client, url, target)
            _save_asset_url(meshes_dir, module_id, url)

            logger.info(
                "[Rodin] %s → %s (%d bytes)",
                module_id,
                target.name,
                target.stat().st_size,
            )
            if on_progress:
                on_progress(module_id, "done", 100)
            return str(target)

        except Exception as e:
            logger.error("[Rodin] %s error: %s", module_id, e)
            if on_progress:
                on_progress(module_id, "failed", 100)
            return None


async def generate_meshes(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Optional[str]]:
    """Text-to-3D per module via Rodin Gen-2."""
    _api_key()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient() as client:
        coros = [
            _generate_one(
                client,
                semaphore,
                m["id"],
                m.get("description") or m.get("asset", "generic object"),
                out_dir,
                on_progress,
            )
            for m in modules
        ]
        results = await asyncio.gather(*coros)
    return {m["id"]: r for m, r in zip(modules, results)}


async def _generate_one_hd(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    module_id: str,
    description: str,
    image_dir: Path,
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[str]:
    async with semaphore:
        try:
            if on_progress:
                on_progress(module_id, "uploading", 10)

            task_uuid, sub_key = await _submit_multiview_to_3d(
                client, image_dir, description=description
            )
            logger.info("[Rodin HD] %s → task %s", module_id, task_uuid)

            if on_progress:
                on_progress(module_id, "generating_3d", 30)

            await _poll_until_done(client, sub_key)

            items = await _download_results(client, task_uuid)
            url, _name = _pick_glb_url(items)
            if not url:
                logger.warning("[Rodin HD] %s: no GLB in download list", module_id)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            meshes_dir = out_dir / "meshes"
            target = meshes_dir / f"{module_id}.glb"
            await _download_glb(client, url, target)
            _save_asset_url(meshes_dir, module_id, url)

            if on_progress:
                on_progress(module_id, "done", 100)
            return str(target)

        except Exception as e:
            logger.error("[Rodin HD] %s error: %s", module_id, e)
            if on_progress:
                on_progress(module_id, "failed", 100)
            return None


async def generate_hd_meshes(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Optional[str]]:
    """Multi-view image-to-3D via Rodin Gen-2 (condition_mode=concat).

    Expects images at out_dir/images/{module_id}/{front,left,back,right}.png|.jpg
    """
    _api_key()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with httpx.AsyncClient() as client:
        coros = [
            _generate_one_hd(
                client,
                semaphore,
                m["id"],
                m.get("description", ""),
                out_dir / "images" / m["id"],
                out_dir,
                on_progress,
            )
            for m in modules
        ]
        results = await asyncio.gather(*coros)
    return {m["id"]: r for m, r in zip(modules, results)}
