from __future__ import annotations

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

    for m in modules:
        rx, ry, rz = m.rotation_deg
        px, py, pz = m.position
        sx, sy, sz = m.scale
        # USD uses degrees in rotateXYZ ops in many examples; use rotateXYZ for clarity
        lines.extend(
            [
                f'        def Xform "{m.id}" {{',
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
