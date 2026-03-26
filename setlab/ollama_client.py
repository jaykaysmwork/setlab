from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from setlab.llm_json import parse_llm_json_object
from setlab.prompts import layout_system_prompt, user_message

DEFAULT_OLLAMA = "http://127.0.0.1:11434"


def generate_raw(
    brief: str,
    *,
    model: str,
    base_url: str = DEFAULT_OLLAMA,
    timeout: float = 120.0,
    max_modules: Optional[int] = None,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": layout_system_prompt(max_modules)},
            {"role": "user", "content": user_message(brief)},
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    content = data.get("message", {}).get("content")
    if not content:
        raise RuntimeError(f"Unexpected Ollama response: {data!r}")
    return parse_llm_json_object(content)
