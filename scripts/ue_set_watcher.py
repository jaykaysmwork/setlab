# ─────────────────────────────────────────────────────────────────────────
# SetLab Unreal Watcher — 자동 임포트 + 자동 배치
# ─────────────────────────────────────────────────────────────────────────
# Unreal 에디터 Python 콘솔에서 실행:
#   exec(open('/path/to/ue_set_watcher.py').read())
# 중지:
#   stop()
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import math
import os
import struct
import time

import unreal

INCOMING_DIR = os.path.join(unreal.Paths.project_content_dir(), "Incoming")
WATCH_GLTF = os.path.join(INCOMING_DIR, "set.gltf")
WATCH_SPEC = os.path.join(unreal.Paths.project_saved_dir(), "SetLab", "set_spec.json")
VR_FLAG_PATH = os.path.join(unreal.Paths.project_saved_dir(), "SetLab", "vr_mode.flag")
HD_MESHES_FS = os.path.join(INCOMING_DIR, "SetLab", "meshes")
HD_MESHES_UE = "/Game/Incoming/SetLab/meshes"
ENV_MESH_FS = os.path.join(INCOMING_DIR, "SetLab", "environment")
ENV_MESH_UE = "/Game/Incoming/SetLab/environment"
DEST_PATH = "/Game/Incoming"
MEGASCANS_ROOT = "/Game/Megascans/Surfaces"
MODIFY_CMD_PATH = os.path.join(
    unreal.Paths.project_saved_dir(), "SetLab", "modify_commands.json"
)
POLL_SECONDS = 2.0
SET_TAG = "SETLAB_AUTO"
ENV_TAG = "SETLAB_ENV"
GROUND_TAG = "SETLAB_GROUND"
MODIFY_TAG = "SETLAB_MODIFY"

_last_mtime = 0.0
_last_check = 0.0
_last_modify_mtime = 0.0
_handle = None

# ── coordinate helpers ──────────────────────────────────────────────────

def _euler_xyz_to_quat(rx_deg, ry_deg, rz_deg):
    """XYZ intrinsic Euler (degrees) → quaternion (x, y, z, w). Same as setlab/glTF."""
    rx, ry, rz = math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
    cx, sx = math.cos(rx * 0.5), math.sin(rx * 0.5)
    cy, sy = math.cos(ry * 0.5), math.sin(ry * 0.5)
    cz, sz = math.cos(rz * 0.5), math.sin(rz * 0.5)
    return (
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
        cx * cy * cz + sx * sy * sz,
    )


def _setlab_rot_to_ue(rx, ry, rz):
    """setlab XYZ Euler (degrees) → unreal.Rotator via quaternion.

    Y↔Z swap + conjugate imaginary part for RH(glTF) → LH(UE) handedness.
    """
    qx, qy, qz, qw = _euler_xyz_to_quat(rx, ry, rz)
    ue_q = unreal.Quat(-qx, -qz, -qy, qw)
    return ue_q.rotator()


def _setlab_quat_to_ue(qx, qy, qz, qw):
    """glTF quaternion (x,y,z,w) → unreal.Rotator. Avoids Euler roundtrip."""
    ue_q = unreal.Quat(-qx, -qz, -qy, qw)
    return ue_q.rotator()


def _setlab_pos_to_ue(px, py, pz):
    """setlab meters → UE Vector (cm). Y↔Z swap: UE(X,Y,Z) = glTF(X,Z,Y) × 100."""
    return unreal.Vector(px * 100.0, pz * 100.0, py * 100.0)


# ── import helpers ──────────────────────────────────────────────────────

_GLB_MAGIC = 0x46546C67  # 'glTF'
_JSON_CHUNK_TYPE = 0x4E4F534A  # 'JSON'


