"""HD mesh pipeline: Gemini multi-view images → Tripo3D multiview-to-model → GLB."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tripo3d import TripoClient, TaskStatus

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

TRIPO_MODEL = os.environ.get("TRIPO_HD_MODEL", "v3.1-20260211")
# Same plan limits as text-to-model; override with TRIPO_HD_CONCURRENCY.
MAX_CONCURRENT = int(os.environ.get("TRIPO_HD_CONCURRENCY", "10"))


async def _generate_one_hd(
    client: TripoClient,
    semaphore: asyncio.Semaphore,
    module_id: str,
    image_dir: Path,
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[str]:
    """Convert multi-view images into a single HD GLB model."""
    async with semaphore:
        try:
            views = ["front", "left", "back", "right"]
            image_paths = [str(image_dir / f"{v}.png") for v in views]
            missing = [p for p in image_paths if not Path(p).exists()]
            if missing:
                logger.warning("[HD] %s missing images: %s", module_id, missing)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            if on_progress:
                on_progress(module_id, "uploading", 10)

            task_id = await client.multiview_to_model(
                images=image_paths,
                model_version=TRIPO_MODEL,
                texture=True,
                pbr=True,
                texture_quality="detailed",
                geometry_quality="detailed",
                orientation="align_image",
            )
            logger.info("[HD] %s → task %s", module_id, task_id)

            if on_progress:
                on_progress(module_id, "generating_3d", 30)

            task = await client.wait_for_task(task_id, timeout=600)

            if task.status != TaskStatus.SUCCESS:
                logger.warning("[HD] %s status: %s", module_id, task.status)
                if on_progress:
                    on_progress(module_id, "failed", 100)
                return None

            meshes_dir = out_dir / "meshes"
            meshes_dir.mkdir(parents=True, exist_ok=True)

            files = await client.download_task_models(task, str(meshes_dir))
            model_path = (
                files.get("model")
                or files.get("pbr_model")
                or files.get("base_model")
            )
            if model_path:
                target = meshes_dir / f"{module_id}.glb"
                Path(model_path).rename(target)
                logger.info("[HD] %s → %s (%d bytes)", module_id, target.name, target.stat().st_size)
                if on_progress:
                    on_progress(module_id, "done", 100)
                return str(target)

            if on_progress:
                on_progress(module_id, "failed", 100)
            return None

        except Exception as e:
            logger.error("[HD] %s error: %s", module_id, e)
            if on_progress:
                on_progress(module_id, "failed", 100)
            return None


async def generate_hd_meshes(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Optional[str]]:
    """Phase 2: convert already-generated images into HD GLB meshes via Tripo multiview.

    Expects images at out_dir/images/{module_id}/{front,left,back,right}.png.
    """
    api_key = os.environ.get("TRIPO_API_KEY")
    if not api_key:
        raise RuntimeError("TRIPO_API_KEY not set")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with TripoClient(api_key=api_key) as client:
        coros = [
            _generate_one_hd(
                client,
                semaphore,
                m["id"],
                out_dir / "images" / m["id"],
                out_dir,
                on_progress,
            )
            for m in modules
        ]
        results = await asyncio.gather(*coros)

    return {m["id"]: r for m, r in zip(modules, results)}
