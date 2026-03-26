from __future__ import annotations

from typing import Any, Dict


def generate_raw(brief: str) -> Dict[str, Any]:
    """Deterministic blocking set — works offline, for CI or no-Ollama runs."""
    _ = brief.lower()
    return {
        "title": "Pilot Blocking Set (mock)",
        "era_style": "neutral_stage",
        "notes": "Generated without LLM — replace with ollama backend for AI runs.",
        "modules": [
            {
                "id": "floor_main",
                "asset": "mod_platform_12x8",
                "position": (0.0, 0.1, 0.0),
                "rotation_deg": (0.0, 0.0, 0.0),
                "scale": (12.0, 0.2, 8.0),
            },
            {
                "id": "wall_n",
                "asset": "mod_wall_12m",
                "position": (0.0, 2.0, -4.0),
                "rotation_deg": (0.0, 0.0, 0.0),
                "scale": (12.0, 4.0, 0.2),
            },
            {
                "id": "wall_s",
                "asset": "mod_wall_12m",
                "position": (0.0, 2.0, 4.0),
                "rotation_deg": (0.0, 0.0, 0.0),
                "scale": (12.0, 4.0, 0.2),
            },
            {
                "id": "column_l",
                "asset": "mod_column",
                "position": (-4.0, 2.0, 0.0),
                "rotation_deg": (0.0, 0.0, 0.0),
                "scale": (0.6, 4.0, 0.6),
            },
            {
                "id": "column_r",
                "asset": "mod_column",
                "position": (4.0, 2.0, 0.0),
                "rotation_deg": (0.0, 0.0, 0.0),
                "scale": (0.6, 4.0, 0.6),
            },
        ],
    }
