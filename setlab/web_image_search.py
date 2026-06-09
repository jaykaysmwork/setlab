"""Web image search and download for reference-based 3D generation.

When the user's prompt contains instructions like "search the web", "find images",
"look up photos", etc., this module fetches real reference images from DuckDuckGo
and stores them so HD mesh generation uses them instead of AI-generated images.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import List, Optional

import httpx

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
            model="claude-haiku-4-5-20251001",
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


def extract_search_query(prompt: str) -> str:
    """Extract the main subject to search for from the prompt.

    Falls back to Claude if ambiguous, but tries simple heuristics first.
    """
    # Remove the search instruction clauses and keep the subject
    cleaned = re.sub(
        r"(search\s+(the\s+)?web.*?[.,]|find\s+images?.*?[.,]|"
        r"look\s+up.*?[.,]|collect.*?[.,]|gather.*?[.,]|"
        r"웹에서.*?[.,]|이미지를?\s*(검색|찾아|수집).*?[.,]|자료\s*(수집|검색).*?[.,])",
        " ",
        prompt,
        flags=re.IGNORECASE,
    ).strip()

    # Take first sentence or up to 80 chars as the query subject
    first_sentence = re.split(r"[.!?\n]", cleaned)[0].strip()
    query = first_sentence[:120] if first_sentence else prompt[:120]
    return query


def search_images(query: str, max_results: int = 10) -> List[str]:
    """Search DuckDuckGo for image URLs matching the query."""
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
) -> List[Path]:
    """Download images from URLs to out_dir. Returns list of saved paths."""
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
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "image" not in content_type:
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
) -> List[Path]:
    """High-level: search DuckDuckGo + download images. Returns saved paths."""
    logger.info("[WebSearch] Searching for: %s (max=%d)", query, max_images)
    urls = search_images(query, max_results=max_images + 5)
    if not urls:
        logger.warning("[WebSearch] No image URLs found for query: %s", query)
        return []
    return download_images(urls, out_dir, max_images=max_images)
