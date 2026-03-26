"""AI material enhancement — re-texture 3D assets via Hyper3D Rodin texture-only API.

Uses ``POST /api/v2/rodin_texture_only`` (PBR, GLB out). Requires per module:
  - A GLB file (local ``meshes/<id>.glb`` or downloadable from ``_asset_urls.json``)
  - A reference image: ``images/<id>/front.png`` (or .jpg) if present, else
    ``image_gen.generate_texture_reference_png_bytes`` (``IMAGE_GEN_BACKEND``:
    ``flux`` + ``FLUX_API_KEY``, or ``google`` + ``GOOGLE_API_KEY``).

Docs: https://developer.hyper3d.ai/api-specification/generate-texture

Auth: ``RODIN_API_KEY`` or ``HYPER3D_API_KEY`` (same as mesh generation).
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

RODIN_API_BASE = os.environ.get("RODIN_API_BASE", "https://api.hyper3d.com/api/v2")
POLL_INTERVAL = float(os.environ.get("RODIN_POLL_INTERVAL", "5.0"))
ENHANCE_TIMEOUT = float(os.environ.get("RODIN_TEXTURE_TIMEOUT", "900"))
MAX_CONCURRENT = int(
    os.environ.get(
        "MATERIAL_RODIN_CONCURRENCY",
        os.environ.get("RODIN_CONCURRENCY", "5"),
    )
)
MAX_MODEL_BYTES = int(os.environ.get("RODIN_TEXTURE_MAX_MODEL_MB", "10")) * 1024 * 1024
TEXTURE_RESOLUTION = os.environ.get("RODIN_TEXTURE_RESOLUTION", "High")

WEATHERING_PRESETS: Dict[str, str] = {
    "medieval_stone": (
        "Weathered medieval stone masonry with subtle moss growth in crevices, "
        "fine cracks, dust deposits, and uneven surface aging. "
        "Natural limestone color with slight discoloration from centuries of exposure."
    ),
    "aged_wood": (
        "Aged wood with visible grain patterns, slight warping, "
        "dry gray-brown patina from sun exposure, small splinters, "
        "and darkened knots. Authentic old-growth timber appearance."
    ),
    "rusty_metal": (
        "Oxidized iron with layered rust patina, flaking paint residue, "
        "pitting corrosion, and warm orange-brown surface deposits. "
        "Metallic sheen visible only at wear points."
    ),
    "worn_brick": (
        "Weathered clay brick with efflorescence salt deposits, "
        "eroded mortar joints, slight spalling, and color variation "
        "from kiln firing irregularities. Historical building facade."
    ),
    "generic_weathered": (
        "Realistically weathered and aged surface with natural wear patterns, "
        "subtle dirt accumulation, micro-cracks, and environmental patina. "
        "Photorealistic film-quality detail."
    ),
}


def _rodin_key() -> str:
    key = os.environ.get("RODIN_API_KEY") or os.environ.get("HYPER3D_API_KEY", "")
    if not key:
        raise RuntimeError(
            "RODIN_API_KEY (or HYPER3D_API_KEY) not set. "
            "Required for rodin_texture_only — https://developer.hyper3d.ai/"
        )
    return key


def _load_asset_urls(out_dir: Path) -> Dict[str, str]:
    urls_file = out_dir / "meshes" / "_asset_urls.json"
    if urls_file.exists():
        return json.loads(urls_file.read_text())
    return {}


def _save_asset_url(meshes_dir: Path, module_id: str, asset_url: str) -> None:
    urls_file = meshes_dir / "_asset_urls.json"
    existing = json.loads(urls_file.read_text()) if urls_file.exists() else {}
    existing[module_id] = asset_url
    urls_file.write_text(json.dumps(existing, indent=2))


async def _load_glb_bytes(
    client: httpx.AsyncClient, out_dir: Path, module_id: str, asset_urls: Dict[str, str]
) -> Optional[bytes]:
    path = out_dir / "meshes" / f"{module_id}.glb"
    if path.is_file():
        data = path.read_bytes()
    elif module_id in asset_urls:
        url = asset_urls[module_id]
        resp = await client.get(url, timeout=120.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.content
    else:
        return None

    if len(data) > MAX_MODEL_BYTES:
        logger.error(
            "[Material] %s: GLB too large for rodin_texture_only (>%d MB)",
            module_id,
            MAX_MODEL_BYTES // (1024 * 1024),
        )
        return None
    return data


def _find_front_image(out_dir: Path, module_id: str) -> Optional[Path]:
    base = out_dir / "images" / module_id
    for name in ("front.png", "front.jpg", "front.jpeg"):
        p = base / name
        if p.is_file():
            return p
    return None


async def _reference_image_bytes(
    out_dir: Path, module_id: str, texture_prompt: str, module_description: str
) -> Optional[Tuple[bytes, str, str]]:
    img_path = _find_front_image(out_dir, module_id)
    if img_path:
        data = img_path.read_bytes()
        mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        return data, img_path.name, mime

    from setlab.image_gen import generate_texture_reference_png_bytes

    def _synth_ref() -> Optional[bytes]:
        try:
            return generate_texture_reference_png_bytes(
                texture_prompt, context=module_description
            )
        except Exception as e:
            logger.error("[Material] synthetic reference image failed: %s", e)
            return None

    png = await asyncio.to_thread(_synth_ref)
    if not png:
        return None
    return png, "reference.png", "image/png"


async def _hyper3d_poll(client: httpx.AsyncClient, subscription_key: str) -> None:
    import time

    start = time.monotonic()
    headers = {
        "Authorization": f"Bearer {_rodin_key()}",
        "Content-Type": "application/json",
    }
    while True:
        resp = await client.post(
            f"{RODIN_API_BASE}/status",
            headers=headers,
            json={"subscription_key": subscription_key},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Rodin texture status error: {data.get('error')}")

        jobs = data.get("jobs") or []
        if not jobs:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        statuses = [j.get("status", "") for j in jobs]
        if any(s == "Failed" for s in statuses):
            raise RuntimeError("Rodin texture-only job failed")
        if all(s == "Done" for s in statuses):
            return

        if time.monotonic() - start > ENHANCE_TIMEOUT:
            raise TimeoutError("Rodin texture-only timed out")

        await asyncio.sleep(POLL_INTERVAL)


async def _hyper3d_download_glb_url(client: httpx.AsyncClient, task_uuid: str) -> Optional[str]:
    resp = await client.post(
        f"{RODIN_API_BASE}/download",
        headers={
            "Authorization": f"Bearer {_rodin_key()}",
            "Content-Type": "application/json",
        },
        json={"task_uuid": task_uuid},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"Rodin texture download error: {data.get('error')}")
    items = list(data.get("list") or [])
    glbs = [it for it in items if str(it.get("name", "")).lower().endswith(".glb")]
    if not glbs:
        return None
    for it in glbs:
        n = str(it.get("name", "")).lower()
        if "preview" not in n:
            return it.get("url")
    return glbs[0].get("url")


async def _submit_texture_only(
    client: httpx.AsyncClient,
    model_bytes: bytes,
    model_filename: str,
    image_bytes: bytes,
    image_filename: str,
    image_mime: str,
    prompt: str,
) -> Tuple[str, str]:
    files: List[Any] = [
        ("model", (model_filename, model_bytes, "model/gltf-binary")),
        ("image", (image_filename, image_bytes, image_mime)),
        ("prompt", prompt),
        ("material", "PBR"),
        ("geometry_file_format", "glb"),
        ("resolution", TEXTURE_RESOLUTION),
    ]
    resp = await client.post(
        f"{RODIN_API_BASE}/rodin_texture_only",
        headers={"Authorization": f"Bearer {_rodin_key()}"},
        files=files,
        timeout=180.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(
            f"rodin_texture_only submit failed: {data.get('error')} — {data.get('message', '')}"
        )
    task_uuid = data.get("uuid")
    jobs = data.get("jobs") or {}
    sub_key = jobs.get("subscription_key")
    if not task_uuid or not sub_key:
        raise RuntimeError(f"rodin_texture_only: bad response: {data}")
    return str(task_uuid), str(sub_key)


async def _enhance_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    module: Dict[str, Any],
    prompt: str,
    out_dir: Path,
    asset_urls: Dict[str, str],
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[str]:
    module_id = module["id"]
    desc = module.get("description") or module.get("asset", "")

    async with semaphore:
        try:
            if on_progress:
                on_progress(module_id, "loading", 5)

            glb_bytes = await _load_glb_bytes(client, out_dir, module_id, asset_urls)
            if not glb_bytes:
                logger.warning("[Material] %s: no GLB on disk or URL", module_id)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            ref = await _reference_image_bytes(out_dir, module_id, prompt, desc)
            if not ref:
                logger.warning(
                    "[Material] %s: no reference image (add images/%s/front.* or configure "
                    "IMAGE_GEN_BACKEND + FLUX_API_KEY / GOOGLE_API_KEY)",
                    module_id,
                    module_id,
                )
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            image_bytes, image_name, image_mime = ref

            if on_progress:
                on_progress(module_id, "texturing", 25)

            task_uuid, sub_key = await _submit_texture_only(
                client,
                glb_bytes,
                f"{module_id}.glb",
                image_bytes,
                image_name,
                image_mime,
                prompt,
            )
            logger.info("[Material] %s → rodin_texture_only task %s", module_id, task_uuid)

            await _hyper3d_poll(client, sub_key)

            if on_progress:
                on_progress(module_id, "downloading", 80)

            new_url = await _hyper3d_download_glb_url(client, task_uuid)
            if not new_url:
                logger.warning("[Material] %s: no GLB in download list", module_id)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            target = out_dir / "meshes" / f"{module_id}.glb"
            resp = await client.get(new_url, timeout=300.0, follow_redirects=True)
            resp.raise_for_status()
            target.write_bytes(resp.content)
            _save_asset_url(out_dir / "meshes", module_id, new_url)

            logger.info(
                "[Material] %s enhanced → %s (%d bytes)",
                module_id,
                target.name,
                target.stat().st_size,
            )
            if on_progress:
                on_progress(module_id, "done", 100)
            return str(target)

        except Exception as e:
            logger.error("[Material] %s error: %s", module_id, e)
            if on_progress:
                on_progress(module_id, "failed", 100)
            return None


async def enhance_materials(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    style: str = "generic_weathered",
    custom_prompt: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Optional[str]]:
    """Re-texture models with Rodin ``rodin_texture_only`` (PBR GLB).

    Each module needs a GLB (``meshes/<id>.glb`` or URL in ``_asset_urls.json``)
    and a reference image (``images/<id>/front.*`` or image_gen backend credentials).
    """
    _rodin_key()

    prompt = custom_prompt or WEATHERING_PRESETS.get(
        style, WEATHERING_PRESETS["generic_weathered"]
    )
    asset_urls = _load_asset_urls(out_dir)

    to_process: List[Dict[str, Any]] = []
    for m in modules:
        mid = m["id"]
        if (out_dir / "meshes" / f"{mid}.glb").is_file() or mid in asset_urls:
            to_process.append(m)

    if not to_process:
        logger.warning("[Material] No GLB sources found — skipping enhancement")
        return {m["id"]: None for m in modules}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient() as client:
        coros = [
            _enhance_one(client, semaphore, m, prompt, out_dir, asset_urls, on_progress)
            for m in to_process
        ]
        results = await asyncio.gather(*coros)

    out: Dict[str, Optional[str]] = {m["id"]: None for m in modules}
    for m, r in zip(to_process, results):
        out[m["id"]] = r
    return out