def _patch_glb_materials(glb_path):
    """Rewrite metallicFactor→0 and doubleSided→true inside a GLB.

    Tripo exports every mesh with metallicFactor=1.0.  In UE, fully-metallic
    PBR surfaces have no diffuse component, so the baseColor texture is only
    visible through specular reflections — making everything appear nearly
    black.  Setting metallic to 0 restores normal diffuse shading.
    """
    with open(glb_path, "rb") as f:
        data = f.read()

    if len(data) < 20 or struct.unpack_from("<I", data, 0)[0] != _GLB_MAGIC:
        return False

    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + json_len])
    rest = data[20 + json_len :]

    changed = False
    for mat in gltf.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        if pbr.get("metallicFactor", 1.0) > 0.5:
            pbr["metallicFactor"] = 0.0
            changed = True
        if not mat.get("doubleSided", False):
            mat["doubleSided"] = True
            changed = True

    if not changed:
        return False

    new_json = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(new_json) % 4 != 0:
        new_json += b" "

    total = 12 + 8 + len(new_json) + len(rest)
    with open(glb_path, "wb") as f:
        f.write(struct.pack("<III", _GLB_MAGIC, 2, total))
        f.write(struct.pack("<II", len(new_json), _JSON_CHUNK_TYPE))
        f.write(new_json)
        f.write(rest)
    return True


def _import_gltf():
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", WATCH_GLTF)
    task.set_editor_property("destination_path", DEST_PATH)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    unreal.log("[SetLab] Imported set.gltf -> %s" % DEST_PATH)


def _import_hd_glb_folder():
    if not os.path.isdir(HD_MESHES_FS):
        return 0
    n = 0
    patched = 0
    for name in sorted(os.listdir(HD_MESHES_FS)):
        if not name.lower().endswith(".glb"):
            continue
        mid = os.path.splitext(name)[0]
        full = os.path.join(HD_MESHES_FS, name)

        if _patch_glb_materials(full):
            patched += 1
            old_dir = HD_MESHES_UE + "/" + mid
            if unreal.EditorAssetLibrary.does_directory_exist(old_dir):
                unreal.EditorAssetLibrary.delete_directory(old_dir)

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", full)
        task.set_editor_property("destination_path", HD_MESHES_UE)
        task.set_editor_property("destination_name", mid)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("automated", True)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        n += 1
    if patched:
        unreal.log("[SetLab] Patched %d GLBs (metallicFactor→0, doubleSided)" % patched)
    unreal.log("[SetLab] Imported %d HD .glb -> %s" % (n, HD_MESHES_UE))
    return n


def _find_static_mesh_for_module(module_id):
    """Resolve imported StaticMesh for a module id. UE GLB import creates sub-folders."""
    if not unreal.EditorAssetLibrary.does_directory_exist(HD_MESHES_UE):
        return None
    try:
        paths = unreal.EditorAssetLibrary.list_assets(HD_MESHES_UE, recursive=True, include_folder=False)
    except TypeError:
        paths = unreal.EditorAssetLibrary.list_assets(HD_MESHES_UE, recursive=True)
    if not paths:
        return None

    exact = None
    partial = None
    for ap in paths:
        try:
            a = unreal.load_asset(ap)
        except Exception:
            continue
        if a is None or not isinstance(a, unreal.StaticMesh):
            continue
        nm = str(a.get_name())
        if nm == module_id:
            exact = a
            break
        if module_id in ap.replace("\\", "/"):
            if partial is None:
                partial = a
    return exact or partial


def _get_mesh_bounds_cm(mesh):
    """Return (half_extent: Vector, center: Vector) in cm from the mesh asset."""
    try:
        bb = mesh.get_bounding_box()
        mn, mx = bb.min, bb.max
        hx = (mx.x - mn.x) * 0.5
        hy = (mx.y - mn.y) * 0.5
        hz = (mx.z - mn.z) * 0.5
        cx = (mn.x + mx.x) * 0.5
        cy = (mn.y + mx.y) * 0.5
        cz = (mn.z + mx.z) * 0.5
        return unreal.Vector(hx, hy, hz), unreal.Vector(cx, cy, cz)
    except Exception:
        pass
    try:
        eb = mesh.extended_bounds
        return eb.box_extent, eb.origin
    except Exception:
        pass
    return None, None


# ── environment (Marble) ─────────────────────────────────────────────────

