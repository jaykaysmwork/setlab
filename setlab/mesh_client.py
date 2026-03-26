"""Tripo3D text-to-3D mesh generation wrapper."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tripo3d import TripoClient, TaskStatus

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

# Tripo Professional allows ~10 concurrent tasks; Basic is 1. Override if your plan differs.
MAX_CONCURRENT = int(os.environ.get("TRIPO_CONCURRENCY", "10"))


async def _generate_one(
    client: TripoClient,
    semaphore: asyncio.Semaphore,
    module_id: str,
    description: str,
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[str]:
    """Generate a single 3D model and save its GLB to out_dir/meshes/."""
    async with semaphore:
        try:
            if on_progress:
                on_progress(module_id, "queued", 0)

            task_id = await client.text_to_model(prompt=description)
            logger.info("[MeshGen] %s → task %s", module_id, task_id)

            if on_progress:
                on_progress(module_id, "generating", 0)

            task = await client.wait_for_task(task_id, timeout=300)

            if task.status != TaskStatus.SUCCESS:
                logger.warning("[MeshGen] %s status: %s", module_id, task.status)
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
                logger.info("[MeshGen] %s → %s", module_id, target.name)
                if on_progress:
                    on_progress(module_id, "done", 100)
                return str(target)

            if on_progress:
                on_progress(module_id, "failed", 100)
            return None

        except Exception as e:
            logger.error("[MeshGen] %s error: %s", module_id, e)
            if on_progress:
                on_progress(module_id, "failed", 100)
            return None


async def generate_meshes(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Optional[str]]:
    """Generate 3D models with controlled concurrency.

    Respects Tripo's per-plan concurrent task limit (Basic≈1, Professional≈10).
    Set TRIPO_CONCURRENCY (default 10); use 1 on Basic.
    """
    api_key = os.environ.get("TRIPO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "TRIPO_API_KEY not set. Get one at https://platform.tripo3d.ai"
        )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async with TripoClient(api_key=api_key) as client:
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
