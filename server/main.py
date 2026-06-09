"""FastAPI server wrapping the setlab pipeline for the web UI."""

import asyncio
import hmac
import json as _json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "out"

import sys
sys.path.insert(0, str(ROOT))

from setlab.run import generate_set  # noqa: E402
from setlab.model_ids import CLAUDE_SONNET  # noqa: E402

app = FastAPI(title="SetLab API")

_cors_raw = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3100,http://127.0.0.1:3100",
)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Optional bearer-token auth -------------------------------------------------
# If SETLAB_API_TOKEN is set, every /api/* call (except static media + /health)
# must send `Authorization: Bearer <token>`. If unset, auth is disabled (local dev).
_AUTH_OPEN_PREFIXES = ("/health", "/api/outputs/", "/api/web-refs/")


@app.middleware("http")
async def _require_api_token(request: Request, call_next):
    token = os.environ.get("SETLAB_API_TOKEN", "").strip()
    if token and request.method != "OPTIONS":
        path = request.url.path
        if path.startswith("/api") and not any(path.startswith(p) for p in _AUTH_OPEN_PREFIXES):
            sent = request.headers.get("authorization", "")
            if not hmac.compare_digest(sent, f"Bearer {token}"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


class GenerateRequest(BaseModel):
    prompt: str
    backend: str = "mock"
    model: str = CLAUDE_SONNET
    max_modules: Optional[int] = Field(
        default=None,
        ge=1,
        le=256,
        description="Cap modules count; overrides MAX_MODULES env when set.",
    )


class EnhancePromptRequest(BaseModel):
    """Expand a short user idea into a detailed English scene brief (Claude)."""

    prompt: str
    model: str = CLAUDE_SONNET
    reference_image_paths: Optional[List[str]] = None


class SearchImagesRequest(BaseModel):
    """Search DuckDuckGo for images matching the given query or prompt."""

    prompt: str = ""
    query: str = ""
    max_images: int = Field(default=10, ge=1, le=30)


class DeployRequest(BaseModel):
    ue_project: Optional[str] = None
    """Same semantics as web viewer: mod_building only, then per-module Δ (degrees XYZ)."""
    building_glb_extra_deg: Optional[List[float]] = None
    per_module_glb_extra_deg: Optional[Dict[str, List[float]]] = None


class RefineRequest(BaseModel):
    run_id: str
    instruction: str
    backend: str = "claude"
    model: str = CLAUDE_SONNET


class RefineModuleRequest(BaseModel):
    """Apply a natural-language edit to one module only (by id)."""

    run_id: str
    module_id: str
    instruction: str
    backend: str = "claude"
    model: str = CLAUDE_SONNET


class SaveViewerEditsRequest(BaseModel):
    """Persist per-module GLB Δ (°) from the web viewer into set_spec.json."""

    per_module_glb_extra_deg: Dict[str, List[float]] = Field(default_factory=dict)


class CopyMeshGlbRequest(BaseModel):
    """Copy meshes/<from>.glb → meshes/<to>.glb (byte-identical reuse)."""

    from_module_id: str = Field(..., min_length=1)
    to_module_id: str = Field(..., min_length=1)


class MeshGenStartRequest(BaseModel):
    """Optional: regenerate Rodin text-to-3D only for these ids (overwrites meshes/<id>.glb)."""

    module_ids: Optional[List[str]] = Field(
        default=None,
        description="If set, only these modules are sent to Rodin; existing GLBs are replaced.",
    )


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    run_id = f"web_{uuid.uuid4().hex[:10]}"
    out_dir = OUT_ROOT / run_id

    try:
        spec, out = generate_set(
            req.prompt,
            backend=req.backend,
            model=req.model,
            ollama_url=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
            out_dir=out_dir,
            max_modules=req.max_modules,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "id": run_id,
        "spec": spec.model_dump(),
        "gltfUrl": f"/api/outputs/{run_id}/set.gltf",
        "usdaUrl": f"/api/outputs/{run_id}/set.usda",
        "specUrl": f"/api/outputs/{run_id}/set_spec.json",
    }


@app.post("/api/enhance-prompt")
def api_enhance_prompt(req: EnhancePromptRequest):
    """Stream the enhanced scene brief as SSE text/event-stream.

    If the prompt contains web search intent ("search the web for images", etc.),
    also searches DuckDuckGo for reference images and emits them as SSE events
    so the frontend can pass them to HD mesh generation.
    """
    if not req.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt is empty")

    from setlab import claude_client
    from setlab.web_image_search import has_search_intent, extract_search_query, search_and_download
    import json as _json_mod

    prompt = req.prompt.strip()

    def generate():
        reference_images: list = []

        if req.reference_image_paths is not None:
            # Explicit paths supplied by the client (post-selection); skip auto-search
            reference_images = [p for p in req.reference_image_paths if Path(p).is_file()]
        else:
            # Auto-detect search intent and fetch images first
            if has_search_intent(prompt):
                query = extract_search_query(prompt)
                yield f"event: search_start\ndata: {query}\n\n"
                try:
                    refs_dir = OUT_ROOT / "_web_refs" / re.sub(r"[^\w\s-]", "", query)[:60].strip()
                    paths = search_and_download(query, refs_dir, max_images=10)
                    reference_images = [str(p) for p in paths]
                    rel_paths = [str(p.relative_to(OUT_ROOT)) for p in paths]
                    yield f"event: search_done\ndata: {_json_mod.dumps({'query': query, 'images': rel_paths, 'refs_dir': str(refs_dir)})}\n\n"
                except Exception as e:
                    yield f"event: search_error\ndata: {str(e)}\n\n"

        try:
            for chunk in claude_client.enhance_prompt_stream(
                prompt,
                model=req.model,
                reference_images=reference_images or None,
            ):
                yield f"data: {_json_mod.dumps(chunk)}\n\n"
        except (ValueError, RuntimeError) as e:
            yield f"event: error\ndata: {_json_mod.dumps(str(e))}\n\n"

        yield "event: done\ndata: \n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/search-images")