def _import_marble_environment():
    """Import Marble environment GLB and place as large-scale backdrop."""
    if not os.path.isdir(ENV_MESH_FS):
        return False

    glb_path = os.path.join(ENV_MESH_FS, "collider_mesh.glb")
    if not os.path.isfile(glb_path):
        return False

    _patch_glb_materials(glb_path)

    if unreal.EditorAssetLibrary.does_directory_exist(ENV_MESH_UE):
        unreal.EditorAssetLibrary.delete_directory(ENV_MESH_UE)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", glb_path)
    task.set_editor_property("destination_path", ENV_MESH_UE)
    task.set_editor_property("destination_name", "collider_mesh")
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    unreal.log("[SetLab] Imported Marble environment mesh")
    return True


def _place_marble_environment():
    """Place imported Marble environment mesh as a large backdrop actor."""
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    for actor in subsystem.get_all_level_actors():
        if actor.actor_has_tag(ENV_TAG):
            subsystem.destroy_actor(actor)

    try:
        paths = unreal.EditorAssetLibrary.list_assets(ENV_MESH_UE, recursive=True, include_folder=False)
    except TypeError:
        paths = unreal.EditorAssetLibrary.list_assets(ENV_MESH_UE, recursive=True)

    env_mesh = None
    if paths:
        for ap in paths:
            try:
                a = unreal.load_asset(ap)
                if a and isinstance(a, unreal.StaticMesh):
                    env_mesh = a
                    break
            except Exception:
                continue

    if env_mesh is None:
        unreal.log_warning("[SetLab] No Marble environment mesh found to place")
        return

    actor = subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0, 0, 0)
    )
    if actor is None:
        return

    actor.set_actor_label("SET_Environment")
    actor.tags.append(SET_TAG)
    actor.tags.append(ENV_TAG)

    smc = actor.get_component_by_class(unreal.StaticMeshComponent)
    if smc:
        smc.set_static_mesh(env_mesh)

    unreal.log("[SetLab] Placed Marble environment backdrop")


# ── Megascans ground plane ───────────────────────────────────────────────

_GROUND_KEYWORDS = {
    "cobblestone": ["cobblestone", "cobble", "paving_stone"],
    "asphalt":     ["asphalt", "road", "tarmac", "blacktop"],
    "concrete":    ["concrete", "cement", "pavement"],
    "grass":       ["grass", "lawn", "turf", "meadow"],
    "dirt":        ["dirt", "soil", "earth", "mud_path"],
    "sand":        ["sand", "beach", "desert", "dune"],
    "gravel":      ["gravel", "pebble", "crushed_stone"],
    "marble":      ["marble", "polished_stone", "travertine"],
    "wood_plank":  ["wood", "plank", "timber", "deck"],
    "brick":       ["brick", "clay_brick", "paver"],
    "slate":       ["slate", "flagstone", "stone_tile"],
    "snow":        ["snow", "ice", "frost"],
    "mud":         ["mud", "wet_soil", "swamp"],
}

_megascans_cache = {}


def _find_megascans_material(ground_keyword):
    """Search Megascans content for a material matching the keyword.

    Scans /Game/Megascans/Surfaces/ for Material Instance assets whose path
    contains any of the search terms for the given ground type. Results are
    cached to avoid repeated content scans.
    """
    if ground_keyword in _megascans_cache:
        return _megascans_cache[ground_keyword]

    if not unreal.EditorAssetLibrary.does_directory_exist(MEGASCANS_ROOT):
        unreal.log_warning(
            "[SetLab] Megascans root not found: %s — install via Quixel Bridge" % MEGASCANS_ROOT
        )
        _megascans_cache[ground_keyword] = None
        return None

    search_terms = _GROUND_KEYWORDS.get(ground_keyword, [ground_keyword])

    try:
        all_assets = unreal.EditorAssetLibrary.list_assets(
            MEGASCANS_ROOT, recursive=True, include_folder=False
        )
    except TypeError:
        all_assets = unreal.EditorAssetLibrary.list_assets(
            MEGASCANS_ROOT, recursive=True
        )

    if not all_assets:
        _megascans_cache[ground_keyword] = None
        return None

    for asset_path in all_assets:
        path_lower = asset_path.lower().replace("\\", "/")
        if not ("_inst" in path_lower or "materialinstance" in path_lower or "mi_" in path_lower):
            if not path_lower.endswith("_mat"):
                continue
        for term in search_terms:
            if term.lower() in path_lower:
                try:
                    mat = unreal.load_asset(asset_path)
                    if mat is not None:
                        _megascans_cache[ground_keyword] = mat
                        unreal.log("[SetLab] Found Megascans material: %s" % asset_path)
                        return mat
                except Exception:
                    continue

    _megascans_cache[ground_keyword] = None
    return None


