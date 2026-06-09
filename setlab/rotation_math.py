"""Pure (stdlib-only) Euler<->quaternion conversion shared by the glTF exporter and
the deploy rotation bake.

Convention: Three.js Euler order 'XYZ' (q = q_x * q_y * q_z), matching the web viewer
(ImportedMeshModule's THREE.Euler(..., "XYZ")) and the USDA rotateXYZ export. Keeping
this in ONE dependency-free place prevents export_gltf and glb_rotation_bake from ever
drifting onto different rotation conventions (which previously caused the exported/Unreal
scene to disagree with the browser preview for multi-axis rotations).
"""

from __future__ import annotations

import math
from typing import Tuple

Vec3 = Tuple[float, float, float]


def euler_deg_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float, float, float, float]:
    """Degrees (XYZ Euler) -> quaternion (x, y, z, w), Three.js order 'XYZ'."""
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(rx * 0.5), math.sin(rx * 0.5)
    cy, sy = math.cos(ry * 0.5), math.sin(ry * 0.5)
    cz, sz = math.cos(rz * 0.5), math.sin(rz * 0.5)
    qx = sx * cy * cz + cx * sy * sz
    qy = cx * sy * cz - sx * cy * sz
    qz = cx * cy * sz + sx * sy * cz
    qw = cx * cy * cz - sx * sy * sz
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
    """Inverse of euler_deg_xyz_to_quat, via the rotation matrix exactly like
    THREE.Euler.setFromQuaternion(q, 'XYZ'): solve Y from m13, then X and Z."""

    def clamp(t: float) -> float:
        return max(-1.0, min(1.0, t))

    x2, y2, z2 = x + x, y + y, z + z
    xx, xy, xz = x * x2, x * y2, x * z2
    yy, yz, zz = y * y2, y * z2, z * z2
    wx, wy, wz = w * x2, w * y2, w * z2
    m11 = 1.0 - (yy + zz)
    m12 = xy - wz
    m13 = xz + wy
    m22 = 1.0 - (xx + zz)
    m23 = yz - wx
    m32 = yz + wx
    m33 = 1.0 - (xx + yy)
    ey = math.asin(clamp(m13))
    if abs(m13) < 0.9999999:
        ex = math.atan2(-m23, m33)
        ez = math.atan2(-m12, m11)
    else:
        ex = math.atan2(m32, m22)
        ez = 0.0
    return (math.degrees(ex), math.degrees(ey), math.degrees(ez))
