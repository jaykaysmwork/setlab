"""Web image search and download for reference-based 3D generation.

When the user's prompt contains instructions like "search the web", "find images",
"look up photos", etc., this module fetches real reference images from DuckDuckGo
and stores them so HD mesh generation uses them instead of AI-generated images.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from setlab.model_ids import CLAUDE_HAIKU

logger = logging.getLogger(__name__)

# Fast regex pre-check — common obvious patterns (avoids Claude call for clear cases)
_FAST_PATTERNS = [
    r"search\s+(the\s+)?(web|internet|online|google)",
    r"search\s+(its\s+|the\s+)?(image|photo|picture)",
    r"find\s+(images?|photos?|pictures?|references?)\s+(from|on|in)\s+(the\s+)?(web|internet|google|online)",
    r"look\s+up\s+(images?|photos?|references?|pictures?)",
    r"(web|internet|online)\s+search",
    r"google\s+(it|images?|photos?|pictures?|this)",
    r"(collect|gather|fetch|grab|pull|get|download)\s+(images?|photos?|pictures?|references?)",
    r"browse\s+(the\s+)?(web|internet|online)\s+for",
    r"check\s+(online|the\s+web|internet)\s+for",
    r"온라인에서\s*(이미지|사진|자료|참고|레퍼런스|찾아|검색)",
    r"reference\s+images?\s+from\s+(the\s+)?(web|internet|online)",
    r"use\s+real\s+(images?|photos?|pictures?)",
    r"(웹|인터넷|구글|온라인)에서\s*(이미지|사진|자료|참고|레퍼런스)",
    r"이미지를?\s*(검색|찾아|수집|가져)",
    r"사진을?\s*(검색|찾아|수집|가져)",
    r"자료\s*(수집|검색|찾아)",
    r"레퍼런스\s*(수집|검색|찾아)",
]

_FAST_COMPILED = [re.compile(p, re.IGNORECASE) for p in _FAST_PATTERNS]


def has_search_intent(prompt: str) -> bool:
    """Detect web image search intent using fast regex + Claude fallback."""
    # Fast path: obvious patterns
    if any(p.search(prompt) for p in _FAST_COMPILED):
        return True
    # Claude fallback: catches any natural language phrasing
    return _claude_detect_search_intent(prompt)


def _claude_detect_search_intent(prompt: str) -> bool:
    """Ask Claude (Haiku) whether the prompt requests web image search."""
    try:
        import anthropic, os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return False
        client = anthropic.Anthropic(api_key=api_key, timeout=10.0)
        msg = client.messages.create(
            model=CLAUDE_HAIKU,
            max_tokens=5,
            system=(
                "Answer only YES or NO. "
                "Does the user's message ask to search the web, internet, or online "
                "for images, photos, pictures, or visual references? "
                "Answer YES even for indirect phrasings like 'get real photos', "
                "'look it up online', 'use actual images', 'browse for references'."
            ),
            messages=[{"role": "user", "content": prompt[:500]}],
        )
        answer = msg.content[0].text.strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.warning("[WebSearch] Claude intent check failed: %s", e)
        return False


def extract_image_count(prompt: str) -> Optional[int]:
    """Return the number of images the user requested, or None if not specified."""
    patterns = [
        r"at\s+least\s+(\d+)",
        r"minimum\s+(\d+)",
        r"(\d+)\s*or\s+more",
        r"(\d+)\s*\+\s*images?",
        r"(\d+)\s*images?",
        r"(\d+)\s*photos?",
        r"(\d+)\s*pictures?",
        r"(\d+)\s*장",
        r"(\d+)\s*개",
        r"최소\s*(\d+)",
        r"(\d+)\s*이상",
        r"최소한\s*(\d+)",
        r"find\s+(\d+)",
        r"search\s+(\d+)",
        r"get\s+(\d+)",
        r"download\s+(\d+)",
        r"collect\s+(\d+)",
        r"(\d+)\s*장\s*이상",
    ]
    for pat in patterns:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 50:
                return n
    return None


def build_image_query(prompt: str) -> Dict[str, Any]:
    """Turn the user's request into a search query + explicit exclusions.

    Honors the constraints the user actually wrote — interior vs exterior, day vs
    night, color vs b/w, "no gif / no moving images", etc. — by asking Claude to
    distill the whole prompt into a focused English Google-Images query plus a few
    structured flags. Nothing is hardcoded: only what the prompt states is applied.
    Falls back to a simple heuristic if Claude is unavailable.

    Returns ``{"query": str, "exclude_animated": bool}``.
    """
    built = _claude_build_query(prompt)
    if built:
        return built
    return {
        "query": _heuristic_query(prompt),
        "exclude_animated": bool(
            re.search(r"gif|animated|움직이|움짤|moving\s+image", prompt, re.IGNORECASE)
        ),
    }


def _claude_build_query(prompt: str) -> Optional[Dict[str, Any]]:
    """Ask Claude (Haiku) to distill the prompt into {query, exclude_animated}."""
    try:
        import os

        import anthropic

        from setlab.llm_json import parse_llm_json_object

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        client = anthropic.Anthropic(api_key=api_key, timeout=15.0)
        msg = client.messages.create(
            model=CLAUDE_HAIKU,
            max_tokens=150,
            system=(
                "You turn a user's image/scene request into a Google Images search. "
                "The user may write in any language and may state visual constraints "
                "(interior vs exterior, indoor/outdoor, day/night, color vs black-and-white, "
                "no people, no text/logo, no gif/animated/moving images, era/style, etc.). "
                'Return ONLY JSON: {"query": "<concise English Google Images query, 3-8 words, '
                "capturing the main subject AND baking in the visual constraints the user stated "
                "(e.g. 'interior', 'at night', 'black and white')>\", "
                '"exclude_animated": <true ONLY if the user asked to avoid gif/animated/moving '
                "images, else false>}. Do NOT add constraints the user did not state. "
                "The query MUST be in English."
            ),
            messages=[{"role": "user", "content": prompt[:1000]}],
        )
        data = parse_llm_json_object(msg.content[0].text)
        query = str(data.get("query") or "").strip()
        if not query:
            return None
        return {"query": query, "exclude_animated": bool(data.get("exclude_animated"))}
    except Exception as e:
        logger.warning("[WebSearch] Claude query builder failed: %s", e)
        return None


def _heuristic_query(prompt: str) -> str:
    """Fallback query: strip search-instruction clauses, keep the first sentence."""
    cleaned = re.sub(
        r"(search\s+(the\s+)?web.*?[.,]|find\s+images?.*?[.,]|"
        r"look\s+up.*?[.,]|collect.*?[.,]|gather.*?[.,]|"
        r"웹에서.*?[.,]|이미지를?\s*(검색|찾아|수집).*?[.,]|자료\s*(수집|검색).*?[.,])",
        " ",
        prompt,
        flags=re.IGNORECASE,
    ).strip()
    first_sentence = re.split(r"[.!?\n]", cleaned)[0].strip()
    return first_sentence[:120] if first_sentence else prompt[:120]


def extract_search_query(prompt: str) -> str:
    """Back-compat: the search query that honors the prompt (via build_image_query)."""
    return build_image_query(prompt)["query"]


def search_images(query: str, max_results: int = 10) -> List[str]:
    """Search for image URLs matching the query.

    Backend is selected by ``IMAGE_SEARCH_BACKEND`` (default ``duckduckgo``):
    - ``serper`` — Serper.dev Google Images API (needs ``SERPER_API_KEY``). Managed,
      reliable; recommended.
    - ``google`` — Google Custom Search JSON API (needs ``GOOGLE_SEARCH_API_KEY`` +
      ``GOOGLE_SEARCH_CX``). NOTE: closed to new Google customers since 2025.
    - anything else — DuckDuckGo (keyless, free).
    Any configured backend falls back to DuckDuckGo when it returns nothing.
    """
    backend = os.environ.get("IMAGE_SEARCH_BACKEND", "duckduckgo").strip().lower()
    if backend == "serper":
        urls = _search_images_serper(query, max_results)
        if urls:
            return urls
        logger.warning("[WebSearch] Serper returned nothing — falling back to DuckDuckGo")
    elif backend in ("google", "google_image", "cse"):
        urls = _search_images_google(query, max_results)
        if urls:
            return urls
        logger.warning("[WebSearch] Google search returned nothing — falling back to DuckDuckGo")
    return _search_images_ddg(query, max_results)


def _search_images_serper(query: str, max_results: int = 10) -> List[str]:
    """Google Images via Serper.dev (managed API). Returns full-res image URLs."""
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if not key:
        logger.warning("[WebSearch] IMAGE_SEARCH_BACKEND=serper but SERPER_API_KEY is not set")
        return []
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://google.serper.dev/images",
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": max(max_results, 10)},
            )
            if resp.status_code != 200:
                logger.warning("[WebSearch] Serper HTTP %d: %s", resp.status_code, resp.text[:200])
                return []
            images = resp.json().get("images") or []
            urls = [it["imageUrl"] for it in images if it.get("imageUrl")]
            return urls[:max_results]
    except Exception as e:
        logger.warning("[WebSearch] Serper failed: %s", e)
        return []


def _search_images_google(query: str, max_results: int = 10) -> List[str]:
    """Google Custom Search JSON API (image search). Returns image URLs."""
    key = os.environ.get("GOOGLE_SEARCH_API_KEY", "").strip()
    cx = os.environ.get("GOOGLE_SEARCH_CX", "").strip()
    if not key or not cx:
        logger.warning(
            "[WebSearch] IMAGE_SEARCH_BACKEND=google but GOOGLE_SEARCH_API_KEY / "
            "GOOGLE_SEARCH_CX is not set"
        )
        return []
    urls: List[str] = []
    try:
        with httpx.Client(timeout=15.0) as client:
            start = 1
            # Custom Search returns <=10 results/request; paginate via `start`
            # (the API exposes up to 100 results total, i.e. start <= 91).
            while len(urls) < max_results and start <= 91:
                num = min(10, max_results - len(urls))
                resp = client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": key,
                        "cx": cx,
                        "q": query,
                        "searchType": "image",
                        "num": num,
                        "start": start,
                        "safe": "active",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "[WebSearch] Google Custom Search HTTP %d: %s",
                        resp.status_code, resp.text[:200],
                    )
                    break
                items = resp.json().get("items") or []
                if not items:
                    break
                urls.extend(it["link"] for it in items if it.get("link"))
                start += len(items)
    except Exception as e:
        logger.warning("[WebSearch] Google Custom Search failed: %s", e)
    return urls[:max_results]


def _search_images_ddg(query: str, max_results: int = 10) -> List[str]:
    """Search DuckDuckGo for image URLs matching the query (keyless)."""
    from ddgs import DDGS

    last_err: Exception | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(2 * attempt)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(
                    query,
                    max_results=max_results * 2,
                    type_image="photo",
                    safesearch="moderate",
                ))
            urls = [r["image"] for r in results if r.get("image")]
            return urls[:max_results]
        except Exception as e:
            last_err = e
            logger.warning("[WebSearch] DuckDuckGo attempt %d failed: %s", attempt + 1, e)

    logger.error("[WebSearch] All attempts failed: %s", last_err)
    return []


def download_images(
    urls: List[str],
    out_dir: Path,
    max_images: int = 10,
    timeout: float = 15.0,
    exclude_animated: bool = False,
) -> List[Path]:
    """Download images from URLs to out_dir. Returns list of saved paths.

    When ``exclude_animated`` is set, .gif / ``image/gif`` results are skipped.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Path] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
        for i, url in enumerate(urls):
            if len(saved) >= max_images:
                break
            if exclude_animated and url.lower().split("?")[0].endswith(".gif"):
                continue
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "image" not in content_type:
                    continue
                if exclude_animated and "gif" in content_type.lower():
                    continue

                ext = ".jpg"
                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"

                out_path = out_dir / f"ref_{i:02d}{ext}"
                out_path.write_bytes(resp.content)
                saved.append(out_path)
                logger.info("[WebSearch] Downloaded %s → %s", url[:60], out_path.name)
            except Exception as e:
                logger.warning("[WebSearch] Failed to download %s: %s", url[:60], e)

    logger.info("[WebSearch] Saved %d / %d images to %s", len(saved), len(urls), out_dir)
    return saved


def search_and_download(
    query: str,
    out_dir: Path,
    max_images: int = 10,
    exclude_animated: bool = False,
) -> List[Path]:
    """High-level: search + download images. Returns saved paths."""
    logger.info("[WebSearch] Searching for: %s (max=%d)", query, max_images)
    urls = search_images(query, max_results=max_images + 5)
    if not urls:
        logger.warning("[WebSearch] No image URLs found for query: %s", query)
        return []
    return download_images(urls, out_dir, max_images=max_images, exclude_animated=exclude_animated)