def _apply_ground_material(actor, smc, ground_keyword, scale_x_m, scale_z_m):
    """Apply a Megascans tiling material to a floor actor's mesh component."""
    mat = _find_megascans_material(ground_keyword)
    if mat is None:
        return False

    smc.set_material(0, mat)

    tile_size_m = 2.0
    u_tiles = max(1.0, scale_x_m / tile_size_m)
    v_tiles = max(1.0, scale_z_m / tile_size_m)

    try:
        smc.set_scalar_parameter_value_on_materials(
            unreal.Name("UVTilingX"), u_tiles
        )
        smc.set_scalar_parameter_value_on_materials(
            unreal.Name("UVTilingY"), v_tiles
        )
    except Exception:
        pass

    actor.tags.append(GROUND_TAG)
    return True


# ── lighting ─────────────────────────────────────────────────────────────

LIGHT_TAG = "SETLAB_LIGHT"

_TIME_TO_SUN_PITCH = {
    "dawn":        -5.0,
    "morning":     25.0,
    "noon":        70.0,
    "afternoon":   45.0,
    "golden_hour": 10.0,
    "sunset":      2.0,
    "dusk":       -10.0,
    "night":      -30.0,
}

_WEATHER_FOG_MULT = {
    "clear":    1.0,
    "overcast": 2.0,
    "cloudy":   1.5,
    "foggy":    6.0,
    "rainy":    3.0,
    "stormy":   4.0,
    "snowy":    2.5,
}

_DEFAULT_ENV = {
    "time_of_day": "noon",
    "weather": "clear",
    "fog_density": 0.02,
    "sun_intensity": 10.0,
    "sun_color_temp": 6500,
}


def _clear_lighting():
    """Remove all previously spawned lighting actors."""
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        if actor.actor_has_tag(LIGHT_TAG):
            subsystem.destroy_actor(actor)


def _color_temp_to_rgb(kelvin):
    """Approximate Kelvin → (R, G, B) in 0..1 for UE LinearColor."""
    t = max(1000, min(40000, kelvin)) / 100.0
    if t <= 66:
        r = 1.0
        g = max(0.0, min(1.0, (99.4708025861 * math.log(t) - 161.1195681661) / 255.0))
    else:
        r = max(0.0, min(1.0, (329.698727446 * ((t - 60) ** -0.1332047592)) / 255.0))
        g = max(0.0, min(1.0, (288.1221695283 * ((t - 60) ** -0.0755148492)) / 255.0))
    if t >= 66:
        b = 1.0
    elif t <= 19:
        b = 0.0
    else:
        b = max(0.0, min(1.0, (138.5177312231 * math.log(t - 10) - 305.0447927307) / 255.0))
    return r, g, b


