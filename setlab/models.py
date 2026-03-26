from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


Vec3 = Tuple[float, float, float]


class EnvironmentSettings(BaseModel):
    time_of_day: str = "noon"
    weather: str = "clear"
    fog_density: float = 0.02
    sun_intensity: float = 10.0
    sun_color_temp: int = 6500


class ModulePlacement(BaseModel):
    id: str
    asset: str = Field(description="Logical module id, e.g. mod_wall_4m")
    description: str = ""
    position: Vec3
    rotation_deg: Vec3 = (0.0, 0.0, 0.0)
    scale: Vec3 = (1.0, 1.0, 1.0)

    @field_validator("position", "rotation_deg", "scale")
    @classmethod
    def triple(cls, v: object) -> Vec3:
        if not isinstance(v, (list, tuple)) or len(v) != 3:
            raise ValueError("expected length-3 tuple")
        return (float(v[0]), float(v[1]), float(v[2]))


class SetSpec(BaseModel):
    title: str
    era_style: str = ""
    ground_material: str = ""
    environment: Optional[EnvironmentSettings] = None
    notes: str = ""
    modules: List[ModulePlacement] = Field(default_factory=list)
    per_module_glb_extra_deg: Dict[str, Tuple[float, float, float]] = Field(
        default_factory=dict,
        description="Viewer/deploy extra Euler Δ (°) XYZ per module id.",
    )

    @field_validator("per_module_glb_extra_deg", mode="before")
    @classmethod
    def _coerce_per_module_extra_deg(
        cls, v: Any
    ) -> Dict[str, Tuple[float, float, float]]:
        if v is None or not isinstance(v, dict):
            return {}
        out: Dict[str, Tuple[float, float, float]] = {}
        for k, val in v.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                try:
                    out[str(k)] = (float(val[0]), float(val[1]), float(val[2]))
                except (TypeError, ValueError):
                    continue
        return out
