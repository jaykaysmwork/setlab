"""Multi-view reference image generation for 3D reconstruction.

Backends (``IMAGE_GEN_BACKEND``):

- **flux** — BFL FLUX 1.1 Pro REST API (``FLUX_API_KEY``).
- **google** / **google_image** — Google Gemini image models via ``generate_content``
  with image output (``GOOGLE_API_KEY``, ``GOOGLE_IMAGE_MODEL``).

Prompt text is shared: use :func:`_build_prompt` for module views and the same
pipeline for texture reference images in :func:`generate_texture_reference_png_bytes`.
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

BackendName = Literal["flux", "google"]

API_BASE = "https://api.bfl.ai/v1"
MODEL_ENDPOINT = "/flux-pro-1.1"
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 1024
POLL_INTERVAL = 1.0
GENERATE_TIMEOUT = 120

DEFAULT_GOOGLE_IMAGE_MODEL = "gemini-3-pro-image-preview"

VIEWS = [
    ("front", "front view, straight-on, eye level, centered in frame"),
    ("left", "left side view, exactly 90 degrees rotated from front, centered"),
    ("back", "rear view, exactly 180 degrees from front, centered"),
    ("right", "right side view, exactly 270 degrees from front, centered"),
]

# ---------------------------------------------------------------------------
# Description cleaner — strips environment / lighting / weather noise so that
# image generators and Rodin receive a pure object description.
# ---------------------------------------------------------------------------

_ENV_STRIP_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"reflecting\s+[\w\-]+\s+(?:sky|sun\w*|light|clouds?)",
        r"(?:amber|golden|warm|cool|blue|pink|orange|red)\s+sky",
        r"(?:at|during|in)\s+(?:golden[\s_]hour|sunset|sunrise|dawn|dusk|twilight|noon|night|midday)",
        r"(?:golden[\s_]hour|sunset|sunrise|dawn|dusk|twilight)\s+(?:light(?:ing)?|glow|sky|sun)",
        r"(?:setting|rising|low[\s\-]angle|overhead)\s+sun\b",
        r"lit\s+by\s+(?:the\s+)?(?:setting|rising|low|warm|amber)\s+sun\w*",
        r"casting\s+(?:long|short|raking|harsh|dramatic)\s+shadows?\b[\w\s,]*",
        r"(?:long|raking|dramatic|harsh)\s+shadows?\s+(?:east|west|north|south)\w*",
        r"volumetric\s+(?:dust|haze|fog|mist|light|rays?)",
        r"lens\s+flare\w*",
        r"god[\s\-]?rays?",
        r"(?:sun|moon|star)\s*(?:light|beam|ray)s?",
        r"(?:ambient|environmental|atmospheric)\s+(?:light(?:ing)?|haze|glow)",
        r"camera\s+at\s+[\w\+\-\.]+m\s+looking\s+[\w\-]+",
        r"sun\s+azimuth\s+[~≈]?\d+\s*(?:deg|°|degrees?)",
        r"sun\s+altitude\s+[~≈]?\d+\s*(?:deg|°|degrees?)",
        r"\d{4,5}\s*K\b",
    ]
]


def clean_description_for_3d(description: str, max_len: int = 280) -> str:
    """Strip environment/lighting references and truncate for 3D generation."""
    text = description
    for pat in _ENV_STRIP_PATTERNS:
        text = pat.sub("", text)

    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip().strip(",").strip()

    if len(text) > max_len:
        cut = text[:max_len]
        last_sep = max(cut.rfind(","), cut.rfind("."))
        if last_sep > max_len // 2:
            text = cut[:last_sep].strip()
        else:
            text = cut.rstrip()

    return text or description[:max_len]

_BACKEND_ALIASES: Dict[str, BackendName] = {
    "flux": "flux",
    "bfl": "flux",
    "google": "google",
    "google_image": "google",
    "gemini": "google",
}


def image_gen_backend() -> BackendName:
    """Resolved backend from ``IMAGE_GEN_BACKEND`` (default: ``flux``)."""
    raw = (os.environ.get("IMAGE_GEN_BACKEND") or "flux").strip().lower()
    if raw in _BACKEND_ALIASES:
        return _BACKEND_ALIASES[raw]
    raise RuntimeError(
        f"Unknown IMAGE_GEN_BACKEND={raw!r}; use flux, google, or google_image."
    )


def _api_key() -> str:
    key = os.environ.get("FLUX_API_KEY", "")
    if not key:
        raise RuntimeError(
            "FLUX_API_KEY not set. Get one at https://docs.bfl.ai"
        )
    return key


def _google_api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set (required when IMAGE_GEN_BACKEND=google)."
        )
    return key


def _google_image_model() -> str:
    return (os.environ.get("GOOGLE_IMAGE_MODEL") or DEFAULT_GOOGLE_IMAGE_MODEL).strip()


def _google_image_aspect_ratio() -> str:
    return (os.environ.get("GOOGLE_IMAGE_ASPECT_RATIO") or "1:1").strip()


def _ensure_credentials_for_backend(backend: BackendName) -> None:
    if backend == "flux":
        _api_key()
    else:
        _google_api_key()


def _build_prompt(description: str, view_instruction: str) -> str:
    clean = clean_description_for_3d(description, max_len=220)
    return (
        f"3D asset reference photo of a single object: {clean}. "
        f"Camera angle: {view_instruction}. "
        "PURE WHITE seamless studio background, completely isolated object, "
        "absolutely NO sky, NO ground plane, NO environment, NO other objects. "
        "Soft even studio lighting from all sides, neutral color temperature, no harsh shadows. "
        "Object perfectly centered in frame, consistent scale. "
        "Sharp material detail on surfaces. Product photography style."
    )


def _generate_single_image_flux(
    client: httpx.Client, prompt: str
) -> Optional[bytes]:
    """Submit a FLUX generation request, poll until ready, return image bytes."""
    headers = {
        "accept": "application/json",
        "x-key": _api_key(),
        "Content-Type": "application/json",
    }

    resp = client.post(
        f"{API_BASE}{MODEL_ENDPOINT}",
        headers=headers,
        json={
            "prompt": prompt,
            "width": IMAGE_WIDTH,
            "height": IMAGE_HEIGHT,
            "output_format": "png",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    polling_url = data.get("polling_url")
    if not polling_url:
        logger.error("[ImageGen] No polling_url in response: %s", data)
        return None

    start = time.monotonic()
    while True:
        poll_resp = client.get(polling_url, headers=headers, timeout=30.0)
        poll_resp.raise_for_status()
        result = poll_resp.json()
        status = result.get("status", "")

        if status == "Ready":
            sample_url = result.get("result", {}).get("sample", "")
            if not sample_url:
                logger.error("[ImageGen] Ready but no sample URL: %s", result)
                return None
            img_resp = client.get(sample_url, timeout=60.0, follow_redirects=True)
            img_resp.raise_for_status()
            return img_resp.content

        if status in ("Error", "Failed"):
            logger.error("[ImageGen] Generation failed: %s", result)
            return None

        elapsed = time.monotonic() - start
        if elapsed > GENERATE_TIMEOUT:
            logger.error("[ImageGen] Timed out after %.0fs", elapsed)
            return None

        time.sleep(POLL_INTERVAL)


def _extract_image_bytes_from_generate_content(response: Any) -> Optional[bytes]:
    """First image part from a ``generate_content`` response, if any."""
    if getattr(response, "prompt_feedback", None) is not None and not (
        response.candidates or []
    ):
        logger.error("[ImageGen] Google: no candidates (prompt_feedback=%s)", response.prompt_feedback)
        return None
    candidates = response.candidates or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = (content.parts if content else None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
            img = part.as_image() if hasattr(part, "as_image") else None
            if img is not None and getattr(img, "image_bytes", None):
                return img.image_bytes
    return None


def _generate_single_image_google(prompt: str) -> Optional[bytes]:
    """Gemini (or compatible) image generation via ``generate_content``."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_google_api_key())
    model = _google_image_model()
    aspect = _google_image_aspect_ratio()

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                image_config=types.ImageConfig(aspect_ratio=aspect),
            ),
        )
    except Exception as e:
        logger.error("[ImageGen] Google generate_content failed: %s", e)
        return None

    data = _extract_image_bytes_from_generate_content(response)
    if not data:
        logger.error("[ImageGen] Google: no image bytes in response (model=%s)", model)
    return data


