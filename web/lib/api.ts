/** API origin (no trailing slash). Browser: uses NEXT_PUBLIC_API_URL or origin+basePath. SSR/build: localhost default. */
export function apiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof window !== "undefined") {
    const bp = (process.env.NEXT_PUBLIC_BASE_PATH || "").trim();
    return `${window.location.origin}${bp}`;
  }
  return "http://localhost:8000";
}

export interface ModulePlacement {
  id: string;
  asset: string;
  description?: string;
  position: [number, number, number];
  rotation_deg: [number, number, number];
  scale: [number, number, number];
}

/** Matches setlab `EnvironmentSettings` — drives web viewer sky / lights / fog. */
export interface EnvironmentSettings {
  time_of_day?: string;
  weather?: string;
  fog_density?: number;
  sun_intensity?: number;
  sun_color_temp?: number;
}

export interface MeshGenStatus {
  status: "running" | "completed" | "failed" | "partial";
  total: number;
  done: number;
  modules: Record<string, string>;
  error?: string;
}

export interface SetSpec {
  title: string;
  era_style: string;
  notes: string;
  modules: ModulePlacement[];
  ground_material?: string;
  environment?: EnvironmentSettings | null;
  /** Saved per-module GLB Δ rotation (°); optional on older runs. */
  per_module_glb_extra_deg?: Record<string, [number, number, number]>;
}

export interface GenerateResult {
  id: string;
  spec: SetSpec;
  gltfUrl: string;
  usdaUrl: string;
  specUrl: string;
  /** Present when POST /api/refine-module was used */
  refined_module_id?: string;
  /** True when description/asset changed; run Generate Missing 3D for new mesh */
  mesh_regen_suggested?: boolean;
}

export interface HistoryItem {
  id: string;
  title: string;
  era_style: string;
  moduleCount: number;
  gltfUrl: string;
}

export interface AppConfig {
  ue_project: string;
  ollama_host: string;
  default_model: string;
  default_backend: string;
}

export async function enhancePrompt(
  prompt: string,
  model = "claude-sonnet-4-6",
): Promise<{ enhanced: string }> {
  const res = await fetch(`${apiBase()}/api/enhance-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, model }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Enhance prompt failed");
  }
  return res.json();
}

export async function generate(
  prompt: string,
  backend = "mock",
  model = "llama3.2",
  maxModules?: number,
): Promise<GenerateResult> {
  const body: Record<string, unknown> = { prompt, backend, model };
  if (
    maxModules != null &&
    Number.isFinite(maxModules) &&
    maxModules >= 1 &&
    maxModules <= 256
  ) {
    body.max_modules = Math.floor(maxModules);
  }
  const res = await fetch(`${apiBase()}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Generation failed");
  }
  return res.json();
}

export type DeployRotationPayload = {
  buildingGlbExtraDeg: [number, number, number];
  perModuleGlbExtraDeg: Record<string, [number, number, number]>;
};

export async function deploy(
  runId: string,
  ueProject?: string,
  vr?: boolean,
  rotation?: DeployRotationPayload | null
): Promise<{
  deployed: boolean;
  destination: string;
  meshes_copied?: number;
}> {
  const params = vr ? "?vr=true" : "";
  const body: Record<string, unknown> = { ue_project: ueProject || undefined };
  if (rotation) {
    body.building_glb_extra_deg = rotation.buildingGlbExtraDeg;
    body.per_module_glb_extra_deg = rotation.perModuleGlbExtraDeg;
  }
  const res = await fetch(`${apiBase()}/api/deploy/${runId}${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Deploy failed");
  }
  return res.json();
}

export async function fetchHistory(): Promise<HistoryItem[]> {
  const res = await fetch(`${apiBase()}/api/history`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.items ?? [];
}

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch(`${apiBase()}/api/config`);
  return res.json();
}

export async function updateConfig(
  ueProject: string
): Promise<{ ue_project: string }> {
  const res = await fetch(`${apiBase()}/api/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ue_project: ueProject }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Config update failed");
  }
  return res.json();
}

export async function refine(
  runId: string,
  instruction: string,
  backend = "claude",
  model = "claude-sonnet-4-6"
): Promise<GenerateResult> {
  const res = await fetch(`${apiBase()}/api/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, instruction, backend, model }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Refine failed");
  }
  return res.json();
}

export async function refineModule(
  runId: string,
  moduleId: string,
  instruction: string,
  backend = "claude",
  model = "claude-sonnet-4-6",
): Promise<GenerateResult> {
  const res = await fetch(`${apiBase()}/api/refine-module`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      module_id: moduleId,
      instruction,
      backend,
      model,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Refine module failed");
  }
  return res.json();
}

export function gltfUrl(path: string): string {
  return `${apiBase()}${path}`;
}

export async function startMeshGen(
  runId: string,
  opts?: { moduleIds?: string[] },
): Promise<MeshGenStatus> {
  const body =
    opts?.moduleIds && opts.moduleIds.length > 0
      ? { module_ids: opts.moduleIds }
      : {};
  const res = await fetch(`${apiBase()}/api/meshgen/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Mesh generation failed to start");
  }
  return res.json();
}

