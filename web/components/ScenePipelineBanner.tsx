"use client";

import type {
  MeshGenStatus,
  HdGenStatus,
  MaterialEnhanceStatus,
  EnvGenStatus,
} from "@/lib/api";

function hdPhaseLabel(phase: string): string {
  switch (phase) {
    case "starting":
      return "HD 파이프라인 시작";
    case "images":
      return "참고 이미지 (FLUX)";
    case "3d":
      return "HD 메시 (Rodin)";
    default:
      return phase;
  }
}

export interface ScenePipelineBannerProps {
  active: boolean;
  /** True while the layout/spec HTTP request is in flight (New Scene only). */
  isLayoutGenerating: boolean;
  autoMesh: boolean;
  autoHd: boolean;
  meshStatus: MeshGenStatus | null;
  hdStatus: HdGenStatus | null;
  /** 자동 머티리얼 향상(rodin_texture_only) */
  autoMaterial?: boolean;
  /** 자동 UE Deploy */
  autoDeploy?: boolean;
  isMaterialEnhancing?: boolean;
  materialStatus?: MaterialEnhanceStatus | null;
  isDeploying?: boolean;
  /** World Labs Marble (원경) */
  autoMarble?: boolean;
  envGenStatus?: EnvGenStatus | null;
}

export default function ScenePipelineBanner({
  active,
  isLayoutGenerating,
  autoMesh,
  autoHd,
  meshStatus,
  hdStatus,
  autoMaterial = false,
  autoDeploy = false,
  isMaterialEnhancing = false,
  materialStatus = null,
  isDeploying = false,
  autoMarble = false,
  envGenStatus = null,
}: ScenePipelineBannerProps) {
  if (!active) return null;

  const meshRunning = Boolean(autoMesh && meshStatus?.status === "running");
  const meshFrac =
    meshStatus && meshStatus.total > 0
      ? Math.min(1, meshStatus.done / meshStatus.total)
      : 0;

  const hdRunning = Boolean(autoHd && hdStatus?.status === "running");
  const hdFrac =
    hdStatus && hdStatus.total > 0
      ? Math.min(1, hdStatus.done / hdStatus.total)
      : 0;

  const matRunning = Boolean(
    autoMaterial && materialStatus?.status === "running",
  );
  const matFrac =
    materialStatus && materialStatus.total > 0
      ? Math.min(1, materialStatus.done / materialStatus.total)
      : 0;

  let title = "씬 파이프라인";
  let subtitle: string | null = "진행 중…";
  let barFrac: number | null = null;

  if (isLayoutGenerating) {
    title = "레이아웃 · 스펙 생성";
    subtitle = "LLM이 JSON 모듈 배치를 만드는 중입니다.";
  } else if (meshRunning && meshStatus) {
    title = "3D 메시 (Rodin)";
    subtitle = `모듈 ${meshStatus.done} / ${meshStatus.total}`;
    barFrac = meshFrac;
  } else if (hdRunning && hdStatus) {
    title = "HD 파이프라인";
    subtitle = `${hdPhaseLabel(hdStatus.phase)} · ${hdStatus.done} / ${hdStatus.total}`;
    barFrac = hdFrac;
  } else if (
    autoHd &&
    hdStatus == null &&
    !isLayoutGenerating &&
    !meshRunning
  ) {
    title = "HD 파이프라인";
    subtitle = "HD 작업을 연결하는 중…";
  } else if (autoMesh && !autoHd && meshStatus && meshStatus.status !== "running") {
    title = "3D 메시 (Rodin)";
    subtitle = "마무리 중…";
  } else if (autoMarble && envGenStatus?.status === "running") {
    title = "원경 · Marble (World Labs)";
    const p = envGenStatus.progress;
    subtitle =
      envGenStatus.phase != null
        ? `${envGenStatus.phase}${typeof p === "number" ? ` · ${p}%` : ""}`
        : "환경 메시 생성 중…";
    barFrac =
      typeof p === "number" && Number.isFinite(p)
        ? Math.min(1, Math.max(0, p / 100))
        : null;
  } else if (matRunning && materialStatus) {
    title = "머티리얼 향상 (Rodin)";
    subtitle = `모듈 ${materialStatus.done} / ${materialStatus.total}`;
    barFrac = matFrac;
  } else if (autoMaterial && isMaterialEnhancing && !materialStatus) {
    title = "머티리얼 향상 (Rodin)";
    subtitle = "작업을 시작하는 중…";
  } else if (autoDeploy && isDeploying) {
    title = "UE Deploy";
    subtitle = "Content/Incoming · Saved/SetLab 로 복사 중…";
  }

  const err =
    meshStatus?.status === "failed"
      ? meshStatus.error ?? "메시 생성 실패"
      : hdStatus?.status === "failed"
        ? hdStatus.error ?? "HD 실패"
        : materialStatus?.status === "failed"
          ? materialStatus.error ?? "머티리얼 향상 실패"
          : envGenStatus?.status === "failed"
            ? envGenStatus.error ?? "Marble 환경 생성 실패"
            : null;

  return (
    <div
      className="rounded-lg border border-[#2e3d6e]/80 bg-gradient-to-r from-[#14182a] to-[#12121c] px-3 py-2.5 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 min-h-[1.25rem]">
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#6b8cff] opacity-40" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-[#4f6df5]" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-[#d8dcff] tracking-wide">
            {title}
          </p>
          {subtitle && (
            <p className="text-[11px] text-[#8b93b8] mt-0.5 truncate">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {barFrac != null && (
        <div className="mt-2 h-1.5 rounded-full bg-[#1a1f2e] overflow-hidden">
          <div
            className="h-full rounded-full bg-[#4f6df5] transition-[width] duration-500 ease-out"
            style={{ width: `${Math.round(barFrac * 100)}%` }}
          />
        </div>
      )}
      {err && (
        <p className="text-[11px] text-red-400 mt-2 leading-snug">{err}</p>
      )}
    </div>
  );
}