def _setup_full_lighting(env):
    """Spawn Directional Light, Sky Atmosphere, Height Fog, Volumetric Clouds,
    SkyLight, and Post Process Volume with Lumen GI — all driven by the spec's
    environment block.
    """
    _clear_lighting()
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    time_of_day = env.get("time_of_day", "noon")
    weather = env.get("weather", "clear")
    fog_density = float(env.get("fog_density", 0.02))
    sun_intensity = float(env.get("sun_intensity", 10.0))
    sun_color_temp = int(env.get("sun_color_temp", 6500))

    sun_pitch = _TIME_TO_SUN_PITCH.get(time_of_day, 70.0)
    sun_yaw = -45.0

    count = 0

    # ── Directional Light (sun) ──
    dl = subsystem.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(0, 0, 1000),
        unreal.Rotator(sun_pitch, sun_yaw, 0),
    )
    if dl:
        dl.set_actor_label("SET_Sun")
        dl.tags.append(SET_TAG)
        dl.tags.append(LIGHT_TAG)
        comp = dl.get_component_by_class(unreal.DirectionalLightComponent)
        if comp:
            comp.set_editor_property("intensity", sun_intensity)
            comp.set_editor_property("light_color", unreal.Color(
                r=int(_color_temp_to_rgb(sun_color_temp)[0] * 255),
                g=int(_color_temp_to_rgb(sun_color_temp)[1] * 255),
                b=int(_color_temp_to_rgb(sun_color_temp)[2] * 255),
                a=255,
            ))
            comp.set_editor_property("use_temperature", True)
            comp.set_editor_property("temperature", float(sun_color_temp))
            try:
                comp.set_editor_property("atmosphere_sun_light", True)
            except Exception:
                pass
        count += 1

    # ── Sky Atmosphere ──
    try:
        sa = subsystem.spawn_actor_from_class(
            unreal.SkyAtmosphere, unreal.Vector(0, 0, 0)
        )
        if sa:
            sa.set_actor_label("SET_SkyAtmosphere")
            sa.tags.append(SET_TAG)
            sa.tags.append(LIGHT_TAG)
            count += 1
    except Exception:
        unreal.log_warning("[SetLab] Could not spawn SkyAtmosphere")

    # ── Exponential Height Fog ──
    try:
        fog_mult = _WEATHER_FOG_MULT.get(weather, 1.0)
        final_fog = fog_density * fog_mult

        ehf = subsystem.spawn_actor_from_class(
            unreal.ExponentialHeightFog, unreal.Vector(0, 0, 100)
        )
        if ehf:
            ehf.set_actor_label("SET_HeightFog")
            ehf.tags.append(SET_TAG)
            ehf.tags.append(LIGHT_TAG)
            fog_comp = ehf.get_component_by_class(unreal.ExponentialHeightFogComponent)
            if fog_comp:
                fog_comp.set_editor_property("fog_density", final_fog)
                fog_comp.set_editor_property("fog_max_opacity", 1.0)
                try:
                    fog_comp.set_editor_property("volumetric_fog", True)
                except Exception:
                    pass
            count += 1
    except Exception:
        unreal.log_warning("[SetLab] Could not spawn ExponentialHeightFog")

    # ── Volumetric Clouds ──
    try:
        vc = subsystem.spawn_actor_from_class(
            unreal.VolumetricCloud, unreal.Vector(0, 0, 0)
        )
        if vc:
            vc.set_actor_label("SET_VolumetricClouds")
            vc.tags.append(SET_TAG)
            vc.tags.append(LIGHT_TAG)
            count += 1
    except Exception:
        pass

    # ── SkyLight ──
    sl = subsystem.spawn_actor_from_class(
        unreal.SkyLight, unreal.Vector(0, 0, 500)
    )
    if sl:
        sl.set_actor_label("SET_SkyLight")
        sl.tags.append(SET_TAG)
        sl.tags.append(LIGHT_TAG)
        sl_comp = sl.get_component_by_class(unreal.SkyLightComponent)
        if sl_comp:
            sl_comp.set_editor_property(
                "source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE
            )
            if time_of_day == "night":
                sl_comp.set_editor_property("intensity", 0.5)
            sl_comp.recapture_sky()
        count += 1

    # ── Post Process Volume (Lumen GI) ──
    try:
        ppv = subsystem.spawn_actor_from_class(
            unreal.PostProcessVolume, unreal.Vector(0, 0, 0)
        )
        if ppv:
            ppv.set_actor_label("SET_PostProcess")
            ppv.tags.append(SET_TAG)
            ppv.tags.append(LIGHT_TAG)
            ppv.set_editor_property("unbound", True)

            settings = ppv.settings
            try:
                settings.set_editor_property("override_global_illumination_method", True)
                settings.set_editor_property(
                    "global_illumination_method",
                    unreal.GlobalIlluminationMethod.LUMEN,
                )
            except Exception:
                pass
            try:
                settings.set_editor_property("override_reflection_method", True)
                settings.set_editor_property(
                    "reflection_method",
                    unreal.ReflectionMethod.LUMEN,
                )
            except Exception:
                pass
            try:
                settings.set_editor_property("override_auto_exposure_method", True)
                settings.set_editor_property(
                    "auto_exposure_method",
                    unreal.AutoExposureMethod.AEM_HISTOGRAM,
                )
            except Exception:
                pass

            count += 1
    except Exception:
        unreal.log_warning("[SetLab] Could not spawn PostProcessVolume")

    unreal.log(
        "[SetLab] Lighting setup: %d actors (time=%s, weather=%s, sun=%.1f lux @ %dK)"
        % (count, time_of_day, weather, sun_intensity, sun_color_temp)
    )


