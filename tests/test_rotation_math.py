"""Regression tests for the Euler<->quaternion conversion used by glTF export and
the deploy rotation bake. Locks the convention to Three.js Euler order 'XYZ' so the
exported scene (and Unreal deploy) can never again diverge from the web viewer.

Run: .venv/bin/python tests/test_rotation_math.py   (or: pytest tests/test_rotation_math.py)
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from setlab.rotation_math import (
    euler_deg_xyz_to_quat,
    euler_deg_xyz_from_quat,
    quat_multiply,
)
from setlab import glb_rotation_bake

# Non-singular plus single-axis and gimbal cases.
CASES = [
    (0, 0, 0), (30, 0, 0), (0, 40, 0), (0, 0, 50),
    (30, 40, 50), (10, -20, 80), (-45, 30, 15),
    (90, 0, 0), (0, 0, 90), (0, 90, 0),  # last two exercise the gimbal branch
]


def _axis_quat(axis, deg):
    h = math.radians(deg) * 0.5
    s, c = math.sin(h), math.cos(h)
    return {"x": (s, 0, 0, c), "y": (0, s, 0, c), "z": (0, 0, s, c)}[axis]


def _compose_xyz(rx, ry, rz):
    """Three.js Euler 'XYZ' quaternion = q_x * q_y * q_z (built from unambiguous
    single-axis quaternions, independent of the formula under test)."""
    q = quat_multiply(*_axis_quat("x", rx), *_axis_quat("y", ry))
    return quat_multiply(*q, *_axis_quat("z", rz))


def _dot(a, b):
    return sum(p * q for p, q in zip(a, b))


def test_forward_matches_threejs_xyz_composition():
    # Non-tautological: compares the formula to an independent single-axis composition.
    for rx, ry, rz in CASES:
        got = euler_deg_xyz_to_quat(rx, ry, rz)
        exp = _compose_xyz(rx, ry, rz)
        assert abs(abs(_dot(got, exp)) - 1.0) < 1e-9, (rx, ry, rz, got, exp)


def test_forward_is_shared():
    # Deduped: every module references the one shared function object, so they cannot drift.
    assert glb_rotation_bake.euler_deg_xyz_to_quat is euler_deg_xyz_to_quat
    try:  # export_gltf pulls pydantic; only assert it when that loads
        from setlab.export_gltf import _euler_deg_xyz_to_quat
    except Exception:
        return
    assert _euler_deg_xyz_to_quat is euler_deg_xyz_to_quat


def test_roundtrip_forward_inverse():
    for rx, ry, rz in CASES:
        q = euler_deg_xyz_to_quat(rx, ry, rz)
        q2 = euler_deg_xyz_to_quat(*euler_deg_xyz_from_quat(*q))
        assert abs(abs(_dot(q, q2)) - 1.0) < 1e-9, (rx, ry, rz)


def test_single_axis_y_is_exact():
    qx, qy, qz, qw = euler_deg_xyz_to_quat(0, 90, 0)
    r = math.sqrt(2) / 2
    assert abs(qx) < 1e-12 and abs(qz) < 1e-12
    assert abs(qy - r) < 1e-9 and abs(qw - r) < 1e-9


def test_is_not_the_old_zyx_convention():
    # Guards against reverting to the buggy aerospace ZYX formula.
    rx, ry, rz = 30, 40, 50
    rxr, ryr, rzr = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(rxr * .5), math.sin(rxr * .5)
    cy, sy = math.cos(ryr * .5), math.sin(ryr * .5)
    cz, sz = math.cos(rzr * .5), math.sin(rzr * .5)
    zyx = (sx * cy * cz - cx * sy * sz, cx * sy * cz + sx * cy * sz,
           cx * cy * sz - sx * sy * cz, cx * cy * cz + sx * sy * sz)
    xyz = euler_deg_xyz_to_quat(rx, ry, rz)
    assert abs(abs(_dot(zyx, xyz)) - 1.0) > 1e-3


if __name__ == "__main__":
    test_forward_matches_threejs_xyz_composition()
    test_forward_is_shared()
    test_roundtrip_forward_inverse()
    test_single_axis_y_is_exact()
    test_is_not_the_old_zyx_convention()
    print("OK: all rotation math tests passed")
