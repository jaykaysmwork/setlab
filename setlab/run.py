"""
setlab CLI 진입점 + 프로그래밍 API.

CLI:  python -m setlab.run --prompt "sci-fi corridor" --backend ollama
API:  from setlab.run import generate_set
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Union

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from setlab.export_gltf import spec_to_gltf_dict
from setlab.export_usda import spec_to_usda
from setlab.layout_orient import orient_buildings_toward_floors
from setlab.models import SetSpec
from setlab.model_ids import CLAUDE_SONNET

_log = logging.getLogger(__name__)


def parse_max_modules_from_env() -> Optional[int]:
    """MAX_MODULES or SETLAB_MAX_MODULES — positive int caps the modules array."""
    raw = (os.environ.get("MAX_MODULES") or os.environ.get("SETLAB_MAX_MODULES") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw, 10)
    except ValueError:
        return None
    return n if n > 0 else None


def _cap_spec_modules(spec: SetSpec, max_n: Optional[int]) -> SetSpec:
    if max_n is None or max_n <= 0 or len(spec.modules) <= max_n:
        return spec
    n_before = len(spec.modules)
    trimmed = list(spec.modules[:max_n])
    _log.warning("Capped modules from %d to %d (max_modules)", n_before, max_n)
    return spec.model_copy(update={"modules": trimmed})


def _fix_positions(spec: SetSpec) -> SetSpec:
    """Correct module Y positions so boxes sit on the ground plane (Y=0)."""
    fixed = []
    for m in spec.modules:
        px, py, pz = m.position
        sx, sy, sz = m.scale
        # Vegetation and platforms: trust the model's Y (already set to half-height)
        if m.asset in ("mod_platform", "mod_tree", "mod_tree_palm"):
            fixed.append(m)
            continue
        correct_y = sy / 2.0
        fixed.append(m.model_copy(update={"position": (px, correct_y, pz)}))
    spec = spec.model_copy(update={"modules": fixed})
    return spec


def generate_set(
    prompt: str,
    *,
    backend: str = "mock",
    model: str = "qwen2.5-coder:32b",
    ollama_url: str = "http://127.0.0.1:11434",
    out_dir: Union[Path, str] = Path("out/pilot"),
    max_modules: Optional[int] = None,
) -> Tuple[SetSpec, Path]:
    """Run the full pipeline and return (validated spec, output directory).

    max_modules: hard cap on len(modules). None = use MAX_MODULES env if set, else uncapped prompt.
    Raises ValueError on validation failure, RuntimeError on backend errors.
    """
    out = Path(out_dir)
    cap = max_modules if max_modules is not None else parse_max_modules_from_env()

    if backend == "mock":
        from setlab import mock_backend
        raw = mock_backend.generate_raw(prompt)
    elif backend == "claude":
        from setlab import claude_client
        raw = claude_client.generate_raw(prompt, model=model, max_modules=cap)
    else:
        from setlab import ollama_client
        raw = ollama_client.generate_raw(
            prompt, model=model, base_url=ollama_url, max_modules=cap
        )

    try:
        spec = SetSpec.model_validate(raw)
    except Exception as e:
        raise ValueError(f"SetSpec validation failed: {e}\nRaw: {json.dumps(raw, indent=2)[:2000]}")

    spec = _cap_spec_modules(spec, cap)
    spec = _fix_positions(spec)
    spec = orient_buildings_toward_floors(spec)
    out.mkdir(parents=True, exist_ok=True)

    (out / "set_spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    (out / "set.usda").write_text(spec_to_usda(spec.modules), encoding="utf-8")
    (out / "set.gltf").write_text(
        json.dumps(spec_to_gltf_dict(spec.modules), indent=2), encoding="utf-8"
    )

    return spec, out


def main() -> int:
    p = argparse.ArgumentParser(description="Pilot: set brief → SetSpec → USDA + glTF")
    p.add_argument("brief", type=Path, nargs="?", default=None, help="Text file with set brief")
    p.add_argument("--prompt", default=None, help='Inline brief. Example: --prompt "sci-fi corridor 12m"')
    p.add_argument("--out", type=Path, default=Path("out/pilot"), help="Output directory")
    p.add_argument("--backend", choices=("ollama", "claude", "mock"), default="mock")
    p.add_argument("--model", default=None, help="Model name (auto-detected from backend if omitted)")
    p.add_argument("--ollama-url", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    p.add_argument(
        "--max-modules",
        type=int,
        default=None,
        metavar="N",
        help="Cap modules array size (overrides MAX_MODULES env when set)",
    )
    args = p.parse_args()

    if args.prompt is not None and args.brief is not None:
        print("Use either a brief file or --prompt, not both.", file=sys.stderr)
        return 2
    if args.prompt is not None:
        brief_text = args.prompt
    elif args.brief is not None:
        brief_text = args.brief.read_text(encoding="utf-8")
    else:
        p.error("Provide my_brief.txt or --prompt \"...\"")

    model = args.model
    if model is None:
        if args.backend == "claude":
            model = os.environ.get("MODEL", CLAUDE_SONNET)
        else:
            model = os.environ.get("MODEL", "qwen2.5-coder:32b")

    try:
        spec, out = generate_set(
            brief_text,
            backend=args.backend,
            model=model,
            ollama_url=args.ollama_url,
            out_dir=args.out,
            max_modules=args.max_modules,
        )
    except (ValueError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Wrote {out / 'set_spec.json'}")
    print(f"Wrote {out / 'set.usda'}")
    print(f"Wrote {out / 'set.gltf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