def api_search_images(req: SearchImagesRequest):
    """Search DuckDuckGo and download images. Returns list of image URLs + server paths."""
    from setlab.web_image_search import has_search_intent, extract_search_query, extract_image_count, search_and_download

    source_text = req.prompt.strip() or req.query.strip()
    if req.query.strip():
        query = req.query.strip()
    elif req.prompt.strip() and has_search_intent(req.prompt.strip()):
        query = extract_search_query(req.prompt.strip())
    else:
        return {"detected": False, "query": "", "images": [], "refs_dir": ""}

    # Honor count specified in the prompt (e.g. "at least 10", "10장")
    extracted_count = extract_image_count(source_text)
    max_images = min(extracted_count or req.max_images, 30)

    slug = re.sub(r"[^\w\s-]", "", query)[:60].strip()
    refs_dir = OUT_ROOT / "_web_refs" / slug
    try:
        paths = search_and_download(query, refs_dir, max_images=max_images)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    images = [
        {
            "url": f"/api/web-refs/{p.relative_to(OUT_ROOT)}",
            "path": str(p),
        }
        for p in paths
    ]
    return {"detected": True, "query": query, "images": images, "refs_dir": str(refs_dir)}


@app.get("/api/web-refs/{filepath:path}")
def api_web_ref_image(filepath: str):
    """Serve downloaded web reference images."""
    base = OUT_ROOT.resolve()
    file_path = (OUT_ROOT / filepath).resolve()
    if not file_path.is_relative_to(base) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    ext = file_path.suffix.lower()
    media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
    return FileResponse(file_path, media_type=media)


@app.get("/api/outputs/{run_id}/{filename:path}")
def api_output_file(run_id: str, filename: str):
    base = OUT_ROOT.resolve()
    file_path = (OUT_ROOT / run_id / filename).resolve()
    if not file_path.is_relative_to(base) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_types = {".gltf": "model/gltf+json", ".glb": "model/gltf-binary", ".json": "application/json"}
    ext = Path(filename).suffix
    media = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media)


@app.post("/api/refine")
def api_refine(req: RefineRequest):
    src_dir = OUT_ROOT / req.run_id
    spec_file = src_dir / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for run {req.run_id}")

    existing_spec = _json.loads(spec_file.read_text())

    try:
        if req.backend == "claude":
            from setlab import claude_client
            raw = claude_client.refine_raw(
                existing_spec, req.instruction, model=req.model
            )
        else:
            raise HTTPException(status_code=400, detail="Refine only supported with claude backend")
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    from setlab.models import SetSpec
    from setlab.run import _fix_positions
    from setlab.export_gltf import spec_to_gltf_dict
    from setlab.export_usda import spec_to_usda

    try:
        # Merge over the existing spec so untouched top-level fields
        # (ground_material, environment) are preserved; LLM-returned keys win.
        spec = SetSpec.model_validate({**existing_spec, **raw})
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation failed: {e}")

    spec = _fix_positions(spec)

    old_extra = existing_spec.get("per_module_glb_extra_deg")
    if isinstance(old_extra, dict):
        new_ids = {m.id for m in spec.modules}
        preserved: Dict[str, Tuple[float, float, float]] = {}
        for k, v in old_extra.items():
            if k not in new_ids:
                continue
            if isinstance(v, (list, tuple)) and len(v) == 3:
                try:
                    preserved[str(k)] = (float(v[0]), float(v[1]), float(v[2]))
                except (TypeError, ValueError):
                    continue
        if preserved:
            spec = spec.model_copy(update={"per_module_glb_extra_deg": preserved})

    run_id = f"web_{uuid.uuid4().hex[:10]}"
    out_dir = OUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "set_spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "set.usda").write_text(spec_to_usda(spec.modules), encoding="utf-8")
    (out_dir / "set.gltf").write_text(
        _json.dumps(spec_to_gltf_dict(spec.modules), indent=2), encoding="utf-8"
    )

    old_meshes = src_dir / "meshes"
    if old_meshes.is_dir():
        new_meshes = out_dir / "meshes"
        new_meshes.mkdir(parents=True, exist_ok=True)
        new_module_ids = {m.id for m in spec.modules}
        for glb in old_meshes.glob("*.glb"):
            if glb.stem in new_module_ids:
                shutil.copy2(glb, new_meshes / glb.name)

    old_images = src_dir / "images"
    if old_images.is_dir():
        new_images = out_dir / "images"
        new_module_ids = {m.id for m in spec.modules}
        for img_dir in old_images.iterdir():
            if img_dir.is_dir() and img_dir.name in new_module_ids:
                shutil.copytree(img_dir, new_images / img_dir.name, dirs_exist_ok=True)

    return {
        "id": run_id,
        "spec": spec.model_dump(),
        "gltfUrl": f"/api/outputs/{run_id}/set.gltf",
        "usdaUrl": f"/api/outputs/{run_id}/set.usda",
        "specUrl": f"/api/outputs/{run_id}/set_spec.json",
    }


def _tripo_prompt_fields_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """If true, skip copying GLB / HD images so meshgen can regenerate."""
    return old.get("description") != new.get("description") or old.get("asset") != new.get(
        "asset"
    )


