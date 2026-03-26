from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import anthropic

from setlab.llm_json import parse_llm_json_object
from setlab.prompts import layout_system_prompt, user_message

REFINE_SYSTEM = """You are a 3D set layout engine. You will receive an existing JSON layout and an instruction to modify it.

Your job is to return an UPDATED version of the full JSON layout that applies the user's instruction.
You CAN and SHOULD modify any field (position, rotation_deg, scale, description) when the instruction calls for it.

Return ONLY valid JSON (no markdown, no explanation) with the same schema:
{
  "title": string,
  "era_style": string,
  "notes": string,
  "modules": [ ... all modules ... ]
}

COORDINATE SYSTEM:
  - Y is up, X and Z are horizontal. Roads typically run along Z.
  - rotation_deg [rx, ry, rz]: Euler degrees. ry rotates around the Y axis.
  - Each module's local +Z is its "front face" before rotation.

BUILDING ORIENTATION (rotation_deg):
  - A building at +X side of road (e.g. x=18) needs ry=-90 to face -X (toward road).
  - A building at -X side of road (e.g. x=-18) needs ry=90 to face +X (toward road).
  - "Buildings face each other" means east-side ry=-90, west-side ry=90.
  - "All buildings face north (+Z)" means ry=0.
  - "Rotate building 180°" means add 180 to its current ry.
  - When the user asks to change orientation, UPDATE rotation_deg accordingly.

VEGETATION scale rules (never use [1,1,1] for trees):
  - Palm tree (mod_tree_palm): scale [0.8, 8.0, 0.8], position Y = 4.0
  - Generic tree (mod_tree): scale [3.0, 6.0, 3.0], position Y = 3.0

New module ids must be unique. Each new module MUST have a "description" field.
The user may write instructions in any language (Korean, English, etc.).
"""


def _get_client(timeout: float = 120.0) -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Get one at https://console.anthropic.com/settings/keys"
        )
    return anthropic.Anthropic(api_key=api_key, timeout=timeout)


def _parse(text: str) -> Dict[str, Any]:
    return parse_llm_json_object(text)


def generate_raw(
    brief: str,
    *,
    model: str = "claude-sonnet-4-6",
    timeout: float = 120.0,
    max_modules: Optional[int] = None,
) -> Dict[str, Any]:
    client = _get_client(timeout)
    message = client.messages.create(
        model=model,
        max_tokens=16384,
        system=layout_system_prompt(max_modules),
        messages=[{"role": "user", "content": user_message(brief)}],
    )
    raw = message.content[0].text
    if message.stop_reason == "max_tokens":
        raise ValueError(
            "레이아웃 JSON이 토큰 한도로 잘렸습니다. "
            "Enhance 브리프를 조금 줄이거나 모듈 수를 요청하지 말고 다시 Generate 해보세요."
        )
    return _parse(raw)