export async function pollMeshStatus(runId: string): Promise<MeshGenStatus> {
  const res = await fetch(`${apiBase()}/api/meshgen/${runId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to poll mesh status");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// HD mesh generation (FLUX multi-view images → Rodin Gen-2 concat → GLB)
// ---------------------------------------------------------------------------

export interface HdGenStatus {
  status: "running" | "completed" | "failed";
  phase: string;
  total: number;
  done: number;
  modules: Record<string, string>;
  error?: string;
}

export async function startHdGen(runId: string): Promise<HdGenStatus> {
  const res = await fetch(`${apiBase()}/api/hdgen/${runId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "HD generation failed to start");
  }
  return res.json();
}

export async function pollHdStatus(runId: string): Promise<HdGenStatus> {
  const res = await fetch(`${apiBase()}/api/hdgen/${runId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to poll HD status");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Marble environment (World Labs) → out/<run_id>/environment/
// ---------------------------------------------------------------------------

export interface EnvGenStatus {
  status: "running" | "completed" | "failed";
  phase?: string;
  progress?: number;
  error?: string;
  result?: unknown;
}

export async function startEnvGen(runId: string): Promise<EnvGenStatus> {
  const res = await fetch(`${apiBase()}/api/envgen/${runId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Marble environment generation failed to start");
  }
  return res.json();
}

export async function pollEnvGenStatus(runId: string): Promise<EnvGenStatus> {
  const res = await fetch(`${apiBase()}/api/envgen/${runId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to poll envgen status");
  }
  return res.json();
}

/** Byte-copy meshes/<from>.glb → meshes/<to>.glb (same run). */
export async function copyMeshGlb(
  runId: string,
  fromModuleId: string,
  toModuleId: string,
): Promise<{ ok: boolean; run_id: string; from_module_id: string; to_module_id: string }> {
  const res = await fetch(`${apiBase()}/api/copy-mesh-glb/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      from_module_id: fromModuleId,
      to_module_id: toModuleId,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Copy mesh GLB failed");
  }
  return res.json();
}

export async function orientBuildingsToRoad(runId: string): Promise<GenerateResult> {
  const res = await fetch(`${apiBase()}/api/orient-buildings/${runId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Orient buildings failed");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Material enhancement (3D AI Studio texture-edit)
// ---------------------------------------------------------------------------

export interface MaterialEnhanceStatus {
  status: "running" | "completed" | "failed";
  total: number;
  done: number;
  modules: Record<string, string>;
  error?: string;
}

export async function startMaterialEnhance(
  runId: string,
  opts?: { style?: string; customPrompt?: string },
): Promise<MaterialEnhanceStatus> {
  const body: Record<string, unknown> = {};
  if (opts?.style) body.style = opts.style;
  if (opts?.customPrompt) body.custom_prompt = opts.customPrompt;
  const res = await fetch(`${apiBase()}/api/material-enhance/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Material enhancement failed to start");
  }
  return res.json();
}

export async function pollMaterialEnhanceStatus(
  runId: string,
): Promise<MaterialEnhanceStatus> {
  const res = await fetch(`${apiBase()}/api/material-enhance/${runId}/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Failed to poll material enhancement status");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Real-time modification (director prompt → tier classification → dispatch)
// ---------------------------------------------------------------------------

export interface ModifyResult {
  tier: "instant" | "fast" | "moderate";
  summary: string;
  module_ids: string[];
  commands: Record<string, unknown>;
}

export async function sendModification(
  runId: string,
  instruction: string,
): Promise<ModifyResult> {
  const res = await fetch(`${apiBase()}/api/modify/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Modification failed");
  }
  return res.json();
}

/** Persist viewer per-module Δ (°) into out/<runId>/set_spec.json (non-zero only). */
export async function saveViewerEdits(
  runId: string,
  perModuleGlbExtraDeg: Record<string, [number, number, number]>,
): Promise<{ saved: boolean; modules_with_delta: number }> {
  const body: Record<string, unknown> = {
    per_module_glb_extra_deg: perModuleGlbExtraDeg,
  };
  const res = await fetch(`${apiBase()}/api/save-edits/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Save failed");
  }
  return res.json();
}
