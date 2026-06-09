# Run inside Unreal Editor only (Tools → Execute Python Script…).
# Requires: Python Editor Script Plugin enabled.
#
# Before running:
# 1. Copy set_spec.json into the project or set SPEC_PATH to an absolute path.
# 2. Fill ASSET_MAP: keys = JSON "asset" field, values = StaticMesh soft object paths
#    (Content Browser → mesh → Right-click → Copy Reference).

from __future__ import annotations

import json
import os
import unreal

# --- configure ---
SPEC_PATH = os.path.join(unreal.Paths.project_saved_dir(), "set_spec.json")
# Example if you paste the file next to Saved:
# SPEC_PATH = r"/Users/you/setlab/out/원하는폴더/set_spec.json"

# Keys must match SetSpec "asset" strings. Values = /Game/... full reference to StaticMesh.
ASSET_MAP = {
    "mod_wall_6m": "/Game/set/StaticMeshes/mod_wall_6m.mod_wall_6m",
    "mod_wall_2m": "/Game/set/StaticMeshes/mod_wall_2m.mod_wall_2m",
    "mod_column_1m": "/Game/set/StaticMeshes/mod_column_1m.mod_column_1m",
}

# Unreal units per meter (usually 100 if project uses cm).
SCALE_M_TO_UU = 100.0


def _load_spec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _spawn(spec_path: str) -> int:
    data = _load_spec(spec_path)
    modules = data.get("modules", [])
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        unreal.log_error("No editor world")
        return 0

    count = 0
    for i, m in enumerate(modules):
        asset_key = m.get("asset")
        if asset_key not in ASSET_MAP:
            unreal.log_warning("No ASSET_MAP entry for asset=%r (index %d)" % (asset_key, i))
            continue

        mesh_path = ASSET_MAP[asset_key]
        mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if not mesh:
            unreal.log_error("Failed to load mesh: %s" % mesh_path)
            continue

        px, py, pz = m["position"]
        rx, ry, rz = m.get("rotation_deg", [0, 0, 0])
        sx, sy, sz = m.get("scale", [1, 1, 1])

        loc = unreal.Vector(px * SCALE_M_TO_UU, py * SCALE_M_TO_UU, pz * SCALE_M_TO_UU)
        # Adjust euler mapping if your up-axis / convention differs.
        rot = unreal.Rotator(roll=rx, pitch=ry, yaw=rz)
        scale = unreal.Vector(sx, sy, sz)

        t = unreal.Transform(loc, rot, scale)
        actor = subsystem.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
        if not actor:
            unreal.log_error("spawn failed for index %d" % i)
            continue

        actor.set_actor_label("%s_%d" % (m.get("id", "mod"), i))
        smc = actor.static_mesh_component
        smc.set_static_mesh(mesh)
        actor.set_actor_transform(t, False, True)
        count += 1

    unreal.log("Spawned %d static mesh actors from %s" % (count, spec_path))
    return count


if __name__ == "__main__":
    if not os.path.isfile(SPEC_PATH):
        unreal.log_error("set_spec.json not found at: %s" % SPEC_PATH)
    else:
        _spawn(SPEC_PATH)
