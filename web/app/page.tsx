"use client";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import dynamic from "next/dynamic";
import PromptPanel from "@/components/PromptPanel";
import ScenePipelineBanner from "@/components/ScenePipelineBanner";
import SpecPanel from "@/components/SpecPanel";
import HistoryPanel from "@/components/HistoryPanel";
import SettingsPanel from "@/components/SettingsPanel";
import {
  generate,
  refine,
  refineModule,
  deploy,
  fetchHistory,
  fetchConfig,
  updateConfig,
  gltfUrl,
  startMeshGen,
  pollMeshStatus,
  startHdGen,
  pollHdStatus,
  startMaterialEnhance,
  pollMaterialEnhanceStatus,
  startEnvGen,
  pollEnvGenStatus,
  saveViewerEdits,
  type SetSpec,
  type GenerateResult,
  type HistoryItem,
  type MeshGenStatus,
  type HdGenStatus,
  type MaterialEnhanceStatus,
  type EnvGenStatus,
} from "@/lib/api";
import { parseMeshExtraDegFromEnv } from "@/lib/meshOrientation";
import {
  parseAutoPipelineAfterGenerate,
  parseAutoPostPipeline,
} from "@/lib/autoPipeline";

const Viewer3D = dynamic(() => import("@/components/Viewer3D"), { ssr: false });
const VRViewer = dynamic(() => import("@/components/VRViewer"), { ssr: false });

