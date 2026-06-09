"""Real-time scene modification — Claude classifies prompt changes into tiers.

Three tiers of modification speed:
  instant  — environment/lighting parameter tweaks (applied in UE within 1 frame)
  fast     — material re-texture via texture-edit API (30-60s)
  moderate — full asset regeneration for specific modules (3-6 min)

The classify() function sends the instruction + current spec to Claude and
returns a structured ModifyResult with the tier, affected modules, and
the commands to execute.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

import anthropic

from setlab.llm_json import parse_llm_json_object
from setlab.model_ids import CLAUDE_SONNET

CLASSIFY_SYSTEM = """You are a real-time scene modification classifier for a virtual production pipeline.

Given a current scene spec (JSON) and a director's instruction, classify the modification into exactly ONE tier and output the commands to execute.

TIERS:
  "instant" — lighting, fog, atmosphere, color temperature, time of day changes.
              These are parameter tweaks that apply in-engine within one frame.
  "fast"    — texture/material changes on specific modules (e.g. "make the wall rougher",
              "change the brick to stone"). These trigger an AI re-texture (30-60s).
  "moderate"— geometry/shape changes that require full 3D regeneration of specific modules
              (e.g. "replace the building with a church", "add a fountain in the center").

Return ONLY valid JSON matching this schema:
{
  "tier": "instant" | "fast" | "moderate",
  "summary": "1-sentence description of what changes",
  "module_ids": ["id1", "id2"],
  "commands": { ... tier-specific payload ... }
}

TIER-SPECIFIC COMMANDS:

For "instant" — commands is an environment block update (partial):
{
  "tier": "instant",
  "summary": "Change to sunset lighting",
  "module_ids": [],
  "commands": {
    "environment": {
      "time_of_day": "sunset",
      "sun_intensity": 4.0,
      "sun_color_temp": 3200,
      "fog_density": 0.04
    }
  }
}

For "fast" — commands has a texture prompt per module:
{
  "tier": "fast",
  "summary": "Make north wall rougher stone",
  "module_ids": ["wall_north"],
  "commands": {
    "retexture": {
      "wall_north": "rough hewn stone wall with deep mortar joints and weathered surface"
    }
  }
}

For "moderate" — commands has updated module descriptions for regeneration:
{
  "tier": "moderate",
  "summary": "Replace tavern with a church",
  "module_ids": ["building_east_1"],
  "commands": {
    "regenerate": {
      "building_east_1": {
        "description": "Gothic stone church with pointed arched windows and bell tower",
        "scale": [12, 20, 15]
      }
    }
  }
}

RULES:
- Always prefer the FASTEST tier that can achieve the result.
- module_ids is empty for "instant" (environment-only changes).
- For "fast", only list modules whose surface appearance changes.
- For "moderate", only list modules whose geometry/shape must change.
- If the instruction mentions both lighting AND texture changes, pick the slower tier.
- The user may write in any language (Korean, English, etc.)."""


_clients: Dict[float, anthropic.Anthropic] = {}
_client_lock = threading.Lock()


def _get_client(timeout: float = 60.0) -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    # Pool one client per distinct timeout so we reuse the httpx connection pool
    # instead of building a new client each call (mirrors claude_client).
    client = _clients.get(timeout)
    if client is None:
        with _client_lock:
            client = _clients.get(timeout)
            if client is None:
                client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
                _clients[timeout] = client
    return client


def classify(
    spec: Dict[str, Any],
    instruction: str,
    *,
    model: str = CLAUDE_SONNET,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Classify a modification instruction and return structured commands.

    Returns dict with keys: tier, summary, module_ids, commands.
    """
    client = _get_client(timeout)

    modules_brief = json.dumps(
        [{"id": m["id"], "asset": m.get("asset", ""), "description": m.get("description", "")}
         for m in spec.get("modules", [])],
        indent=2,
    )
    env_brief = json.dumps(spec.get("environment", {}), indent=2)

    user_content = (
        f"Current scene: {spec.get('title', '')} ({spec.get('era_style', '')})\n\n"
        f"Environment:\n{env_brief}\n\n"
        f"Modules:\n{modules_brief}\n\n"
        f"Director's instruction: {instruction.strip()}\n\n"
        "Classify and return the modification JSON."
    )

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=CLASSIFY_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = message.content[0].text
    if message.stop_reason == "max_tokens":
        raise ValueError(
            "수정 분류 JSON이 토큰 한도로 잘렸습니다. 더 간단한 지시로 다시 시도해주세요."
        )
    result = parse_llm_json_object(raw)

    if result.get("tier") not in ("instant", "fast", "moderate"):
        raise ValueError(f"Invalid tier: {result.get('tier')}")

    return result