@app.post("/api/refine-module")
def api_refine_module(req: RefineModuleRequest):
    """Refine a single module by id; other modules and spec metadata stay unchanged."""
    src_dir = OUT_ROOT / req.run_id
    spec_file = src_dir / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for run {req.run_id}")

    existing_spec = _json.loads(spec_file.read_text())
    modules_list: List[Dict[str, Any]] = list(existing_spec.get("modules", []))
    idx = next(
        (i for i, m in enumerate(modules_list) if m.get("id") == req.module_id),
        None,
    )
    if idx is None:
        raise HTTPException(
            status_code=404, detail=f"No module with id {req.module_id!r}"
        )

    old_module = dict(modules_list[idx])

    try:
        if req.backend == "claude":
            from setlab import claude_client

            reference_modules = [
                m for m in modules_list if m.get("id") != req.module_id
            ]
            updated = claude_client.refine_single_module_raw(
                old_module,
                title=str(existing_spec.get("title", "")),
                era_style=str(existing_spec.get("era_style", "")),
                instruction=req.instruction,
                reference_modules=reference_modules,
                model=req.model,
            )
        else:
            raise HTTPException(
                status_code=400, detail="refine-module only supported with claude backend"
            )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    from setlab.models import SetSpec
    from setlab.run import _fix_positions
    from setlab.export_gltf import spec_to_gltf_dict
    from setlab.export_usda import spec_to_usda

    modules_list[idx] = updated
    merged_spec_dict = {**existing_spec, "modules": modules_list}

    try:
        spec = SetSpec.model_validate(merged_spec_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation failed: {e}")

    spec = _fix_positions(spec)

    old_extra = existing_spec.get("per_module_glb_extra_deg")
    if isinstance(old_extra, dict):
        new_ids = {m.id for m in spec.modules}
        preserved: Dict[str, Tuple[float, float, float]] = {}
        for k, v in old_extra.items():
            if k not in new_ids:
                continue
            if isinstance(v, (list, tuple)) and len(v) == 3:
                try:
                    preserved[str(k)] = (float(v[0]), float(v[1]), float(v[2]))
                except (TypeError, ValueError):
                    continue
        if preserved:
            spec = spec.model_copy(update={"per_module_glb_extra_deg": preserved})

    run_id = f"web_{uuid.uuid4().hex[:10]}"
    out_dir = OUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "set_spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "set.usda").write_text(spec_to_usda(spec.modules), encoding="utf-8")
    (out_dir / "set.gltf").write_text(
        _json.dumps(spec_to_gltf_dict(spec.modules), indent=2), encoding="utf-8"
    )

    skip_mesh_for_id: Optional[str] = None
    if _tripo_prompt_fields_changed(old_module, updated):
        skip_mesh_for_id = req.module_id

    old_meshes = src_dir / "meshes"
    if old_meshes.is_dir():
        new_meshes = out_dir / "meshes"
        new_meshes.mkdir(parents=True, exist_ok=True)
        new_module_ids = {m.id for m in spec.modules}
        for glb in old_meshes.glob("*.glb"):
            if glb.stem not in new_module_ids:
                continue
            if skip_mesh_for_id and glb.stem == skip_mesh_for_id:
                continue
            shutil.copy2(glb, new_meshes / glb.name)

    old_images = src_dir / "images"
    if old_images.is_dir():
        new_images = out_dir / "images"
        new_module_ids = {m.id for m in spec.modules}
        for img_dir in old_images.iterdir():
            if not img_dir.is_dir() or img_dir.name not in new_module_ids:
                continue
            if skip_mesh_for_id and img_dir.name == skip_mesh_for_id:
                continue
            shutil.copytree(img_dir, new_images / img_dir.name, dirs_exist_ok=True)

    return {
        "id": run_id,
        "spec": spec.model_dump(),
        "gltfUrl": f"/api/outputs/{run_id}/set.gltf",
        "usdaUrl": f"/api/outputs/{run_id}/set.usda",
        "specUrl": f"/api/outputs/{run_id}/set_spec.json",
        "refined_module_id": req.module_id,
        "mesh_regen_suggested": skip_mesh_for_id is not None,
    }


@app.post("/api/save-edits/{run_id}")
def api_save_viewer_edits(run_id: str, req: SaveViewerEditsRequest):
    """Write viewer per-module GLB rotation deltas into out/<run_id>/set_spec.json."""
    from setlab.models import SetSpec

    out_dir = OUT_ROOT / run_id
    spec_file = out_dir / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    spec = SetSpec.model_validate(
        _json.loads(spec_file.read_text(encoding="utf-8"))
    )
    incoming = _per_module_vec3_map(req.per_module_glb_extra_deg)
    valid_ids = {m.id for m in spec.modules}
    clean: Dict[str, Tuple[float, float, float]] = {}
    for mid, tri in incoming.items():
        if mid not in valid_ids:
            continue
        if tri == (0.0, 0.0, 0.0):
            continue
        clean[mid] = tri

    spec = spec.model_copy(update={"per_module_glb_extra_deg": clean})
    spec_file.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return {"saved": True, "run_id": run_id, "modules_with_delta": len(clean)}


@app.post("/api/copy-mesh-glb/{run_id}")
def api_copy_mesh_glb(run_id: str, req: CopyMeshGlbRequest):
    """Copy one generated GLB onto another module id (identical geometry/texture on disk)."""
    from setlab.models import SetSpec

    if req.from_module_id == req.to_module_id:
        raise HTTPException(status_code=400, detail="from_module_id and to_module_id must differ")

    out_dir = OUT_ROOT / run_id
    spec_file = out_dir / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    spec = SetSpec.model_validate(_json.loads(spec_file.read_text(encoding="utf-8")))
    valid = {m.id for m in spec.modules}
    if req.from_module_id not in valid or req.to_module_id not in valid:
        raise HTTPException(
            status_code=400,
            detail="Both module ids must exist in set_spec.json modules",
        )

    meshes = out_dir / "meshes"
    src = meshes / f"{req.from_module_id}.glb"
    if not src.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No GLB at meshes/{req.from_module_id}.glb",
        )

    meshes.mkdir(parents=True, exist_ok=True)
    dst = meshes / f"{req.to_module_id}.glb"
    shutil.copy2(src, dst)

    return {
        "ok": True,
        "run_id": run_id,
        "from_module_id": req.from_module_id,
        "to_module_id": req.to_module_id,
    }