_MULTITURN_VIEW_PROMPTS = [
    (
        "front",
        "Generate a 3D asset reference photo of: {desc}. "
        "Camera angle: front view, straight-on, eye level, centered in frame. "
        "PURE WHITE seamless studio background, completely isolated object. "
        "Soft even studio lighting from all sides, neutral color temperature, no harsh shadows. "
        "Sharp material detail on surfaces. Product photography style.",
    ),
    (
        "left",
        "Now rotate the camera exactly 90 degrees to the LEFT to show the LEFT side "
        "of this exact same object. "
        "Keep the identical white background, same studio lighting, same object scale and framing. "
        "Do NOT change or redesign the object — it must be the same one from the previous image.",
    ),
    (
        "back",
        "Now rotate the camera exactly 180 degrees from the original front to show the BACK "
        "of this exact same object. "
        "Keep the identical white background, same studio lighting, same object scale and framing. "
        "Do NOT change or redesign the object.",
    ),
    (
        "right",
        "Now rotate the camera exactly 90 degrees to the RIGHT (270 degrees from front) "
        "to show the RIGHT side of this exact same object. "
        "Keep the identical white background, same studio lighting, same object scale and framing. "
        "Do NOT change or redesign the object.",
    ),
]


def _generate_multiview_google(
    description: str,
    images_dir: Path,
    module_id: str = "",
    on_progress: Optional[ProgressCallback] = None,
    reference_image_path: Optional[Path] = None,
) -> List[Path]:
    """Consistent multi-view images via Gemini multi-turn chat session.

    If reference_image_path is provided, includes the real photo in the first
    message so Gemini grounds the generation in the actual building appearance.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_google_api_key())
    model = _google_image_model()
    aspect = _google_image_aspect_ratio()

    config = types.GenerateContentConfig(
        response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
        image_config=types.ImageConfig(aspect_ratio=aspect),
    )

    chat = client.chats.create(model=model, config=config)
    clean = clean_description_for_3d(description, max_len=220)
    saved: List[Path] = []

    for i, (view_name, prompt_template) in enumerate(_MULTITURN_VIEW_PROMPTS):
        if on_progress:
            on_progress(module_id, f"image_{view_name}", int((i / 4) * 100))

        base_prompt = prompt_template.format(desc=clean) if "{desc}" in prompt_template else prompt_template

        # First view: optionally prepend reference image for visual grounding
        if i == 0 and reference_image_path and reference_image_path.is_file():
            try:
                ref_b64, mime = _ref_to_b64_jpeg(reference_image_path)
                import base64 as _b64
                ref_bytes = _b64.standard_b64decode(ref_b64)
                message = [
                    types.Part(inline_data=types.Blob(data=ref_bytes, mime_type=mime)),
                    types.Part(text=(
                        "The image above is a real-world reference photo of the target subject. "
                        "Use it as visual guidance for the exact colors, materials, proportions, "
                        "and architectural details — replicate its appearance faithfully.\n\n"
                        + base_prompt
                    )),
                ]
            except Exception as e:
                logger.warning("[ImageGen] %s: could not attach reference image: %s", module_id, e)
                message = base_prompt
        else:
            message = base_prompt

        try:
            response = chat.send_message(message)
            image_bytes = _extract_image_bytes_from_generate_content(response)

            if image_bytes:
                img = Image.open(BytesIO(image_bytes))
                out_path = images_dir / f"{view_name}.png"
                img.save(str(out_path), format="PNG")
                saved.append(out_path)
                logger.info(
                    "[ImageGen] %s/%s saved (%dx%d) google-multiturn",
                    module_id, view_name, img.width, img.height,
                )
            else:
                logger.warning(
                    "[ImageGen] %s/%s: no image in response (google-multiturn)",
                    module_id, view_name,
                )
        except Exception as e:
            logger.error("[ImageGen] %s/%s error: %s", module_id, view_name, e)

    return saved


def _pick_best_reference_image(ref_files: List[Path]) -> Path:
    """Pick the largest (highest-quality) file from a list of reference images."""
    return max(ref_files, key=lambda p: p.stat().st_size)


def _ref_to_b64_jpeg(ref_path: Path) -> tuple[str, str]:
    """Load a reference image and return (base64_string, mime_type) as JPEG."""
    import base64 as _b64
    raw = ref_path.read_bytes()
    try:
        img_obj = Image.open(BytesIO(raw)).convert("RGB")
        buf = BytesIO()
        img_obj.save(buf, format="JPEG", quality=85)
        return _b64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"
    except Exception:
        mime = {".png": "image/png", ".webp": "image/webp"}.get(ref_path.suffix.lower(), "image/jpeg")
        return _b64.standard_b64encode(raw).decode(), mime


def _generate_single_image_flux_with_ref(
    client: httpx.Client,
    prompt: str,
    ref_b64: str,
    strength: float = 0.35,
) -> Optional[bytes]:
    """FLUX Pro Ultra with image_prompt for visual reference guidance.

    Falls back gracefully (returns None) if the endpoint rejects the request,
    so the caller can fall through to standard text-to-image.
    """
    headers = {
        "accept": "application/json",
        "x-key": _api_key(),
        "Content-Type": "application/json",
    }
    try:
        resp = client.post(
            f"{API_BASE}/flux-pro-1.1-ultra",
            headers=headers,
            json={
                "prompt": prompt,
                "image_prompt": ref_b64,
                "image_prompt_strength": round(max(0.05, min(0.95, strength)), 2),
                "width": IMAGE_WIDTH,
                "height": IMAGE_HEIGHT,
                "output_format": "png",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("[ImageGen] FLUX ultra ref request failed (%s) — will fall back to text-only", e)
        return None

    data = resp.json()
    polling_url = data.get("polling_url")
    if not polling_url:
        logger.warning("[ImageGen] FLUX ultra: no polling_url — will fall back")
        return None

    start = time.monotonic()
    while True:
        try:
            poll = client.get(polling_url, headers=headers, timeout=30.0)
            poll.raise_for_status()
            result = poll.json()
        except Exception as e:
            logger.warning("[ImageGen] FLUX ultra poll error: %s", e)
            return None
        status = result.get("status", "")
        if status == "Ready":
            url = result.get("result", {}).get("sample", "")
            if not url:
                return None
            r = client.get(url, timeout=60.0, follow_redirects=True)
            r.raise_for_status()
            return r.content
        if status in ("Error", "Failed"):
            logger.error("[ImageGen] FLUX ultra failed: %s", result)
            return None
        if time.monotonic() - start > GENERATE_TIMEOUT:
            logger.error("[ImageGen] FLUX ultra timed out")
            return None
        time.sleep(POLL_INTERVAL)


def _generate_views_flux_with_ref(
    client: httpx.Client,
    description: str,
    ref_path: Path,
    images_dir: Path,
    module_id: str,
    on_progress: Optional[ProgressCallback] = None,
) -> List[Path]:
    """Generate 4 Rodin-ready views (front/left/back/right) using FLUX Ultra
    with the given reference photo as visual guidance."""
    ref_b64, _ = _ref_to_b64_jpeg(ref_path)
    clean = clean_description_for_3d(description, max_len=180)
    saved: List[Path] = []

    for i, (view_name, view_instruction) in enumerate(VIEWS):
        if on_progress:
            on_progress(module_id, f"image_{view_name}", int((i / len(VIEWS)) * 100))

        prompt = (
            f"3D asset reference photo of: {clean}. "
            f"Camera angle: {view_instruction}. "
            "PURE WHITE seamless studio background, completely isolated object. "
            "Soft even studio lighting, no harsh shadows. Product photography style."
        )

        image_bytes = _generate_single_image_flux_with_ref(client, prompt, ref_b64, strength=0.35)

        if not image_bytes:
            logger.info("[ImageGen] %s/%s: ref-guided failed, using text-only fallback", module_id, view_name)
            image_bytes = _generate_single_image_flux(client, _build_prompt(description, view_instruction))

        if image_bytes:
            img = Image.open(BytesIO(image_bytes))
            out_path = images_dir / f"{view_name}.png"
            img.save(str(out_path), format="PNG")
            saved.append(out_path)
            logger.info("[ImageGen] %s/%s ref-guided saved (%dx%d)", module_id, view_name, img.width, img.height)
        else:
            logger.warning("[ImageGen] %s/%s: both ref and fallback failed", module_id, view_name)

    return saved


def generate_image_bytes(prompt: str) -> Optional[bytes]:
    """Run the configured backend for a single full prompt string."""
    backend = image_gen_backend()
    _ensure_credentials_for_backend(backend)
    if backend == "flux":
        with httpx.Client() as client:
            return _generate_single_image_flux(client, prompt)
    return _generate_single_image_google(prompt)


def generate_texture_reference_png_bytes(
    texture_prompt: str,
    *,
    context: str = "",
) -> Optional[bytes]:
    """Single reference image for Hyper3D rodin_texture_only.

    Uses the same ``IMAGE_GEN_BACKEND`` as module multi-view generation.
    Blocking; call from ``asyncio.to_thread`` in async code.
    """
    backend = image_gen_backend()
    _ensure_credentials_for_backend(backend)

    ctx = (context or "").strip()
    if len(ctx) > 280:
        ctx = ctx[:277] + "..."
    body = (
        f"Photorealistic architectural surface reference for 3D PBR texturing. "
        f"Material / weathering goal: {texture_prompt.strip()[:500]}. "
    )
    if ctx:
        body += f"Structure context: {ctx}. "
    body += (
        "Single facade fragment or wall section, even soft lighting, fills frame, "
        "high-frequency surface detail, no people, no watermark, no text."
    )

    if backend == "flux":
        with httpx.Client() as client:
            return _generate_single_image_flux(client, body)
    return _generate_single_image_google(body)


def generate_module_images(
    module_id: str,
    description: str,
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
    web_refs_dir: Optional[Path] = None,
) -> List[Path]:
    """Generate multi-view images for one module using the configured backend.

    If web_refs_dir contains pre-downloaded reference images, copies them into
    the module's images folder and skips AI generation entirely.
    """
    images_dir = out_dir / "images" / module_id
    images_dir.mkdir(parents=True, exist_ok=True)

    # Use web reference images as visual guidance for generating consistent views
    if web_refs_dir and web_refs_dir.is_dir():
        ref_files = sorted(
            (p for p in web_refs_dir.iterdir()
             if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if ref_files:
            best_ref = ref_files[0]
            backend = image_gen_backend()
            logger.info(
                "[ImageGen] %s: reference-guided generation from %s (backend=%s)",
                module_id, best_ref.name, backend,
            )
            try:
                _ensure_credentials_for_backend(backend)
                if backend == "flux":
                    with httpx.Client() as _client:
                        saved = _generate_views_flux_with_ref(
                            _client, description, best_ref, images_dir, module_id, on_progress
                        )
                else:
                    saved = _generate_multiview_google(
                        description, images_dir, module_id=module_id,
                        on_progress=on_progress, reference_image_path=best_ref,
                    )
                if saved:
                    if on_progress:
                        on_progress(module_id, "images_done", 100)
                    return saved
                logger.warning("[ImageGen] %s: ref-guided returned no images, falling through to text-only", module_id)
            except Exception as e:
                logger.error("[ImageGen] %s: ref-guided generation failed (%s), falling through", module_id, e)

    backend = image_gen_backend()
    _ensure_credentials_for_backend(backend)

    if backend == "google":
        saved = _generate_multiview_google(
            description, images_dir, module_id=module_id, on_progress=on_progress,
        )
        if on_progress:
            on_progress(module_id, "images_done", 100)
        return saved

    saved: List[Path] = []

    with ExitStack() as stack:
        client: Optional[httpx.Client] = None
        if backend == "flux":
            client = stack.enter_context(httpx.Client())

        for i, (view_name, view_instruction) in enumerate(VIEWS):
            if on_progress:
                on_progress(module_id, f"image_{view_name}", int((i / len(VIEWS)) * 100))

            prompt = _build_prompt(description, view_instruction)

            try:
                assert client is not None
                image_bytes = _generate_single_image_flux(client, prompt)
                if image_bytes:
                    img = Image.open(BytesIO(image_bytes))
                    out_path = images_dir / f"{view_name}.png"
                    img.save(str(out_path), format="PNG")
                    saved.append(out_path)
                    logger.info(
                        "[ImageGen] %s/%s saved (%dx%d) backend=flux",
                        module_id, view_name, img.width, img.height,
                    )
                else:
                    logger.warning(
                        "[ImageGen] %s/%s: no image returned backend=flux",
                        module_id, view_name,
                    )
            except Exception as e:
                logger.error("[ImageGen] %s/%s error: %s", module_id, view_name, e)

    if on_progress:
        on_progress(module_id, "images_done", 100)

    return saved


def generate_all_module_images(
    modules: List[Dict[str, Any]],
    out_dir: Path,
    on_progress: Optional[ProgressCallback] = None,
    web_refs_dir: Optional[Path] = None,
) -> Dict[str, List[Path]]:
    """Generate multi-view images for all modules with parallel module processing.

    If web_refs_dir is provided, building-type modules use those real images
    instead of AI-generated ones.
    """
    max_workers = min(len(modules), 4)
    results: Dict[str, List[Path]] = {}

    def _gen_one(idx: int, m: Dict[str, Any]) -> tuple[str, List[Path]]:
        mid = m["id"]
        raw_desc = m.get("description") or m.get("asset", "generic building")
        desc = clean_description_for_3d(raw_desc)
        if on_progress:
            on_progress(mid, "image_start", 0)
        # Use web refs for building-type modules
        is_building = "building" in m.get("asset", "")
        refs = web_refs_dir if (web_refs_dir and is_building) else None
        paths = generate_module_images(mid, desc, out_dir, on_progress, web_refs_dir=refs)
        logger.info("[ImageGen] %d/%d modules done", idx + 1, len(modules))
        return mid, paths

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_gen_one, i, m): m["id"]
            for i, m in enumerate(modules)
        }
        for future in as_completed(futures):
            mid = futures[future]
            try:
                mid, paths = future.result()
                results[mid] = paths
            except Exception as e:
                logger.error("[ImageGen] Module %s failed: %s", mid, e)
                results[mid] = []

    return results
