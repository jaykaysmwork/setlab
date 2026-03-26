"""Compatibility shim — Hunyuan / 3D AI Studio is no longer used.

Mesh and HD pipelines use **Hyper3D Rodin** (`setlab.rodin_client`) with
``RODIN_API_KEY`` or ``HYPER3D_API_KEY``.

If anything still does ``from setlab import studio3d_client`` or
``from setlab.studio3d_client import generate_meshes``, it now forwards to
Rodin so you do not need ``STUDIO3D_API_KEY``.

Prefer importing from ``setlab.rodin_client`` in new code.
Docs: https://developer.hyper3d.ai/
"""

from __future__ import annotations

from setlab.rodin_client import generate_hd_meshes, generate_meshes

__all__ = ["generate_meshes", "generate_hd_meshes"]