def refine_raw(
    existing_spec: Dict[str, Any],
    instruction: str,
    *,
    model: str = "claude-sonnet-4-6",
    timeout: float = 120.0,
) -> Dict[str, Any]:
    client = _get_client(timeout)
    user_content = (
        f"Existing layout:\n{json.dumps(existing_spec, indent=2)}\n\n"
        f"Instruction: {instruction.strip()}\n\n"
        "Return the full updated JSON layout."
    )
    message = client.messages.create(
        model=model,
        max_tokens=16384,
        system=REFINE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    if message.stop_reason == "max_tokens":
        raise ValueError("응답이 너무 길어 잘렸습니다. 더 간단한 수정을 시도해주세요.")
    return _parse(raw)


REFINE_MODULE_SYSTEM = """You are a 3D set layout engine. You receive ONE module to edit, optional REFERENCE modules from the same scene, and an instruction.

Return ONLY valid JSON for that single module (no markdown, no explanation). Schema:
{
  "id": string,
  "asset": string,
  "description": string,
  "position": [x, y, z],
  "rotation_deg": [rx, ry, rz],
  "scale": [sx, sy, sz]
}

Rules:
- The "id" MUST stay EXACTLY the same as in the input module. Never rename.
- Change only fields the user's instruction requires; keep others identical to the input unless the instruction clearly requires copying from a reference module.
- If the user asks to match / copy / make identical to another module (by id or description), look up that module in REFERENCE MODULES and copy its description and scale onto the target. For paired east/west sidewalks along a central road, keep the target's position X sign (and magnitude) appropriate for its side—usually mirror only if the instruction asks for symmetric layout; otherwise copy description+scale and leave position unless the user asks to move it.
- User may write in any language (Korean, English, etc.).
- Y-up meters; same layout conventions as the parent scene (rotation_deg, scale semantics).

BUILDING ORIENTATION (rotation_deg) if the instruction asks to face the road:
  - Building on +X side of road → ry=-90 to face -X toward road
  - Building on -X side → ry=90 to face +X toward road
"""


def refine_single_module_raw(
    module: Dict[str, Any],
    *,
    title: str = "",
    era_style: str = "",
    instruction: str,
    reference_modules: Optional[List[Dict[str, Any]]] = None,
    model: str = "claude-sonnet-4-6",
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Return updated single module dict; id must match input.

    reference_modules: other modules in the same spec (read-only). Lets the model
    copy description/scale when the user says e.g. "match floor_sidewalk_west".
    """
    mid = module.get("id")
    if not mid:
        raise ValueError("module must have an id")

    client = _get_client(timeout)
    ref_block = ""
    if reference_modules:
        ref_block = (
            "\nREFERENCE MODULES (read-only; same scene — use when user names another id "
            "or asks to match / copy another object):\n"
            f"{json.dumps(reference_modules, indent=2)}\n"
        )

    user_content = (
        f"Scene title: {title}\nEra/style: {era_style}\n\n"
        f"TARGET module (you output ONLY an update for this one):\n{json.dumps(module, indent=2)}\n"
        f"{ref_block}\n"
        f"Instruction: {instruction.strip()}\n\n"
        f'Return JSON for the target module only. The "id" must remain exactly "{mid}".'
    )
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=REFINE_MODULE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    if message.stop_reason == "max_tokens":
        raise ValueError("응답이 너무 길어 잘렸습니다. 더 짧은 지시로 시도해주세요.")
    out = _parse(raw)
    if not isinstance(out, dict):
        raise ValueError("Expected a JSON object for one module")
    if out.get("id") != mid:
        raise ValueError(
            f'Model changed module id (expected "{mid}", got "{out.get("id")}")'
        )
    return out


def _strip_plain_text_response(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response")
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


ENHANCE_PROMPT_SYSTEM = """You are a senior art director and layout designer. The user writes a rough idea (any language). You rewrite it into a single, maximally specific English scene brief for a downstream 3D set-layout model that emits JSON modules (roads, sidewalks, buildings, vegetation, props).

Goals (photoreal / film-set fidelity the layout and text-to-3D steps can actually use):
- **Spatial layout**: Y-up meters. Name approximate positions (e.g. central road along +Z, building rows at ±X), road width/length, sidewalk widths, setbacks, lane count if relevant, where the camera “hero” view would sit.
- **Architecture & era**: Materials (stucco, glass curtain wall, weathered concrete), roofline, floor count ranges, signage style, regional cues (e.g. Seoul backstreet vs. LA strip mall), decade or “timeless contemporary”.
- **Lighting & atmosphere**: Time of day, sun direction if implied, weather (clear / haze / wet pavement), color temperature, key practicals (neon, sodium vapor, LED storefronts).
- **Surface & detail**: Ground (asphalt wear, cracks, manhole covers), curbs, street furniture (benches, bollards, bike racks), vegetation species and spacing, parked vehicles or empty stalls if it matters.
- **Population & story**: Optional light narrative (quiet dawn vs. crowded evening) without inventing named characters unless the user did.
- **Module-oriented hints**: Call out distinct zones the layout engine should separate (e.g. east/west sidewalks, median, park strip, façade modules) so each gets a clear description for later mesh generation.
- **Constraints**: Do not output JSON. Do not use markdown code fences. Plain prose or tight bullet phrases. Prefer **about 350–900 words** when the idea is rich; shorter only if the user gave almost nothing (then still add sane defaults). No meta (“Here is the enhanced prompt”). Start directly with the scene."""


def enhance_prompt_raw(
    brief: str,
    *,
    model: str = "claude-sonnet-4-6",
    timeout: float = 180.0,
) -> str:
    """Return an expanded English scene brief for the layout generator."""
    brief = brief.strip()
    if not brief:
        raise ValueError("Brief is empty")

    client = _get_client(timeout)
    user_content = (
        "Original user brief (any language):\n"
        f"{brief}\n\n"
        "Write ONE enhanced scene brief in English only. It will be pasted into the layout generator and into text-to-3D / image-to-3D pipelines — maximize concrete, checkable visual detail while staying internally consistent."
    )
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=ENHANCE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    if message.stop_reason == "max_tokens":
        raise ValueError("응답이 잘렸습니다. 짧은 입력으로 다시 시도해주세요.")
    return _strip_plain_text_response(raw)
