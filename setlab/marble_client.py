"""World Labs Marble client — text-to-3D-environment via REST API.

Generates full explorable 3D environments from a text prompt using the
World Labs Marble API. Outputs include a collider mesh (GLB), Gaussian
Splat (SPZ), and panorama image.

API docs: https://docs.worldlabs.ai/api/reference/worlds/generate
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int], None]

API_BASE = "https://api.worldlabs.ai"
DEFAULT_MODEL = "Marble 0.1-plus"
POLL_INTERVAL = 10.0
GENERATE_TIMEOUT = 900  # Marble plus can take 5-10 minutes


def _api_key() -> str:
    key = os.environ.get("WORLDLABS_API_KEY", "")
    if not key:
        raise RuntimeError(
            "WORLDLABS_API_KEY not set. Get one at https://worldlabs.ai"
        )
    return key


def _headers() -> dict:
    return {
        "WLT-Api-Key": _api_key(),
        "Content-Type": "application/json",
    }


async def _submit_generation(
    client: httpx.AsyncClient,
    prompt: str,
    display_name: str = "SetLab Environment",
    model: str = DEFAULT_MODEL,
) -> str:
    """Submit a world generation request, return operation_id."""
    body = {
        "display_name": display_name[:64],
        "model": model,
        "world_prompt": {
            "type": "text",
            "text_prompt": prompt,
        },
        "permission": {"public": False},
    }
    resp = await client.post(
        f"{API_BASE}/marble/v1/worlds:generate",
        headers=_headers(),
        json=body,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["operation_id"]


async def _poll_until_done(
    client: httpx.AsyncClient,
    operation_id: str,
    on_progress: Optional[ProgressCallback] = None,
    timeout: float = GENERATE_TIMEOUT,
) -> Dict[str, Any]:
    """Poll operation status until done. Returns the world response."""
    start = time.monotonic()
    while True:
        resp = await client.get(
            f"{API_BASE}/marble/v1/operations/{operation_id}",
            headers=_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("done"):
            if data.get("error"):
                err = data["error"]
                raise RuntimeError(
                    f"Marble generation failed: {err.get('message', 'unknown')}"
                )
            return data.get("response", {})

        metadata = data.get("metadata", {})
        progress = metadata.get("progress", 0)
        if on_progress and isinstance(progress, (int, float)):
            on_progress("generating", int(progress))

        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(
                f"Marble generation timed out after {timeout:.0f}s "
                f"(operation {operation_id})"
            )

        await asyncio.sleep(POLL_INTERVAL)


async def _download_file(
    client: httpx.AsyncClient, url: str, dest: Path
) -> Path:
    """Download a file from URL to local path."""
    resp = await client.get(url, timeout=300.0, follow_redirects=True)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


async def generate_environment(
    prompt: str,
    out_dir: Path,
    display_name: str = "SetLab Environment",
    model: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Generate a full 3D environment from a text prompt.

    Downloads all available assets to out_dir/environment/:
    - collider_mesh.glb (100-200k triangles, physics-ready)
    - splat_500k.spz (Gaussian Splat, 500k splats)
    - splat_2m.spz (Gaussian Splat, 2M splats — highest quality)
    - panorama.jpg (panoramic reference image)

    Returns a dict with:
    - world_id: str
    - world_url: str (Marble web viewer)
    - assets: dict of downloaded file paths
    - caption: str (AI-generated description)
    """
    _api_key()  # fail-fast

    use_model = model or os.environ.get("WORLDLABS_MODEL", DEFAULT_MODEL)
    env_dir = out_dir / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("submitting", 0)

    async with httpx.AsyncClient() as client:
        operation_id = await _submit_generation(
            client, prompt, display_name, use_model
        )
        logger.info("[Marble] Submitted generation → operation %s", operation_id)

        if on_progress:
            on_progress("generating", 5)

        world = await _poll_until_done(client, operation_id, on_progress)

        world_id = world.get("world_id", "")
        world_url = world.get("world_marble_url", "")
        assets_data = world.get("assets") or {}
        caption = assets_data.get("caption", "")

        if on_progress:
            on_progress("downloading", 90)

        downloaded: Dict[str, str] = {}

        mesh = assets_data.get("mesh") or {}
        collider_url = mesh.get("collider_mesh_url")
        if collider_url:
            path = await _download_file(
                client, collider_url, env_dir / "collider_mesh.glb"
            )
            downloaded["collider_mesh"] = str(path)
            logger.info("[Marble] Downloaded collider mesh (%d bytes)", path.stat().st_size)

        splats = assets_data.get("splats") or {}
        spz_urls = splats.get("spz_urls") or {}
        for quality, url in spz_urls.items():
            fname = f"splat_{quality}.spz"
            path = await _download_file(client, url, env_dir / fname)
            downloaded[f"splat_{quality}"] = str(path)
            logger.info("[Marble] Downloaded %s (%d bytes)", fname, path.stat().st_size)

        imagery = assets_data.get("imagery") or {}
        pano_url = imagery.get("pano_url")
        if pano_url:
            path = await _download_file(
                client, pano_url, env_dir / "panorama.jpg"
            )
            downloaded["panorama"] = str(path)
            logger.info("[Marble] Downloaded panorama")

        thumb_url = assets_data.get("thumbnail_url")
        if thumb_url:
            path = await _download_file(
                client, thumb_url, env_dir / "thumbnail.jpg"
            )
            downloaded["thumbnail"] = str(path)

        if on_progress:
            on_progress("done", 100)

        logger.info(
            "[Marble] Environment ready: %s (%d assets)",
            world_id, len(downloaded),
        )

        return {
            "world_id": world_id,
            "world_url": world_url,
            "caption": caption,
            "assets": downloaded,
        }
