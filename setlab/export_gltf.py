from __future__ import annotations

import base64
import json
import math
import struct
from typing import Any, Dict, List, Tuple

from setlab.models import ModulePlacement


def _euler_deg_xyz_to_quat(rx: float, ry: float, rz: float) -> Tuple[float, float, float, float]:
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(rx * 0.5), math.sin(rx * 0.5)
    cy, sy = math.cos(ry * 0.5), math.sin(ry * 0.5)
    cz, sz = math.cos(rz * 0.5), math.sin(rz * 0.5)
    qw = cx * cy * cz + sx * sy * sz
    qx = sx * cy * cz - cx * sy * sz
    qy = cx * sy * cz + sx * cy * sz
    qz = cx * cy * sz - sx * sy * cz
    return (qx, qy, qz, qw)


def _unit_cube_mesh() -> Tuple[bytes, bytes, bytes]:
    """Unit cube with per-face normals, 24 vertices (4 per face), 36 indices."""
    S = 0.5
    # fmt: off
    verts = [
        # Front (+Z)
        (-S, -S,  S), (-S,  S,  S), ( S,  S,  S), ( S, -S,  S),
        # Back (-Z)
        ( S, -S, -S), ( S,  S, -S), (-S,  S, -S), (-S, -S, -S),
        # Top (+Y)
        (-S,  S,  S), (-S,  S, -S), ( S,  S, -S), ( S,  S,  S),
        # Bottom (-Y)
        (-S, -S, -S), (-S, -S,  S), ( S, -S,  S), ( S, -S, -S),
        # Right (+X)
        ( S, -S,  S), ( S,  S,  S), ( S,  S, -S), ( S, -S, -S),
        # Left (-X)
        (-S, -S, -S), (-S,  S, -S), (-S,  S,  S), (-S, -S,  S),
    ]
    norms = [
        ( 0,  0,  1),( 0,  0,  1),( 0,  0,  1),( 0,  0,  1),
        ( 0,  0, -1),( 0,  0, -1),( 0,  0, -1),( 0,  0, -1),
        ( 0,  1,  0),( 0,  1,  0),( 0,  1,  0),( 0,  1,  0),
        ( 0, -1,  0),( 0, -1,  0),( 0, -1,  0),( 0, -1,  0),
        ( 1,  0,  0),( 1,  0,  0),( 1,  0,  0),( 1,  0,  0),
        (-1,  0,  0),(-1,  0,  0),(-1,  0,  0),(-1,  0,  0),
    ]
    # fmt: on
    idx = []
    for face in range(6):
        b = face * 4
        idx.extend([b, b + 1, b + 2, b, b + 2, b + 3])

    pos_bytes = struct.pack("<{}f".format(24 * 3), *[c for v in verts for c in v])
    nrm_bytes = struct.pack("<{}f".format(24 * 3), *[c for n in norms for c in n])
    idx_bytes = struct.pack("<{}H".format(len(idx)), *idx)
    return pos_bytes, nrm_bytes, idx_bytes


def spec_to_gltf_dict(modules: List[ModulePlacement]) -> Dict[str, Any]:
    buffer_views: List[Dict[str, Any]] = []
    accessors: List[Dict[str, Any]] = []
    meshes: List[Dict[str, Any]] = []
    nodes: List[Dict[str, Any]] = []
    binary = bytearray()

    pos_cube, nrm_cube, idx_cube = _unit_cube_mesh()

    for m in modules:
        def _pad():
            while len(binary) % 4 != 0:
                binary.append(0)

        _pad()
        pos_start = len(binary)
        binary.extend(pos_cube)
        _pad()
        nrm_start = len(binary)
        binary.extend(nrm_cube)
        _pad()
        idx_start = len(binary)
        binary.extend(idx_cube)

        bv_base = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": pos_start, "byteLength": len(pos_cube), "target": 34962})
        buffer_views.append({"buffer": 0, "byteOffset": nrm_start, "byteLength": len(nrm_cube), "target": 34962})
        buffer_views.append({"buffer": 0, "byteOffset": idx_start, "byteLength": len(idx_cube), "target": 34963})

        acc_base = len(accessors)
        accessors.append({"bufferView": bv_base, "byteOffset": 0, "componentType": 5126, "count": 24, "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]})
        accessors.append({"bufferView": bv_base + 1, "byteOffset": 0, "componentType": 5126, "count": 24, "type": "VEC3"})
        accessors.append({"bufferView": bv_base + 2, "byteOffset": 0, "componentType": 5123, "count": 36, "type": "SCALAR"})

        mesh_i = len(meshes)
        meshes.append({
            "name": m.asset,
            "primitives": [{"attributes": {"POSITION": acc_base, "NORMAL": acc_base + 1}, "indices": acc_base + 2, "material": 0}],
        })
        qx, qy, qz, qw = _euler_deg_xyz_to_quat(*m.rotation_deg)
        px, py, pz = m.position
        sx, sy, sz = m.scale
        nodes.append(
            {
                "name": m.id,
                "mesh": mesh_i,
                "translation": [px, py, pz],
                "rotation": [qx, qy, qz, qw],
                "scale": [sx, sy, sz],
            }
        )

    root_children = list(range(len(nodes)))
    scene_node = len(nodes)
    nodes.append({"name": "SET_ROOT", "children": root_children})

    uri = "data:application/octet-stream;base64," + base64.b64encode(bytes(binary)).decode("ascii")

    return {
        "asset": {"version": "2.0", "generator": "setlab-pilot"},
        "scene": 0,
        "scenes": [{"nodes": [scene_node]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.85, 0.85, 0.88, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.7}, "doubleSided": True}],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary), "uri": uri}],
    }


def spec_to_gltf_json(modules: List[ModulePlacement]) -> str:
    return json.dumps(spec_to_gltf_dict(modules), indent=2)