export default function Home() {
  const [currentGltf, setCurrentGltf] = useState<string | null>(null);
  const [currentSpec, setCurrentSpec] = useState<SetSpec | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [deployMessage, setDeployMessage] = useState<string | null>(null);
  const [isSavingEdits, setIsSavingEdits] = useState(false);
  const [saveEditMessage, setSaveEditMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [viewMode, setViewMode] = useState<"3d" | "vr">("3d");

  const [meshStatus, setMeshStatus] = useState<MeshGenStatus | null>(null);
  const [meshGlbs, setMeshGlbs] = useState<Record<string, string>>({});
  const meshGlbCopyBustRef = useRef<Record<string, number>>({});
  /** `${runId}:${moduleId}` already given a fresh bust token for this HD run. */
  const hdBustDoneRef = useRef<Set<string>>(new Set());
  const [isMeshGenerating, setIsMeshGenerating] = useState(false);
  const [meshPollToken, setMeshPollToken] = useState(0);
  const [meshedOnlyView, setMeshedOnlyView] = useState(false);

  const [hdStatus, setHdStatus] = useState<HdGenStatus | null>(null);
  const [isHdGenerating, setIsHdGenerating] = useState(false);
  const [hdPollToken, setHdPollToken] = useState(0);

  const [materialStatus, setMaterialStatus] = useState<MaterialEnhanceStatus | null>(null);
  const [isMaterialEnhancing, setIsMaterialEnhancing] = useState(false);
  const [materialPollToken, setMaterialPollToken] = useState(0);

  const [envGenStatus, setEnvGenStatus] = useState<EnvGenStatus | null>(null);
  const [envPollToken, setEnvPollToken] = useState(0);

  /** Set in handleGenerate when auto mesh should chain to HD for this run_id. */
  const autoMeshAfterGenerateRunIdRef = useRef<string | null>(null);
  const autoHdAfterMeshRunIdRef = useRef<string | null>(null);

  const meshGlbExtraDeg = useMemo(() => parseMeshExtraDegFromEnv(), []);
  const autoPipeline = useMemo(() => parseAutoPipelineAfterGenerate(), []);
  const autoPost = useMemo(() => parseAutoPostPipeline(), []);

  /** 자동 머티리얼 향상을 이미 시작한 run_id (중복 방지). */
  const materialAutoStartedRef = useRef<string | null>(null);
  /** 자동 Deploy를 이미 수행한 run_id (중복 방지). */
  const deployAutoDoneRef = useRef<string | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [perModuleGlbExtraDeg, setPerModuleGlbExtraDeg] = useState<
    Record<string, [number, number, number]>
  >({});

  /** True from New Scene Generate until auto mesh/HD (if any) finish. */
  const [scenePipelineBusy, setScenePipelineBusy] = useState(false);
  /** Run id for the in-flight generate pipeline (clears when pipeline ends). */
  const [pipelineRunId, setPipelineRunId] = useState<string | null>(null);

  const [backend, setBackend] = useState("claude");
  const [model, setModel] = useState("claude-sonnet-4-6");
  const [ueProject, setUeProject] = useState("");

  const runDeployInternal = useCallback(
    async (opts: { vr: boolean; auto: boolean }) => {
      if (!currentRunId) return;
      setIsDeploying(true);
      setDeployMessage(null);
      try {
        const res = await deploy(
          currentRunId,
          ueProject || undefined,
          opts.vr,
          {
            buildingGlbExtraDeg: meshGlbExtraDeg,
            perModuleGlbExtraDeg: perModuleGlbExtraDeg,
          },
        );
        const meshNote =
          res.meshes_copied != null && res.meshes_copied > 0
            ? ` · HD .glb ${res.meshes_copied}개 복사`
            : "";
        const prefix = opts.auto ? "[자동] " : "";
        setDeployMessage(
          `${prefix}Deployed to ${res.destination}${opts.vr ? " (VR)" : ""}${meshNote}`,
        );
      } catch (e) {
        setDeployMessage(
          (opts.auto ? "[자동] " : "") +
            (e instanceof Error ? e.message : "Deploy failed"),
        );
      } finally {
        setIsDeploying(false);
      }
    },
    [currentRunId, ueProject, meshGlbExtraDeg, perModuleGlbExtraDeg],
  );

  const handleBackendChange = useCallback((be: string) => {
    setBackend(be);
    if (be === "claude") setModel("claude-sonnet-4-6");
    else if (be === "ollama") setModel("llama3.1:8b");
  }, []);

  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        if (cfg.default_backend) setBackend(cfg.default_backend);
        if (cfg.default_model) setModel(cfg.default_model);
        if (cfg.ue_project) setUeProject(cfg.ue_project);
      })
      .catch(() => {});
    fetchHistory()
      .then(setHistory)
      .catch(() => {});
  }, []);

  const applyMeshStatus = useCallback((runId: string, status: MeshGenStatus) => {
    setMeshStatus(status);
    setMeshGlbs((prev) => {
      const glbs: Record<string, string> = {};
      for (const [moduleId, modStatus] of Object.entries(status.modules)) {
        if (modStatus === "done") {
          const base = gltfUrl(`/api/outputs/${runId}/meshes/${moduleId}.glb`);
          const b = meshGlbCopyBustRef.current[moduleId];
          glbs[moduleId] = b != null ? `${base}?t=${b}` : base;
        }
      }
      const prevKeys = Object.keys(prev);
      const newKeys = Object.keys(glbs);
      if (
        prevKeys.length === newKeys.length &&
        newKeys.every((k) => prev[k] === glbs[k])
      ) {
        return prev;
      }
      return glbs;
    });
    setIsMeshGenerating(status.status === "running");
  }, []);

  useEffect(() => {
    meshGlbCopyBustRef.current = {};
    hdBustDoneRef.current = new Set();
  }, [currentRunId]);

  const handleMeshGlbCopied = useCallback((toModuleId: string) => {
    meshGlbCopyBustRef.current[toModuleId] = Date.now();
    setMeshPollToken((t) => t + 1);
  }, []);

  useEffect(() => {
    setSelectedModuleId(null);

    if (!currentSpec) {
      setPerModuleGlbExtraDeg({});
      return;
    }
    const ext = currentSpec.per_module_glb_extra_deg;
    const next: Record<string, [number, number, number]> = {};
    if (ext && typeof ext === "object") {
      for (const [k, v] of Object.entries(ext)) {
        if (
          Array.isArray(v) &&
          v.length === 3 &&
          v.every((n) => typeof n === "number" && Number.isFinite(n))
        ) {
          next[k] = [v[0], v[1], v[2]];
        }
      }
    }
    setPerModuleGlbExtraDeg(next);
  }, [currentSpec]);

  useEffect(() => {
    if (!currentRunId) {
      setMeshStatus(null);
      setMeshGlbs({});
      setIsMeshGenerating(false);
      return;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const status = await pollMeshStatus(currentRunId);
        if (cancelled) return;
        applyMeshStatus(currentRunId, status);
        if (status.status === "running") {
          timeoutId = setTimeout(tick, 2000);
        }
      } catch (e) {
        if (!cancelled) {
          setIsMeshGenerating(false);
          setMeshStatus({
            status: "failed",
            total: 0,
            done: 0,
            modules: {},
            error: e instanceof Error ? e.message : "메시 상태 조회 실패",
          });
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [currentRunId, meshPollToken, applyMeshStatus]);

  /** After auto mesh from New Scene Generate completes, optionally start HD. */
  useEffect(() => {
    if (!currentRunId || !meshStatus) return;
    if (autoMeshAfterGenerateRunIdRef.current !== currentRunId) return;

    if (meshStatus.status === "failed") {
      autoMeshAfterGenerateRunIdRef.current = null;
      return;
    }
    if (meshStatus.status !== "completed") return;

    autoMeshAfterGenerateRunIdRef.current = null;

    if (!autoPipeline.hd) return;
    if (autoHdAfterMeshRunIdRef.current === currentRunId) return;
    autoHdAfterMeshRunIdRef.current = currentRunId;

    void (async () => {
      try {
        await startHdGen(currentRunId);
        setHdPollToken((t) => t + 1);
      } catch (e) {
        autoHdAfterMeshRunIdRef.current = null;
        setHdStatus({
          status: "failed",
          phase: "error",
          total: 0,
          done: 0,
          modules: {},
          error:
            e instanceof Error ? e.message : "Auto HD generation failed to start",
        });
        setIsHdGenerating(false);
      }
    })();
  }, [meshStatus?.status, currentRunId, autoPipeline.hd]);

  const handlePerModuleGlbExtraDeg = useCallback(
    (moduleId: string, next: [number, number, number]) => {
      setPerModuleGlbExtraDeg((prev) => {
        if (next[0] === 0 && next[1] === 0 && next[2] === 0) {
          const { [moduleId]: _, ...rest } = prev;
          return rest;
        }
        return { ...prev, [moduleId]: next };
      });
    },
    [],
  );

  const applyHdStatus = useCallback((runId: string, status: HdGenStatus) => {
    setHdStatus(status);
    setIsHdGenerating(status.status === "running");
    if (status.status === "completed" || status.status === "running") {
      const glbs: Record<string, string> = {};
      for (const [moduleId, modStatus] of Object.entries(status.modules)) {
        if (modStatus === "done") {
          // HD overwrites the same <id>.glb; bust the URL so drei refetches the
          // HD mesh instead of serving the stale low-res cached one. Force a
          // fresh token once per module per HD run (stable across repeat polls,
          // and independent of any pre-existing mesh/copy token).
          const hdKey = `${runId}:${moduleId}`;
          if (!hdBustDoneRef.current.has(hdKey)) {
            meshGlbCopyBustRef.current[moduleId] = Date.now();
            hdBustDoneRef.current.add(hdKey);
          }
          const base = gltfUrl(`/api/outputs/${runId}/meshes/${moduleId}.glb`);
          const b = meshGlbCopyBustRef.current[moduleId];
          glbs[moduleId] = `${base}?t=${b}`;
        }
      }
      setMeshGlbs((prev) => ({ ...prev, ...glbs }));
    }
  }, []);

  useEffect(() => {
    if (!currentRunId || hdPollToken === 0) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const status = await pollHdStatus(currentRunId);
        if (cancelled) return;
        applyHdStatus(currentRunId, status);
        if (status.status === "running") {
          timeoutId = setTimeout(tick, 5000);
        }
      } catch (e) {
        if (!cancelled) {
          setIsHdGenerating(false);
          setHdStatus({
            status: "failed",
            phase: "error",
            total: 0,
            done: 0,
            modules: {},
            error: e instanceof Error ? e.message : "HD 상태 조회 실패",
          });
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [currentRunId, hdPollToken, applyHdStatus]);

  useEffect(() => {
    if (!currentRunId || materialPollToken === 0) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const status = await pollMaterialEnhanceStatus(currentRunId);
        if (cancelled) return;
        setMaterialStatus(status);
        setIsMaterialEnhancing(status.status === "running");
        if (status.status === "running") {
          timeoutId = setTimeout(tick, 3000);
        } else if (status.status === "completed") {
          setMeshPollToken((t) => t + 1);
        }
      } catch (e) {
        if (!cancelled) {
          setIsMaterialEnhancing(false);
          setMaterialStatus({
            status: "failed",
            total: 0,
            done: 0,
            modules: {},
            error: e instanceof Error ? e.message : "머티리얼 상태 조회 실패",
          });
        }
      }
    };

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [currentRunId, materialPollToken]);

  useEffect(() => {
    if (!scenePipelineBusy || !pipelineRunId) return;
    if (currentRunId !== pipelineRunId) {
      setScenePipelineBusy(false);
      setPipelineRunId(null);
      return;
    }

    const wantMesh = autoPipeline.mesh;
    const wantHd = autoPipeline.hd;
    const post = autoPost.material || autoPost.deploy || autoPost.marble;

    if (wantMesh && meshStatus?.status === "failed" && !wantHd) {
      if (!post) {
        setScenePipelineBusy(false);
        setPipelineRunId(null);
      }
      return;
    }

    if (wantMesh && meshStatus?.status === "failed" && wantHd) {
      if (!post) {
        setScenePipelineBusy(false);
        setPipelineRunId(null);
      }
      return;
    }

    if (post) {
      return;
    }

    if (wantHd) {
      if (hdStatus?.status === "completed" || hdStatus?.status === "failed") {
        setScenePipelineBusy(false);
        setPipelineRunId(null);
      }
      return;
    }

    if (wantMesh) {
      const terminal =
        meshStatus?.status === "completed" ||
        meshStatus?.status === "failed" ||
        meshStatus?.status === "partial";
      if (terminal) {
        setScenePipelineBusy(false);
        setPipelineRunId(null);
      }
    }
  }, [
    scenePipelineBusy,
    pipelineRunId,
    currentRunId,
    autoPipeline.mesh,
    autoPipeline.hd,
    autoPost.material,
    autoPost.deploy,
    autoPost.marble,
    meshStatus?.status,
    hdStatus?.status,
  ]);

  /** HD(또는 메시만) 성공 후 자동 머티리얼 향상 시작. */
  useEffect(() => {
    if (!autoPost.material) return;
    if (!scenePipelineBusy || !pipelineRunId || currentRunId !== pipelineRunId)
      return;
    if (materialAutoStartedRef.current === currentRunId) return;

    let primarySuccess = false;
    if (autoPipeline.hd) {
      if (hdStatus?.status === "completed") primarySuccess = true;
    } else if (autoPipeline.mesh) {
      if (
        meshStatus?.status === "completed" ||
        meshStatus?.status === "partial"
      )
        primarySuccess = true;
    }

    if (!primarySuccess) return;

    materialAutoStartedRef.current = currentRunId;
    void (async () => {
      try {
        await startMaterialEnhance(currentRunId, {
          style: autoPost.materialStyle,
        });
        setIsMaterialEnhancing(true);
        setMaterialPollToken((t) => t + 1);
      } catch (e) {
        setMaterialStatus({
          status: "failed",
          total: 0,
          done: 0,
          modules: {},
          error: e instanceof Error ? e.message : "Auto material failed",
        });
        setIsMaterialEnhancing(false);
      }
    })();
  }, [
    autoPost.material,
    autoPost.materialStyle,
    scenePipelineBusy,
    pipelineRunId,
    currentRunId,
    autoPipeline.hd,
    autoPipeline.mesh,
    hdStatus?.status,
    meshStatus?.status,
  ]);

  /** 자동 Deploy: 머티리얼 생략 시 1차 완료 직후 / 머티리얼 종료 후 / 1차 실패 시. */
  useEffect(() => {
    if (!autoPost.deploy) return;
    if (!scenePipelineBusy || !pipelineRunId || currentRunId !== pipelineRunId)
      return;
    if (deployAutoDoneRef.current === currentRunId) return;

    const wantHd = autoPipeline.hd;
    const wantMesh = autoPipeline.mesh;
    const meshFail = wantMesh && meshStatus?.status === "failed";
    const hdFail = wantHd && hdStatus?.status === "failed";

    const primaryDone =
      (!wantHd && !wantMesh) ||
      meshFail ||
      (wantHd &&
        hdStatus != null &&
        (hdStatus.status === "completed" ||
          hdStatus.status === "failed")) ||
      (!wantHd &&
        wantMesh &&
        (meshStatus?.status === "completed" ||
          meshStatus?.status === "failed" ||
          meshStatus?.status === "partial"));

    if (!primaryDone) return;

    const marbleDone =
      !autoPost.marble ||
      (envGenStatus != null &&
        (envGenStatus.status === "completed" ||
          envGenStatus.status === "failed"));
    if (!marbleDone) return;

    const materialTerminal =
      materialStatus?.status === "completed" ||
      materialStatus?.status === "failed";

    let shouldDeploy = false;
    if (!autoPost.material) {
      shouldDeploy = true;
    } else if (
      materialTerminal &&
      materialAutoStartedRef.current === currentRunId
    ) {
      shouldDeploy = true;
    } else if (materialTerminal && autoPost.material) {
      shouldDeploy = true;
    } else if (hdFail || meshFail) {
      shouldDeploy = true;
    }

    if (!shouldDeploy) return;

    deployAutoDoneRef.current = currentRunId;
    void (async () => {
      if (!ueProject?.trim()) {
        setDeployMessage(
          "[자동] UE_PROJECT가 비어 있어 Deploy를 건너뜁니다. 설정에서 경로를 지정하세요.",
        );
        setScenePipelineBusy(false);
        setPipelineRunId(null);
        return;
      }
      await runDeployInternal({ vr: viewMode === "vr", auto: true });
      setScenePipelineBusy(false);
      setPipelineRunId(null);
    })();
  }, [
    autoPost.deploy,
    autoPost.material,
    autoPost.marble,
    scenePipelineBusy,
    pipelineRunId,
    currentRunId,
    autoPipeline.hd,
    autoPipeline.mesh,
    meshStatus,
    hdStatus,
    materialStatus,
    envGenStatus,
    ueProject,
    runDeployInternal,
    viewMode,
  ]);

  /** 자동 머티리얼만 켠 경우(Deploy 없음) 머티리얼 종료 시 busy 해제. */
  useEffect(() => {
    if (autoPost.deploy || !autoPost.material) return;
    if (!scenePipelineBusy || !pipelineRunId || currentRunId !== pipelineRunId)
      return;
    if (materialAutoStartedRef.current !== currentRunId) return;
    if (
      materialStatus?.status !== "completed" &&
      materialStatus?.status !== "failed"
    )
      return;
    if (autoPost.marble) {
      const md =
        envGenStatus?.status === "completed" ||
        envGenStatus?.status === "failed";
      if (!md) return;
    }
    setScenePipelineBusy(false);
    setPipelineRunId(null);
  }, [
    autoPost.deploy,
    autoPost.material,
    autoPost.marble,
    scenePipelineBusy,
    pipelineRunId,
    currentRunId,
    materialStatus?.status,
    envGenStatus?.status,
  ]);

  /** Marble만(머티리얼/Deploy 없음) 자동인 경우 완료 시 busy 해제. */
  useEffect(() => {
    if (autoPost.deploy || autoPost.material) return;
    if (!autoPost.marble) return;
    if (!scenePipelineBusy || !pipelineRunId || currentRunId !== pipelineRunId)
      return;
    if (
      envGenStatus?.status !== "completed" &&
      envGenStatus?.status !== "failed"
    )
      return;
    setScenePipelineBusy(false);
    setPipelineRunId(null);
  }, [
    autoPost.deploy,
    autoPost.material,
    autoPost.marble,
    scenePipelineBusy,
    pipelineRunId,
    currentRunId,
    envGenStatus?.status,
  ]);

  /** World Labs Marble envgen 상태 폴링. */
  useEffect(() => {
    if (!autoPost.marble || !currentRunId || envPollToken === 0) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const st = await pollEnvGenStatus(currentRunId);
        if (cancelled) return;
        setEnvGenStatus(st);
        if (st.status === "running") {
          timeoutId = setTimeout(tick, 5000);
        }
      } catch {
        if (!cancelled) {
          setEnvGenStatus((prev) =>
            prev ?? {
              status: "failed",
              error: "Marble 상태 폴링 실패",
            },
          );
        }
      }
    };

    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [currentRunId, envPollToken, autoPost.marble]);

  const handleHdGen = useCallback(async () => {
    if (!currentRunId) return;
    try {
      await startHdGen(currentRunId);
      setIsHdGenerating(true);
      setHdPollToken((t) => t + 1);
    } catch (e) {
      setHdStatus({
        status: "failed",
        phase: "error",
        total: 0,
        done: 0,
        modules: {},
        error: e instanceof Error ? e.message : "Failed",
      });
      setIsHdGenerating(false);
    }
  }, [currentRunId]);

  const handleMaterialEnhance = useCallback(
    async (style?: string, customPrompt?: string) => {
      if (!currentRunId) return;
      try {
        await startMaterialEnhance(currentRunId, {
          style,
          customPrompt: customPrompt || undefined,
        });
        setIsMaterialEnhancing(true);
        setMaterialPollToken((t) => t + 1);
      } catch (e) {
        setMaterialStatus({
          status: "failed",
          total: 0,
          done: 0,
          modules: {},
          error: e instanceof Error ? e.message : "Failed",
        });
        setIsMaterialEnhancing(false);
      }
    },
    [currentRunId],
  );

  const [modifyBusy, setModifyBusy] = useState(false);
  const [modifyResult, setModifyResult] = useState<{
    tier: string;
    summary: string;
  } | null>(null);

  const handleModify = useCallback(
    async (instruction: string) => {
      if (!currentRunId || !instruction.trim()) return;
      setModifyBusy(true);
      setModifyResult(null);
      try {
        const { sendModification, gltfUrl: gu } = await import("@/lib/api");
        const result = await sendModification(currentRunId, instruction);
        setModifyResult({ tier: result.tier, summary: result.summary });

        if (result.tier === "instant") {
          try {
            const specRes = await fetch(gu(`/api/outputs/${currentRunId}/set_spec.json`));
            if (specRes.ok) setCurrentSpec(await specRes.json());
          } catch { /* ignore */ }
        } else if (result.tier === "fast") {
          setIsMaterialEnhancing(true);
          setMaterialPollToken((t) => t + 1);
        } else if (result.tier === "moderate") {
          setIsMeshGenerating(true);
          setMeshPollToken((t) => t + 1);
        }
      } catch (e) {
        setModifyResult({
          tier: "error",
          summary: e instanceof Error ? e.message : "Modification failed",
        });
      } finally {
        setModifyBusy(false);
      }
    },
    [currentRunId],
  );

  const handleUeProjectChange = useCallback(async (path: string) => {
    const res = await updateConfig(path);
    setUeProject(res.ue_project);
  }, []);

  const handleViewportModulePick = useCallback((id: string | null) => {
    setSelectedModuleId((prev) => {
      if (id === null) return null;
      if (prev === id) return null;
      return id;
    });
  }, []);

  const handleGenerate = useCallback(
    async (prompt: string, be: string, mdl: string, maxModules?: number) => {
      setScenePipelineBusy(true);
      setPipelineRunId(null);
      setIsLoading(true);
      setError(null);
      setDeployMessage(null);
      setMeshStatus(null);
      setMeshGlbs({});
      setHdStatus(null);
      setMaterialStatus(null);
      setIsMaterialEnhancing(false);
      setEnvGenStatus(null);
      setEnvPollToken(0);
      materialAutoStartedRef.current = null;
      deployAutoDoneRef.current = null;
      autoMeshAfterGenerateRunIdRef.current = null;
      autoHdAfterMeshRunIdRef.current = null;
      try {
        const result: GenerateResult = await generate(
          prompt,
          be,
          mdl,
          maxModules,
        );
        setCurrentSpec(result.spec);
        setCurrentRunId(result.id);
        setCurrentGltf(gltfUrl(result.gltfUrl));
        fetchHistory().then(setHistory).catch(() => {});

        const followup = autoPipeline.mesh || autoPipeline.hd;
        const postOnly =
          !followup &&
          (autoPost.marble || autoPost.material || autoPost.deploy);
        if (!followup && !postOnly) {
          setScenePipelineBusy(false);
          setPipelineRunId(null);
        } else {
          setPipelineRunId(result.id);
        }

        if (autoPipeline.mesh) {
          autoMeshAfterGenerateRunIdRef.current = result.id;
          try {
            await startMeshGen(result.id);
            setMeshPollToken((t) => t + 1);
          } catch (e) {
            autoMeshAfterGenerateRunIdRef.current = null;
            if (!autoPost.marble) {
              setScenePipelineBusy(false);
              setPipelineRunId(null);
            }
            setMeshStatus({
              status: "failed",
              total: 0,
              done: 0,
              modules: {},
              error:
                e instanceof Error ? e.message : "Auto mesh generation failed",
            });
            setIsMeshGenerating(false);
          }
        } else if (autoPipeline.hd) {
          /* 스펙만 두고 일반 메시 없이 곧바로 참조 이미지 → Rodin HD */
          try {
            await startHdGen(result.id);
            setIsHdGenerating(true);
            setHdPollToken((t) => t + 1);
          } catch (e) {
            if (!autoPost.marble) {
              setScenePipelineBusy(false);
              setPipelineRunId(null);
            }
            setHdStatus({
              status: "failed",
              phase: "error",
              total: 0,
              done: 0,
              modules: {},
              error:
                e instanceof Error ? e.message : "Auto HD failed to start",
            });
            setIsHdGenerating(false);
          }
        }

        if (autoPost.marble) {
          try {
            const ev = await startEnvGen(result.id);
            setEnvGenStatus(ev);
            setEnvPollToken((t) => t + 1);
          } catch (e) {
            setEnvGenStatus({
              status: "failed",
              error:
                e instanceof Error
                  ? e.message
                  : "Marble 환경 생성 시작 실패",
            });
          }
        }
      } catch (e) {
        setScenePipelineBusy(false);
        setPipelineRunId(null);
        const msg = e instanceof Error ? e.message : "Unknown error";
        setError(msg);
        throw e;
      } finally {
        setIsLoading(false);
      }
    },
    [autoPipeline.mesh, autoPipeline.hd, autoPost],
  );

  const handleRefine = useCallback(
    async (instruction: string) => {
      if (!currentRunId) return;
      setIsLoading(true);
      setError(null);
      setDeployMessage(null);
      setHdStatus(null);
      try {
        const result: GenerateResult = selectedModuleId
          ? await refineModule(
              currentRunId,
              selectedModuleId,
              instruction,
              backend,
              model,
            )
          : await refine(currentRunId, instruction, backend, model);
        setCurrentSpec(result.spec);
        setCurrentRunId(result.id);
        setCurrentGltf(gltfUrl(result.gltfUrl));
        setMeshPollToken((t) => t + 1);
        fetchHistory().then(setHistory).catch(() => {});
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setIsLoading(false);
      }
    },
    [currentRunId, backend, model, selectedModuleId]
  );

  const handleSaveViewerEdits = useCallback(async () => {
    if (!currentRunId) return;
    setIsSavingEdits(true);
    setSaveEditMessage(null);
    try {
      const res = await saveViewerEdits(currentRunId, perModuleGlbExtraDeg);
      setCurrentSpec((prev) =>
        prev
          ? {
              ...prev,
              per_module_glb_extra_deg: { ...perModuleGlbExtraDeg },
            }
          : null,
      );
      setSaveEditMessage(
        `저장됨 · set_spec.json (${res.modules_with_delta}개 모듈에 Δ)`,
      );
    } catch (e) {
      setSaveEditMessage(
        e instanceof Error ? e.message : "저장 실패",
      );
    } finally {
      setIsSavingEdits(false);
    }
  }, [currentRunId, perModuleGlbExtraDeg]);

  const handleDeploy = useCallback(
    async (vr: boolean) => {
      if (!currentRunId) return;
      await runDeployInternal({ vr, auto: false });
    },
    [currentRunId, runDeployInternal],
  );

  const handleMeshGen = useCallback(async (onlyModuleIds?: string[]) => {
    if (!currentRunId) return;
    try {
      // Regenerating overwrites the same <id>.glb on disk; bust the URL so drei
      // refetches instead of returning the stale cached mesh.
      if (onlyModuleIds?.length) {
        const t = Date.now();
        for (const id of onlyModuleIds) {
          meshGlbCopyBustRef.current[id] = t;
        }
      }
      await startMeshGen(
        currentRunId,
        onlyModuleIds?.length ? { moduleIds: onlyModuleIds } : undefined,
      );
      setMeshPollToken((t) => t + 1);
    } catch (e) {
      setMeshStatus({
        status: "failed",
        total: 0,
        done: 0,
        modules: {},
        error: e instanceof Error ? e.message : "Failed",
      });
      setIsMeshGenerating(false);
    }
  }, [currentRunId]);

  const handleHistorySelect = useCallback((item: HistoryItem) => {
    setCurrentRunId(item.id);
    setCurrentGltf(gltfUrl(item.gltfUrl));
    setCurrentSpec(null);
    setDeployMessage(null);
    setMeshStatus(null);
    setMeshGlbs({});
    setHdStatus(null);
    setMaterialStatus(null);
    setEnvGenStatus(null);
    setEnvPollToken(0);

    fetch(gltfUrl(`/api/outputs/${item.id}/set_spec.json`))
      .then((r) => r.json())
      .then((spec) => setCurrentSpec(spec))
      .catch(() => {});
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-[#1e1e2e] bg-[#0c0c14]/80 backdrop-blur shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-sm font-semibold tracking-wide text-[#c0c0d0]">
            SetLab
            <span className="ml-2 text-xs font-normal text-[#555]">
              Prompt to Viewport
            </span>
          </h1>
          <div className="flex items-center gap-0.5 bg-[#16161e] rounded-lg p-0.5">
            <button
              onClick={() => setViewMode("3d")}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                viewMode === "3d"
                  ? "bg-[#2a2a3e] text-white"
                  : "text-[#666] hover:text-[#999]"
              }`}
            >
              3D
            </button>
            <button
              onClick={() => setViewMode("vr")}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                viewMode === "vr"
                  ? "bg-violet-600 text-white"
                  : "text-[#666] hover:text-[#999]"
              }`}
            >
              VR
            </button>
          </div>
        </div>
        <SettingsPanel
          backend={backend}
          model={model}
          ueProject={ueProject}
          onBackendChange={handleBackendChange}
          onModelChange={setModel}
          onUeProjectChange={handleUeProjectChange}
        />
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* History sidebar */}
        <aside className="w-56 shrink-0 border-r border-[#1e1e2e] bg-[#0e0e18] p-3 overflow-y-auto flex flex-col gap-2">
          <p className="text-xs font-medium text-[#666] uppercase tracking-wider">
            History
          </p>
          <HistoryPanel
            items={history}
            activeId={currentRunId}
            onSelect={handleHistorySelect}
          />
        </aside>

        {/* Main area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Viewport */}
          <div className="flex-1 min-h-0 p-3 pb-0">
            {viewMode === "vr" ? (
              <VRViewer
                key={currentGltf ?? "empty"}
                gltfUrl={currentGltf}
                spec={currentSpec}
                meshGlbs={meshGlbs}
                meshedOnly={meshedOnlyView}
                meshGlbExtraDeg={meshGlbExtraDeg}
                perModuleGlbExtraDeg={perModuleGlbExtraDeg}
                selectedModuleId={selectedModuleId}
                onViewportSelectModuleId={handleViewportModulePick}
              />
            ) : (
              <Viewer3D
                key={currentGltf ?? "empty"}
                gltfUrl={currentGltf}
                spec={currentSpec}
                meshGlbs={meshGlbs}
                meshedOnly={meshedOnlyView}
                meshGlbExtraDeg={meshGlbExtraDeg}
                perModuleGlbExtraDeg={perModuleGlbExtraDeg}
                selectedModuleId={selectedModuleId}
                onViewportSelectModuleId={handleViewportModulePick}
              />
            )}
          </div>

          {/* Prompt bar */}
          <div className="shrink-0 p-3 space-y-2">
            {error && (
              <p className="text-xs text-red-400 bg-red-950/30 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <ScenePipelineBanner
              active={scenePipelineBusy}
              isLayoutGenerating={isLoading && scenePipelineBusy}
              autoMesh={autoPipeline.mesh}
              autoHd={autoPipeline.hd}
              meshStatus={meshStatus}
              hdStatus={hdStatus}
              autoMaterial={autoPost.material}
              autoDeploy={autoPost.deploy}
              autoMarble={autoPost.marble}
              envGenStatus={envGenStatus}
              isMaterialEnhancing={isMaterialEnhancing}
              materialStatus={materialStatus}
              isDeploying={isDeploying}
            />
            <PromptPanel
              onGenerate={handleGenerate}
              onRefine={handleRefine}
              isLoading={isLoading}
              fullPipelineBusy={scenePipelineBusy}
              backend={backend}
              model={model}
              hasCurrentSpec={!!currentSpec}
              selectedModuleId={selectedModuleId}
            />
          </div>
        </main>

        {/* Spec sidebar */}
        <aside className="w-72 shrink-0 border-l border-[#1e1e2e] bg-[#0e0e18] p-3">
          <SpecPanel
            spec={currentSpec}
            runId={currentRunId}
            onDeploy={handleDeploy}
            isDeploying={isDeploying}
            deployMessage={deployMessage}
            viewMode={viewMode}
            meshStatus={meshStatus}
            onGenerateMeshes={handleMeshGen}
            isMeshGenerating={isMeshGenerating}
            meshedOnlyView={meshedOnlyView}
            onMeshedOnlyViewChange={setMeshedOnlyView}
            meshedGlbCount={Object.keys(meshGlbs).length}
            hdStatus={hdStatus}
            onGenerateHd={handleHdGen}
            isHdGenerating={isHdGenerating}
            glbModuleIds={Object.keys(meshGlbs)}
            selectedModuleId={selectedModuleId}
            onSelectedModuleIdChange={setSelectedModuleId}
            perModuleGlbExtraDeg={perModuleGlbExtraDeg}
            onPerModuleGlbExtraDegChange={handlePerModuleGlbExtraDeg}
            onSaveViewerEdits={handleSaveViewerEdits}
            isSavingEdits={isSavingEdits}
            saveEditMessage={saveEditMessage}
            onMeshGlbCopied={handleMeshGlbCopied}
            materialStatus={materialStatus}
            onMaterialEnhance={handleMaterialEnhance}
            isMaterialEnhancing={isMaterialEnhancing}
            onModify={handleModify}
            isModifying={modifyBusy}
            modifyResult={modifyResult}
          />
        </aside>
      </div>
    </div>
  );
}