@app.post("/api/orient-buildings/{run_id}")
def api_orient_buildings(run_id: str):
    """Recompute mod_building rotation_deg toward nearest mod_floor; same run_id (meshes unchanged)."""
    from setlab.models import SetSpec
    from setlab.export_gltf import spec_to_gltf_dict
    from setlab.export_usda import spec_to_usda
    from setlab.layout_orient import orient_buildings_toward_floors

    out_dir = OUT_ROOT / run_id
    spec_file = out_dir / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    spec = SetSpec.model_validate(_json.loads(spec_file.read_text(encoding="utf-8")))
    spec = orient_buildings_toward_floors(spec)

    (out_dir / "set_spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "set.usda").write_text(spec_to_usda(spec.modules), encoding="utf-8")
    (out_dir / "set.gltf").write_text(
        _json.dumps(spec_to_gltf_dict(spec.modules), indent=2), encoding="utf-8"
    )

    return {
        "id": run_id,
        "spec": spec.model_dump(),
        "gltfUrl": f"/api/outputs/{run_id}/set.gltf",
        "usdaUrl": f"/api/outputs/{run_id}/set.usda",
        "specUrl": f"/api/outputs/{run_id}/set_spec.json",
    }


def _vec3_from_list(v: Optional[List[float]]) -> Tuple[float, float, float]:
    if not v or len(v) != 3:
        return (0.0, 0.0, 0.0)
    return (float(v[0]), float(v[1]), float(v[2]))


def _per_module_vec3_map(raw: Optional[Dict[str, List[float]]]) -> Dict[str, Tuple[float, float, float]]:
    if not raw:
        return {}
    out: Dict[str, Tuple[float, float, float]] = {}
    for k, lst in raw.items():
        if lst is not None and len(lst) == 3:
            out[k] = (float(lst[0]), float(lst[1]), float(lst[2]))
    return out


@app.post("/api/deploy/{run_id}")
def api_deploy(run_id: str, vr: bool = False, req: Optional[DeployRequest] = None):
    from setlab.export_gltf import spec_to_gltf_dict
    from setlab.glb_rotation_bake import bake_spec_modules_for_deploy
    from setlab.models import SetSpec

    src_dir = OUT_ROOT / run_id
    gltf = src_dir / "set.gltf"
    if not gltf.exists():
        raise HTTPException(status_code=404, detail=f"No output for {run_id}")

    ue_project = (req and req.ue_project) or os.environ.get("UE_PROJECT")
    if not ue_project:
        raise HTTPException(status_code=400, detail="UE_PROJECT not configured")
    if not Path(ue_project).is_dir() or not any(Path(ue_project).glob("*.uproject")):
        raise HTTPException(
            status_code=400,
            detail="ue_project is not a valid Unreal project directory (no .uproject)",
        )

    dest = Path(ue_project) / "Content" / "Incoming"
    dest.mkdir(parents=True, exist_ok=True)

    spec_src = src_dir / "set_spec.json"
    spec_dest = Path(ue_project) / "Saved" / "SetLab"
    spec_dest.mkdir(parents=True, exist_ok=True)

    if spec_src.exists():
        spec_obj: Dict[str, Any] = _json.loads(spec_src.read_text(encoding="utf-8"))
        building_extra = _vec3_from_list(req.building_glb_extra_deg if req else None)
        per_map = _per_module_vec3_map(req.per_module_glb_extra_deg if req else None)
        baked_modules = bake_spec_modules_for_deploy(
            spec_obj.get("modules", []), building_extra, per_map
        )
        spec_out = {**spec_obj, "modules": baked_modules}
        (spec_dest / "set_spec.json").write_text(
            _json.dumps(spec_out, indent=2), encoding="utf-8"
        )
        spec_model = SetSpec.model_validate(spec_out)
        gltf_dict = spec_to_gltf_dict(spec_model.modules)
        (dest / "set.gltf").write_text(
            _json.dumps(gltf_dict, indent=2), encoding="utf-8"
        )
    else:
        shutil.copy2(gltf, dest / "set.gltf")

    meshes_copied = 0
    meshes_src = src_dir / "meshes"
    if meshes_src.is_dir():
        meshes_dest = dest / "SetLab" / "meshes"
        meshes_dest.mkdir(parents=True, exist_ok=True)
        for glb in sorted(meshes_src.glob("*.glb")):
            shutil.copy2(glb, meshes_dest / glb.name)
            meshes_copied += 1

    env_src = src_dir / "environment"
    env_copied = 0
    if env_src.is_dir():
        env_dest = dest / "SetLab" / "environment"
        env_dest.mkdir(parents=True, exist_ok=True)
        for f in env_src.iterdir():
            if f.is_file():
                shutil.copy2(f, env_dest / f.name)
                env_copied += 1

    vr_flag = spec_dest / "vr_mode.flag"
    if vr:
        vr_flag.write_text("true", encoding="utf-8")
    elif vr_flag.exists():
        vr_flag.unlink()

    return {
        "deployed": True,
        "destination": str(dest),
        "vr": vr,
        "meshes_copied": meshes_copied,
    }


@app.get("/api/history")
def api_history():
    items = []
    if not OUT_ROOT.exists():
        return {"items": items}

    for d in sorted(OUT_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or not d.name.startswith("web_"):
            continue
        spec_file = d / "set_spec.json"
        if not spec_file.exists():
            continue
        try:
            spec = _json.loads(spec_file.read_text())
        except Exception:
            continue
        items.append({
            "id": d.name,
            "title": spec.get("title", d.name),
            "era_style": spec.get("era_style", ""),
            "moduleCount": len(spec.get("modules", [])),
            "gltfUrl": f"/api/outputs/{d.name}/set.gltf",
        })

    return {"items": items}


@app.get("/api/config")
def api_config():
    return {
        "ue_project": os.environ.get("UE_PROJECT", ""),
        "ollama_host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "default_model": os.environ.get("MODEL", CLAUDE_SONNET),
        "default_backend": os.environ.get("BACKEND", "claude"),
    }


class ConfigUpdate(BaseModel):
    ue_project: Optional[str] = None


@app.post("/api/config")
def api_config_update(req: ConfigUpdate):
    if req.ue_project is not None:
        path = Path(req.ue_project)
        if not path.is_dir() or not any(path.glob("*.uproject")):
            raise HTTPException(
                status_code=400,
                detail=f"Not a valid Unreal project directory (no .uproject): {req.ue_project}",
            )

        env_file = ROOT / ".env"
        try:
            lines = env_file.read_text().splitlines() if env_file.exists() else []
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith("UE_PROJECT=") or line.strip().startswith("# UE_PROJECT="):
                    lines[i] = f'UE_PROJECT="{req.ue_project}"'
                    updated = True
                    break
            if not updated:
                lines.append(f'UE_PROJECT="{req.ue_project}"')
            env_file.write_text("\n".join(lines) + "\n")
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to persist .env: {e}")
        os.environ["UE_PROJECT"] = req.ue_project

    return {"ue_project": os.environ.get("UE_PROJECT", "")}


# ---------------------------------------------------------------------------
# Mesh generation (Hyper3D Rodin Gen-2)
# ---------------------------------------------------------------------------

# One lock guards all background-job dicts so the "already running? -> reuse : start"
# check-then-store is atomic; two concurrent requests can no longer spawn duplicate
# pipelines writing the same files for one run_id.
_jobs_lock = threading.Lock()

_meshgen_jobs: Dict[str, dict] = {}


def _disk_glb_module_ids(out_dir: Path) -> set:
    d = out_dir / "meshes"
    if not d.is_dir():
        return set()
    return {p.stem for p in d.glob("*.glb")}


def _derive_mesh_terminal_status(merged: Dict[str, Any], module_ids: list) -> str:
    """Overall meshgen status from per-module done / failed / pending (truthy for UI)."""
    if not module_ids:
        return "completed"
    states = [merged.get(mid, "pending") for mid in module_ids]
    if any(s == "pending" for s in states):
        return "partial"
    if all(s == "failed" for s in states):
        return "failed"
    if any(s == "failed" for s in states):
        return "partial"
    return "completed"


def _merge_mesh_status(run_id: str, job: Optional[dict]) -> dict:
    """Merge on-disk GLBs into status so the UI always sees files saved under meshes/."""
    out_dir = OUT_ROOT / run_id
    spec_file = out_dir / "set_spec.json"
    module_ids: list = []
    if spec_file.exists():
        spec = _json.loads(spec_file.read_text())
        module_ids = [m["id"] for m in spec.get("modules", [])]
    total = len(module_ids)
    disk_done = _disk_glb_module_ids(out_dir)

    if job:
        merged = dict(job["modules"])
        for mid in disk_done:
            merged[mid] = "done"
        done_count = sum(1 for s in merged.values() if s in ("done", "failed"))
        js = job["status"]
        if js == "running":
            out_status: str = "running"
        elif js == "failed" and job.get("error"):
            out_status = "failed"
        else:
            # Thread used to mark "completed" even when some modules failed — recompute.
            out_status = _derive_mesh_terminal_status(merged, module_ids)
        out = {
            "status": out_status,
            "total": total or job.get("total", len(merged)),
            "done": done_count,
            "modules": merged,
            "disk_glb_count": len(disk_done),
        }
        if job.get("error"):
            out["error"] = job["error"]
        return out

    if not disk_done:
        raise HTTPException(
            status_code=404, detail=f"No meshgen job for {run_id}"
        )

    if not module_ids:
        merged = {mid: "done" for mid in sorted(disk_done)}
        n = len(merged)
        return {
            "status": "completed",
            "total": n,
            "done": n,
            "modules": merged,
            "disk_glb_count": len(disk_done),
        }

    merged = {mid: "pending" for mid in module_ids}
    for mid in disk_done:
        merged[mid] = "done"
    done_count = sum(1 for s in merged.values() if s in ("done", "failed"))
    has_missing = done_count < total
    return {
        "status": "completed" if not has_missing else "partial",
        "total": total,
        "done": done_count,
        "modules": merged,
        "disk_glb_count": len(disk_done),
    }


def _run_meshgen_thread(run_id: str, modules: list, out_dir: Path):
    """Background thread: runs the async Rodin Gen-2 pipeline."""
    job = _meshgen_jobs[run_id]

    def on_progress(module_id: str, status: str, _progress: int):
        job["modules"][module_id] = status
        job["done"] = sum(1 for s in job["modules"].values() if s in ("done", "failed"))

    loop = asyncio.new_event_loop()
    try:
        from setlab.rodin_client import generate_meshes
        loop.run_until_complete(generate_meshes(modules, out_dir, on_progress=on_progress))
        job["done"] = sum(
            1 for s in job["modules"].values() if s in ("done", "failed")
        )
        mids = list(job["modules"].keys())
        job["status"] = _derive_mesh_terminal_status(job["modules"], mids)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        loop.close()


@app.post("/api/meshgen/{run_id}")
def api_meshgen_start(
    run_id: str,
    req: MeshGenStartRequest = Body(default_factory=MeshGenStartRequest),
):
    spec_file = OUT_ROOT / run_id / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    if run_id in _meshgen_jobs and _meshgen_jobs[run_id]["status"] == "running":
        return _meshgen_jobs[run_id]

    spec = _json.loads(spec_file.read_text())
    modules = spec.get("modules", [])
    mid_order = [m["id"] for m in modules]
    ids_in_spec = set(mid_order)

    already_done = _disk_glb_module_ids(OUT_ROOT / run_id)

    if req.module_ids is not None:
        if not req.module_ids:
            raise HTTPException(
                status_code=422,
                detail="module_ids, if provided, must be a non-empty list",
            )
        requested = list(dict.fromkeys(req.module_ids))
        unknown = [x for x in requested if x not in ids_in_spec]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown module_ids (not in set_spec): {unknown}",
            )
        requested_set = set(requested)
        modules_to_gen = [m for m in modules if m["id"] in requested_set]
        mod_status = {}
        for m in modules:
            mid = m["id"]
            if mid in requested_set:
                mod_status[mid] = "pending"
            else:
                mod_status[mid] = "done" if mid in already_done else "pending"
        done_for_job = sum(1 for s in mod_status.values() if s in ("done", "failed"))
    else:
        modules_to_gen = [m for m in modules if m["id"] not in already_done]
        mod_status = {}
        for m in modules:
            mod_status[m["id"]] = "done" if m["id"] in already_done else "pending"
        done_for_job = len(already_done)

    if not modules_to_gen:
        return {
            "status": _derive_mesh_terminal_status(mod_status, mid_order),
            "total": len(modules),
            "done": sum(1 for s in mod_status.values() if s in ("done", "failed")),
            "modules": mod_status,
        }

    job: dict = {
        "status": "running",
        "total": len(modules),
        "done": done_for_job,
        "modules": mod_status,
    }
    with _jobs_lock:
        existing = _meshgen_jobs.get(run_id)
        if existing and existing.get("status") == "running":
            return existing
        _meshgen_jobs[run_id] = job

    t = threading.Thread(
        target=_run_meshgen_thread,
        args=(run_id, modules_to_gen, OUT_ROOT / run_id),
        daemon=True,
    )
    t.start()
    return job


@app.get("/api/meshgen/{run_id}/status")
def api_meshgen_status(run_id: str):
    if not (OUT_ROOT / run_id / "set_spec.json").exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")
    job = _meshgen_jobs.get(run_id)
    if not job and not _disk_glb_module_ids(OUT_ROOT / run_id):
        raise HTTPException(status_code=404, detail=f"No meshgen job for {run_id}")
    return _merge_mesh_status(run_id, job)


# ---------------------------------------------------------------------------
# HD mesh generation (image_gen: FLUX or Google → Rodin Gen-2 concat → GLB)
# ---------------------------------------------------------------------------

_hdgen_jobs: Dict[str, dict] = {}


def _hd_job_refresh_done(job: dict) -> None:
    """Keep HD progress bar meaningful across image (img_*) and Rodin (uploading, …) phases."""
    phase = job.get("phase", "starting")
    vals = list(job["modules"].values())
    if phase in ("starting", "images"):
        # First touch on a module → at least 1/9; each module finishes images before the next starts.
        job["done"] = sum(1 for s in vals if s != "pending")
    else:
        # 3D phase: Rodin in-flight counts; ignore leftover img_* labels until overwritten.
        job["done"] = sum(
            1
            for s in vals
            if s in ("done", "failed", "uploading", "generating_3d")
        )


def _run_hdgen_thread(run_id: str, modules: list, out_dir: Path):
    """Background thread: generate reference images (IMAGE_GEN_BACKEND) then Rodin GLBs."""
    job = _hdgen_jobs[run_id]

    def on_img_progress(module_id: str, status: str, pct: int):
        job["modules"][module_id] = f"img_{status}"
        _hd_job_refresh_done(job)

    def on_3d_progress(module_id: str, status: str, pct: int):
        job["modules"][module_id] = status
        _hd_job_refresh_done(job)

    try:
        job["phase"] = "images"
        from setlab.image_gen import generate_all_module_images
        # Use web reference images if they exist (downloaded via enhance + web search)
        web_refs = next(iter(sorted((OUT_ROOT / "_web_refs").glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)), None) if (OUT_ROOT / "_web_refs").exists() else None
        img_results = generate_all_module_images(modules, out_dir, on_progress=on_img_progress, web_refs_dir=web_refs)
        if isinstance(img_results, dict) and not any(img_results.values()):
            raise RuntimeError(
                "참조 이미지 생성 결과가 비어 있습니다 (모든 모듈 0뷰). FLUX/이미지 백엔드 키·설정을 확인하세요."
            )

        job["phase"] = "3d"
        loop = asyncio.new_event_loop()
        try:
            from setlab.rodin_client import generate_hd_meshes
            mesh_results = loop.run_until_complete(generate_hd_meshes(modules, out_dir, on_progress=on_3d_progress))
        finally:
            loop.close()
        if isinstance(mesh_results, dict) and not any(mesh_results.values()):
            raise RuntimeError("HD 메시 생성 결과가 비어 있습니다 (모든 모듈 실패).")

        job["status"] = "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)


@app.post("/api/hdgen/{run_id}")
def api_hdgen_start(run_id: str):
    spec_file = OUT_ROOT / run_id / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    if run_id in _hdgen_jobs and _hdgen_jobs[run_id]["status"] == "running":
        return _hdgen_jobs[run_id]

    spec = _json.loads(spec_file.read_text())
    modules = spec.get("modules", [])
    hd_modules = [m for m in modules if m.get("asset") != "mod_floor"]
    if not hd_modules:
        hd_modules = modules

    job: dict = {
        "status": "running",
        "phase": "starting",
        "total": len(hd_modules),
        "done": 0,
        "modules": {m["id"]: "pending" for m in hd_modules},
    }
    with _jobs_lock:
        existing = _hdgen_jobs.get(run_id)
        if existing and existing.get("status") == "running":
            return existing
        _hdgen_jobs[run_id] = job

    t = threading.Thread(
        target=_run_hdgen_thread,
        args=(run_id, hd_modules, OUT_ROOT / run_id),
        daemon=True,
    )
    t.start()
    return job


@app.get("/api/hdgen/{run_id}/status")
def api_hdgen_status(run_id: str):
    if not (OUT_ROOT / run_id / "set_spec.json").exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    job = _hdgen_jobs.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No hdgen job for {run_id}")
    return job


# ---------------------------------------------------------------------------
# Environment generation (World Labs Marble)
# ---------------------------------------------------------------------------

_envgen_jobs: Dict[str, dict] = {}


def _run_envgen_thread(run_id: str, prompt: str, out_dir: Path):
    """Background thread: generate full 3D environment via Marble."""
    job = _envgen_jobs[run_id]

    def on_progress(status: str, pct: int):
        job["phase"] = status
        job["progress"] = pct

    loop = asyncio.new_event_loop()
    try:
        from setlab.marble_client import generate_environment

        result = loop.run_until_complete(
            generate_environment(prompt, out_dir, on_progress=on_progress)
        )
        job["status"] = "completed"
        job["result"] = result
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        loop.close()


@app.post("/api/envgen/{run_id}")
def api_envgen_start(run_id: str):
    """Start Marble environment generation for a run's scene description."""
    spec_file = OUT_ROOT / run_id / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    if run_id in _envgen_jobs and _envgen_jobs[run_id]["status"] == "running":
        return _envgen_jobs[run_id]

    spec = _json.loads(spec_file.read_text())
    title = spec.get("title", "")
    era_style = spec.get("era_style", "")
    modules = spec.get("modules", [])
    descriptions = [m.get("description", "") for m in modules if m.get("description")]

    env_prompt = (
        f"{title}. {era_style}. "
        + " ".join(descriptions[:5])
    )

    job: dict = {
        "status": "running",
        "phase": "submitting",
        "progress": 0,
    }
    with _jobs_lock:
        existing = _envgen_jobs.get(run_id)
        if existing and existing.get("status") == "running":
            return existing
        _envgen_jobs[run_id] = job

    t = threading.Thread(
        target=_run_envgen_thread,
        args=(run_id, env_prompt, OUT_ROOT / run_id),
        daemon=True,
    )
    t.start()
    return job


@app.get("/api/envgen/{run_id}/status")
def api_envgen_status(run_id: str):
    if not (OUT_ROOT / run_id / "set_spec.json").exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    job = _envgen_jobs.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No envgen job for {run_id}")
    return job


# ---------------------------------------------------------------------------
# Material enhancement (3D AI Studio texture-edit)
# ---------------------------------------------------------------------------

class MaterialEnhanceRequest(BaseModel):
    style: str = "generic_weathered"
    custom_prompt: Optional[str] = None

_matenhance_jobs: Dict[str, dict] = {}


def _run_matenhance_thread(
    run_id: str, modules: list, out_dir: Path,
    style: str, custom_prompt: Optional[str],
):
    """Background thread: re-texture meshes with weathering via texture-edit API."""
    job = _matenhance_jobs[run_id]

    def on_progress(module_id: str, status: str, pct: int):
        job["modules"][module_id] = status
        job["done"] = sum(
            1 for s in job["modules"].values() if s in ("done", "failed")
        )

    loop = asyncio.new_event_loop()
    try:
        from setlab.material_enhance import enhance_materials

        loop.run_until_complete(
            enhance_materials(
                modules, out_dir,
                style=style,
                custom_prompt=custom_prompt,
                on_progress=on_progress,
            )
        )
        job["done"] = sum(
            1 for s in job["modules"].values() if s in ("done", "failed")
        )
        all_failed = all(s == "failed" for s in job["modules"].values())
        job["status"] = "failed" if all_failed else "completed"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        loop.close()


@app.post("/api/material-enhance/{run_id}")
def api_material_enhance_start(
    run_id: str,
    req: MaterialEnhanceRequest = Body(default_factory=MaterialEnhanceRequest),
):
    spec_file = OUT_ROOT / run_id / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    if run_id in _matenhance_jobs and _matenhance_jobs[run_id]["status"] == "running":
        return _matenhance_jobs[run_id]

    spec = _json.loads(spec_file.read_text())
    modules = spec.get("modules", [])

    job: dict = {
        "status": "running",
        "total": len(modules),
        "done": 0,
        "modules": {m["id"]: "pending" for m in modules},
    }
    with _jobs_lock:
        existing = _matenhance_jobs.get(run_id)
        if existing and existing.get("status") == "running":
            return existing
        _matenhance_jobs[run_id] = job

    t = threading.Thread(
        target=_run_matenhance_thread,
        args=(run_id, modules, OUT_ROOT / run_id, req.style, req.custom_prompt),
        daemon=True,
    )
    t.start()
    return job


@app.get("/api/material-enhance/{run_id}/status")
def api_material_enhance_status(run_id: str):
    if not (OUT_ROOT / run_id / "set_spec.json").exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    job = _matenhance_jobs.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No material-enhance job for {run_id}")
    return job


# ---------------------------------------------------------------------------
# Real-time modification (Claude tier classification → dispatch)
# ---------------------------------------------------------------------------

class ModifyRequest(BaseModel):
    instruction: str
    model: str = CLAUDE_SONNET


@app.post("/api/modify/{run_id}")
def api_modify(run_id: str, req: ModifyRequest):
    """Classify a director's modification and dispatch to the appropriate tier."""
    spec_file = OUT_ROOT / run_id / "set_spec.json"
    if not spec_file.exists():
        raise HTTPException(status_code=404, detail=f"No spec for {run_id}")

    spec = _json.loads(spec_file.read_text())

    try:
        from setlab.modify_client import classify
        result = classify(spec, req.instruction, model=req.model)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    tier = result.get("tier", "moderate")
    commands = result.get("commands", {})

    if tier == "instant":
        env_update = commands.get("environment", {})
        if env_update:
            current_env = spec.get("environment") or {}
            current_env.update(env_update)
            spec["environment"] = current_env
            spec_file.write_text(_json.dumps(spec, indent=2, ensure_ascii=False))

        ue_project = os.environ.get("UE_PROJECT")
        if ue_project:
            cmd_dir = Path(ue_project) / "Saved" / "SetLab"
            cmd_dir.mkdir(parents=True, exist_ok=True)
            cmd_file = cmd_dir / "modify_commands.json"
            cmd_file.write_text(_json.dumps({
                "tier": tier,
                "commands": commands,
            }, indent=2, ensure_ascii=False))

    elif tier == "fast":
        retexture = commands.get("retexture", {})
        if retexture:
            ue_project = os.environ.get("UE_PROJECT")
            if ue_project:
                cmd_dir = Path(ue_project) / "Saved" / "SetLab"
                cmd_dir.mkdir(parents=True, exist_ok=True)
                cmd_file = cmd_dir / "modify_commands.json"
                cmd_file.write_text(_json.dumps({
                    "tier": tier,
                    "commands": commands,
                    "module_ids": result.get("module_ids", []),
                }, indent=2, ensure_ascii=False))

            module_ids = list(retexture.keys())
            modules_to_enhance = [
                m for m in spec.get("modules", []) if m["id"] in module_ids
            ]
            if modules_to_enhance:
                first_prompt = next(iter(retexture.values()), None)
                spawn = False
                with _jobs_lock:
                    existing = _matenhance_jobs.get(run_id)
                    if not (existing and existing.get("status") == "running"):
                        _matenhance_jobs[run_id] = {
                            "status": "running",
                            "total": len(modules_to_enhance),
                            "done": 0,
                            "modules": {m["id"]: "pending" for m in modules_to_enhance},
                        }
                        spawn = True
                if spawn:
                    t = threading.Thread(
                        target=_run_matenhance_thread,
                        args=(run_id, modules_to_enhance, OUT_ROOT / run_id, "generic_weathered", first_prompt),
                        daemon=True,
                    )
                    t.start()

    elif tier == "moderate":
        regenerate = commands.get("regenerate", {})
        if regenerate:
            modules = spec.get("modules", [])
            for mid, updates in regenerate.items():
                for m in modules:
                    if m["id"] == mid:
                        if "description" in updates:
                            m["description"] = updates["description"]
                        if "scale" in updates:
                            m["scale"] = updates["scale"]
                        break
            spec["modules"] = modules
            spec_file.write_text(_json.dumps(spec, indent=2, ensure_ascii=False))

            module_ids = list(regenerate.keys())
            if module_ids:
                modules_to_gen = [m for m in modules if m["id"] in module_ids]
                mod_status = {}
                for m in modules:
                    mod_status[m["id"]] = "pending" if m["id"] in module_ids else "done"
                spawn = False
                with _jobs_lock:
                    existing = _meshgen_jobs.get(run_id)
                    if not (existing and existing.get("status") == "running"):
                        _meshgen_jobs[run_id] = {
                            "status": "running",
                            "total": len(modules),
                            "done": sum(1 for s in mod_status.values() if s == "done"),
                            "modules": mod_status,
                        }
                        spawn = True
                if spawn:
                    t = threading.Thread(
                        target=_run_meshgen_thread,
                        args=(run_id, modules_to_gen, OUT_ROOT / run_id),
                        daemon=True,
                    )
                    t.start()

    return {
        "tier": tier,
        "summary": result.get("summary", ""),
        "module_ids": result.get("module_ids", []),
        "commands": commands,
    }


@app.get("/api/browse")
def api_browse(path: str = ""):
    target = Path(path).expanduser().resolve() if path else Path.home().resolve()
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    # Optional allowlist: if SETLAB_BROWSE_ROOTS is set (os.pathsep-separated),
    # restrict browsing to those roots. Unset = permissive (local dev default).
    roots_env = os.environ.get("SETLAB_BROWSE_ROOTS", "").strip()
    if roots_env:
        roots = [Path(r).expanduser().resolve() for r in roots_env.split(os.pathsep) if r.strip()]
        if not any(target == r or target.is_relative_to(r) for r in roots):
            raise HTTPException(status_code=403, detail="Path outside allowed browse roots")

    entries = []
    try:
        for child in sorted(target.iterdir()):
            if child.name.startswith("."):
                continue
            try:
                if not child.is_dir():
                    continue
            except (PermissionError, OSError):
                continue
            try:
                has_uproject = any(child.glob("*.uproject"))
            except (PermissionError, OSError):
                has_uproject = False
            entries.append({"name": child.name, "path": str(child), "is_project": has_uproject})
    except PermissionError:
        pass

    return {
        "current": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "entries": entries,
    }
