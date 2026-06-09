"""Bake viewer-style GLB rotation chain into rotation_deg (XYZ Euler °), matching web ImportedMeshModule."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# Euler<->quat math lives in one shared, dependency-free module so this module,
# export_gltf, and the web viewer all stay on the same Three.js 'XYZ' convention.
from setlab.rotation_math import (
    euler_deg_xyz_to_quat,
    euler_deg_xyz_from_quat,
    quat_multiply,
)

Vec3 = Tuple[float, float, float]


def build_extra_euler_chain_deg(
    asset: str,
    building_extra_deg: Vec3,
    module_id: str,
    per_module_map: Dict[str, Vec3],
) -> List[Vec3]:
    """Mirror web/lib/meshGlbRotation.buildGlbExtraEulerChain."""
    chain: List[Vec3] = []
    if asset == "mod_building":
        bx, by, bz = building_extra_deg
        if bx != 0 or by != 0 or bz != 0:
            chain.append((bx, by, bz))
    d = per_module_map.get(module_id)
    if d is not None:
        rx, ry, rz = d
        if rx != 0 or ry != 0 or rz != 0:
            chain.append((rx, ry, rz))
    return chain


def _bake_rotation_quat(
    asset: str,
    rotation_deg: Vec3,
    building_extra_deg: Vec3,
    per_module_map: Dict[str, Vec3],
    module_id: str,
) -> Tuple[float, float, float, float]:
    """q = q_spec * ∏ q_extra → baked quaternion (x,y,z,w)."""
    q = euler_deg_xyz_to_quat(*rotation_deg)
    chain = build_extra_euler_chain_deg(asset, building_extra_deg, module_id, per_module_map)
    for rx, ry, rz in chain:
        dq = euler_deg_xyz_to_quat(rx, ry, rz)
        q = quat_multiply(q[0], q[1], q[2], q[3], dq[0], dq[1], dq[2], dq[3])
    return q


def bake_rotation_deg(
    asset: str,
    rotation_deg: Vec3,
    building_extra_deg: Vec3,
    per_module_map: Dict[str, Vec3],
    module_id: str,
) -> Vec3:
    """q = q_spec * ∏ q_extra → new XYZ Euler °."""
    q = _bake_rotation_quat(asset, rotation_deg, building_extra_deg, per_module_map, module_id)
    return euler_deg_xyz_from_quat(*q)


def bake_spec_modules_for_deploy(
    modules: List[Dict[str, Any]],
    building_extra_deg: Vec3,
    per_module_glb_extra_deg: Dict[str, Vec3],
) -> List[Dict[str, Any]]:
    """Return new module list with rotation_deg and rotation_quat baked (does not mutate input)."""
    out: List[Dict[str, Any]] = []
    for m in modules:
        mm = dict(m)
        rid = m.get("id", "")
        asset = m.get("asset", "")
        rot = m.get("rotation_deg", [0.0, 0.0, 0.0])
        base = (float(rot[0]), float(rot[1]), float(rot[2]))
        q = _bake_rotation_quat(asset, base, building_extra_deg, per_module_glb_extra_deg, rid)
        euler = euler_deg_xyz_from_quat(*q)
        mm["rotation_deg"] = [round(euler[0], 6), round(euler[1], 6), round(euler[2], 6)]
        mm["rotation_quat"] = [round(q[0], 9), round(q[1], 9), round(q[2], 9), round(q[3], 9)]
        out.append(mm)
    return out