# ── placement ───────────────────────────────────────────────────────────

def _clear_previous():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        if actor.actor_has_tag(SET_TAG):
            subsystem.destroy_actor(actor)


def _place_from_spec():
    if not os.path.isfile(WATCH_SPEC):
        unreal.log("[SetLab] No set_spec.json found, skipping placement.")
        return

    with open(WATCH_SPEC, "r") as f:
        spec = json.load(f)

    modules = spec.get("modules", [])
    if not modules:
        return

    ground_keyword = spec.get("ground_material", "").strip().lower()

    _clear_previous()

    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cube_mesh = unreal.load_asset("/Engine/BasicShapes/Cube")
    plane_mesh = unreal.load_asset("/Engine/BasicShapes/Plane")
    hd_used = 0
    cube_used = 0
    ground_applied = 0

    for m in modules:
        px, py, pz = m["position"]
        sx, sy, sz = m["scale"]
        rq = m.get("rotation_quat")
        if rq and len(rq) == 4:
            rot = _setlab_quat_to_ue(rq[0], rq[1], rq[2], rq[3])
        else:
            rx, ry, rz = m.get("rotation_deg", [0, 0, 0])
            rot = _setlab_rot_to_ue(rx, ry, rz)
        hd_mesh = _find_static_mesh_for_module(m["id"])

        if hd_mesh is not None:
            half_ext, center = _get_mesh_bounds_cm(hd_mesh)

            if half_ext is not None and half_ext.x > 0.01 and half_ext.y > 0.01 and half_ext.z > 0.01:
                # Target size in UE cm — Y↔Z swap: UE(X,Y,Z) = glTF(X,Z,Y)
                target_x = sx * 100.0
                target_y = sz * 100.0
                target_z = sy * 100.0

                mesh_sx = target_x / (2.0 * half_ext.x)
                mesh_sy = target_y / (2.0 * half_ext.y)
                mesh_sz = target_z / (2.0 * half_ext.z)
                scale = unreal.Vector(mesh_sx, mesh_sy, mesh_sz)

                base_loc = _setlab_pos_to_ue(px, py, pz)
                loc = unreal.Vector(
                    base_loc.x - center.x * mesh_sx,
                    base_loc.y - center.y * mesh_sy,
                    base_loc.z - center.z * mesh_sz,
                )

                if hd_used == 0:
                    unreal.log(
                        "[SetLab][diag] %s  bounds_half=(%.1f,%.1f,%.1f) center=(%.1f,%.1f,%.1f)"
                        "  target=(%.0f,%.0f,%.0f) scale=(%.3f,%.3f,%.3f)"
                        % (m["id"], half_ext.x, half_ext.y, half_ext.z,
                           center.x, center.y, center.z,
                           target_x, target_y, target_z,
                           mesh_sx, mesh_sy, mesh_sz)
                    )
            else:
                loc = _setlab_pos_to_ue(px, py, pz)
                scale = unreal.Vector(sx, sz, sy)
        else:
            loc = _setlab_pos_to_ue(px, py, pz)
            scale = unreal.Vector(sx, sz, sy)

        actor = subsystem.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
        if actor is None:
            continue

        actor.set_actor_label("SET_%s" % m["id"])
        actor.set_actor_scale3d(scale)
        actor.tags.append(SET_TAG)

        smc = actor.get_component_by_class(unreal.StaticMeshComponent)
        is_floor = m.get("asset", "") == "mod_floor"

        if is_floor and plane_mesh and ground_keyword:
            use_mesh = plane_mesh
        elif hd_mesh is not None:
            use_mesh = hd_mesh
        else:
            use_mesh = cube_mesh

        if smc and use_mesh:
            smc.set_static_mesh(use_mesh)

        if is_floor and ground_keyword and smc:
            if _apply_ground_material(actor, smc, ground_keyword, sx, sz):
                ground_applied += 1

        if hd_mesh is not None and not is_floor:
            hd_used += 1
        elif not is_floor:
            cube_used += 1

    env = spec.get("environment") or _DEFAULT_ENV
    _setup_full_lighting(env)

    ground_note = ", %d Megascans ground" % ground_applied if ground_applied else ""
    unreal.log(
        "[SetLab] Placed %d modules (%d HD mesh, %d fallback cube%s)."
        % (len(modules), hd_used, cube_used, ground_note)
    )


