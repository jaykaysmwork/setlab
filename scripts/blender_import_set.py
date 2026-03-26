# SPDX-License-Identifier: MIT
"""Optional: blender --background --python scripts/blender_import_set.py -- path/to/set_spec.json

Requires Blender 3.x+. Clears scene and spawns cubes from SetSpec JSON.
"""
import json
import sys
from pathlib import Path

try:
    import bpy  # type: ignore
except ImportError:
    print("Run inside Blender: blender --background --python ...")
    sys.exit(1)


def main() -> None:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    if not argv:
        print("Usage: blender ... --python ... -- /path/to/set_spec.json")
        sys.exit(1)
    path = Path(argv[0])
    data = json.loads(path.read_text(encoding="utf-8"))
    modules = data.get("modules", [])

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for m in modules:
        mid = m["id"]
        pos = m["position"]
        rot = m.get("rotation_deg", [0, 0, 0])
        sc = m.get("scale", [1, 1, 1])
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=pos)
        obj = bpy.context.active_object
        obj.name = mid
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = [rot[0] * 3.14159265 / 180, rot[1] * 3.14159265 / 180, rot[2] * 3.14159265 / 180]
        obj.scale = sc

    out = path.parent / "set_blocking.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
