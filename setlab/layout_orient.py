"""Post-process layout: face storefronts toward the nearest road/sidewalk (mod_floor)."""

from __future__ import annotations

import math
from typing import List, Tuple

from setlab.models import ModulePlacement, SetSpec


def _closest_point_aabb_2d(
    px: float, pz: float, cx: float, cz: float, hx: float, hz: float
) -> Tuple[float, float]:
    qx = min(max(px, cx - hx), cx + hx)
    qz = min(max(pz, cz - hz), cz + hz)
    return qx, qz


def _dist_sq_2d(ax: float, az: float, bx: float, bz: float) -> float:
    dx, dz = ax - bx, az - bz
    return dx * dx + dz * dz


def orient_buildings_toward_floors(spec: SetSpec) -> SetSpec:
    """Set rotation_deg for mod_building so local +Z (facade) points toward nearest floor AABB.

    Works for straight roads, T-junctions, and L-shapes: each building uses the closest
    point on any mod_floor footprint in XZ, then faces that point from its center.
    """
    floors: List[ModulePlacement] = [m for m in spec.modules if m.asset == "mod_floor"]
    if not floors:
        return spec

    fixed: List[ModulePlacement] = []
    for m in spec.modules:
        if m.asset != "mod_building":
            fixed.append(m)
            continue

        bx, _, bz = m.position
        best_q: Tuple[float, float] | None = None
        best_d = float("inf")

        for f in floors:
            fx, _, fz = f.position
            sx, _, sz = f.scale
            hx, hz = sx * 0.5, sz * 0.5
            qx, qz = _closest_point_aabb_2d(bx, bz, fx, fz, hx, hz)
            d = _dist_sq_2d(bx, bz, qx, qz)
            if d < best_d:
                best_d = d
                best_q = (qx, qz)

        if best_q is None or best_d < 1e-8:
            fixed.append(m)
            continue

        qx, qz = best_q
        vx, vz = qx - bx, qz - bz
        len_h = math.hypot(vx, vz)
        if len_h < 1e-6:
            fixed.append(m)
            continue

        vx /= len_h
        vz /= len_h
        # Local +Z after Ry-only maps to world (sin(ry), cos(ry)) in (x,z); match export_gltf / Three.js.
        ry_deg = math.degrees(math.atan2(vx, vz))
        rx, _, rz = m.rotation_deg
        fixed.append(
            m.model_copy(update={"rotation_deg": (float(rx), float(ry_deg), float(rz))})
        )

    return spec.model_copy(update={"modules": fixed})
