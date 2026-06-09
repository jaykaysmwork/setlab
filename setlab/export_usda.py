from __future__ import annotations

import re
from typing import List

from setlab.models import ModulePlacement


def spec_to_usda(modules: List[ModulePlacement], *, default_prim: str = "World") -> str:
    lines: List[str] = [
        "#usda 1.0",
        "(",
        f'    defaultPrim = "{default_prim}"',
        "    metersPerUnit = 1",
        '    upAxis = "Y"',
        ")",
        "",
        f'def Xform "{default_prim}" (',
        '    kind = "assembly"',
        ")",
        "{",
        '    def Xform "SET" (',
        '        kind = "group"',
        "    )",
        "    {",
    ]

    used_names = set()
    for m in modules:
        rx, ry, rz = m.rotation_deg
        px, py, pz = m.position
        sx, sy, sz = m.scale
        # Sanitize the id into a VALID, UNIQUE USD prim name. USD prim names must
        # match [A-Za-z_][A-Za-z0-9_]* and be unique among siblings, so: alnum +
        # underscore only (raw quotes/newlines would corrupt the prim), never
        # digit-leading or empty, and de-duplicated within the SET scope (free-form
        # / non-ASCII ids can otherwise collide and silently drop a module).
        prim_name = re.sub(r"[^A-Za-z0-9_]", "_", str(m.id))
        if not prim_name or prim_name[0].isdigit():
            prim_name = "_" + prim_name
        if prim_name in used_names:
            n = 2
            while f"{prim_name}_{n}" in used_names:
                n += 1
            prim_name = f"{prim_name}_{n}"
        used_names.add(prim_name)
        # USD uses degrees in rotateXYZ ops in many examples; use rotateXYZ for clarity
        lines.extend(
            [
                f'        def Xform "{prim_name}" {{',
                f"            float3 xformOp:translate = ({px}, {py}, {pz})",
                f"            float3 xformOp:rotateXYZ = ({rx}, {ry}, {rz})",
                f"            float3 xformOp:scale = ({sx}, {sy}, {sz})",
                '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
                '            def Cube "proxy" {',
                "                double size = 1.0",
                "            }",
                "        }",
            ]
        )

    lines.extend(["    }", "}", ""])
    return "\n".join(lines)