def _check_vr_flag():
    if not os.path.isfile(VR_FLAG_PATH):
        return
    os.remove(VR_FLAG_PATH)
    unreal.log("[SetLab] VR mode flag detected — enabling VR Preview...")
    unreal.SystemLibrary.execute_console_command(None, "vr.bEnableStereo 1")


# ── real-time modify ──────────────────────────────────────────────────

def _apply_modify_commands():
    """Check for modify_commands.json and apply tier-appropriate changes."""
    global _last_modify_mtime

    if not os.path.isfile(MODIFY_CMD_PATH):
        return

    mtime = os.path.getmtime(MODIFY_CMD_PATH)
    if mtime <= _last_modify_mtime:
        return
    _last_modify_mtime = mtime

    try:
        with open(MODIFY_CMD_PATH, "r") as f:
            cmd = json.load(f)
    except Exception as e:
        unreal.log_warning("[SetLab] Failed to read modify_commands.json: %s" % e)
        return

    tier = cmd.get("tier", "")
    commands = cmd.get("commands", {})

    if tier == "instant":
        _apply_instant_modify(commands)
    elif tier == "fast":
        _apply_fast_modify(commands, cmd.get("module_ids", []))
    elif tier == "moderate":
        unreal.log("[SetLab] Moderate modification — waiting for mesh regeneration...")
    else:
        unreal.log_warning("[SetLab] Unknown modify tier: %s" % tier)


def _apply_instant_modify(commands):
    """Apply environment/lighting parameter changes in-engine instantly."""
    env_update = commands.get("environment", {})
    if not env_update:
        return

    spec_env = _DEFAULT_ENV.copy()
    if os.path.isfile(WATCH_SPEC):
        try:
            with open(WATCH_SPEC, "r") as f:
                spec = json.load(f)
            spec_env.update(spec.get("environment") or {})
        except Exception:
            pass
    spec_env.update(env_update)

    _clear_lighting()
    _setup_full_lighting(spec_env)
    unreal.log("[SetLab] Instant modify applied — lighting updated")


def _apply_fast_modify(commands, module_ids):
    """Signal that fast (retexture) modification is in progress."""
    retexture = commands.get("retexture", {})
    affected = list(retexture.keys()) if retexture else module_ids
    unreal.log(
        "[SetLab] Fast modify — retexturing %d module(s): %s"
        % (len(affected), ", ".join(affected))
    )


# ── tick / start / stop ────────────────────────────────────────────────

def _tick(delta_time):
    global _last_mtime, _last_check

    now = time.time()
    if now - _last_check < POLL_SECONDS:
        return
    _last_check = now

    _apply_modify_commands()

    if not os.path.isfile(WATCH_GLTF):
        return

    mtime = os.path.getmtime(WATCH_GLTF)
    if mtime <= _last_mtime:
        return

    _last_mtime = mtime
    unreal.log("[SetLab] Change detected — importing & placing...")
    _import_gltf()
    _import_hd_glb_folder()
    if _import_marble_environment():
        _place_marble_environment()
    _place_from_spec()
    _check_vr_flag()


def start():
    global _handle, _last_mtime
    if _handle is not None:
        unreal.log("[SetLab] Already running.")
        return

    _last_mtime = 0.0
    _handle = unreal.register_slate_post_tick_callback(_tick)
    unreal.log("[SetLab] Watcher started (poll=%.1fs)" % POLL_SECONDS)

    if os.path.isfile(WATCH_GLTF):
        unreal.log("[SetLab] Existing file found — importing now...")
        _import_gltf()
        _import_hd_glb_folder()
        if _import_marble_environment():
            _place_marble_environment()
        _place_from_spec()
        _check_vr_flag()
        _last_mtime = os.path.getmtime(WATCH_GLTF)


def stop():
    global _handle
    if _handle is not None:
        unreal.unregister_slate_post_tick_callback(_handle)
        _handle = None
        unreal.log("[SetLab] Watcher stopped.")


start()
