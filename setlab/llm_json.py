"""Parse JSON objects from LLM text; tolerate common syntax mistakes."""

from __future__ import annotations

import json
from typing import Any, Dict


def extract_json_object(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response")
    if text.startswith("```"):
        # Drop the opening fence line (```lang). A single-line ```{...}``` fence
        # has no newline, so fall back to stripping just the leading backticks.
        nl = text.find("\n")
        text = text[nl + 1 :] if nl != -1 else text[3:]
        text = text.rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return text


def parse_llm_json_object(text: str) -> Dict[str, Any]:
    """Strict json.loads first; on failure try json-repair (missing commas, trailing commas, etc.)."""
    blob = extract_json_object(text)
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        try:
            import json_repair

            repaired = json_repair.loads(blob)
            if not isinstance(repaired, dict):
                raise TypeError("expected object at root")
            return repaired
        except Exception as repair_err:
            raise ValueError(
                "레이아웃 JSON을 읽지 못했습니다. "
                "모델이 쉼표를 빼먹었거나 출력이 잘렸을 수 있습니다. "
                f"상세: {e!s}"
            ) from repair_err
