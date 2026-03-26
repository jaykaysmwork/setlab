"""Bake viewer-style GLB rotation chain into rotation_deg (XYZ Euler °), matching web ImportedMeshModule."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

Vec3 = Tuple[float, float, float]


def euler_deg_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float, float, float, float]:
    """Same convention as setlab.export_gltf._euler_deg_xyz_to_quat → glTF (x,y,z,w)."""
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(rx * 0.5), math.sin(rx * 0.5)
    cy, sy = math.cos(ry * 0.5), math.sin(ry * 0.5)
    cz, sz = math.cos(rz * 0.5), math.sin(rz * 0.5)
    qw = cx * cy * cz + sx * sy * sz
    qx = sx * cy * cz - cx * sy * sz
    qy = cx * sy * cz + sx * cy * sz
    qz = cx * cy * sz - sx * sy * cz
    return (qx, qy, qz, qw)


def quat_multiply(
    ax: float, ay: float, az: float, aw: float,
    bx: float, by: float, bz: float, bw: float,
) -> Tuple[float, float, float, float]:
    """Hamilton product a * b (same as Three.js Quaternion.multiply)."""
    x = aw * bx + ax * bw + ay * bz - az * by
    y = aw * by - ax * bz + ay * bw + az * bx
    z = aw * bz + ax * by - ay * bx + az * bw
    w = aw * bw - ax * bx - ay * by - az * bz
    return (x, y, z, w)


def euler_deg_xyz_from_quat(x: float, y: float, z: float, w: float) -> Vec3:
    """Inverse of euler_deg_xyz_to_quat; matches Three.js Euler order 'XYZ' (degrees)."""

    def clamp(t: float) -> float:
        return max(-1.0, min(1.0, t))

    t0 = 2.0 * (w * x + y * z)
    t1 = 1.0 - 2.0 * (x * x + y * y)
    ex = math.atan2(t0, t1)
    t2 = clamp(2.0 * (w * y - z * x))
    ey = math.asin(t2)
    t3 = 2.0 * (w * z + x * y)
    t4 = 1.0 - 2.0 * (y * y + z * z)
    ez = math.atan2(t3, t4)
    return (math.degrees(ex), math.degrees(ey), math.degrees(ez))


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
