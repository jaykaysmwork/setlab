"use client";

import { useEffect, useState } from "react";
import {
  copyMeshGlb,
  type MeshGenStatus,
  type SetSpec,
  type HdGenStatus,
  type MaterialEnhanceStatus,
} from "@/lib/api";

interface Props {
  spec: SetSpec | null;
  runId: string | null;
  onDeploy: (vr: boolean) => void;
  isDeploying: boolean;
  deployMessage: string | null;
  viewMode: "3d" | "vr";
  meshStatus: MeshGenStatus | null;
  /** Omit ids = missing modules only; pass one id to regenerate that module only (overwrites GLB). */
  onGenerateMeshes: (onlyModuleIds?: string[]) => void;
  isMeshGenerating: boolean;
  meshedOnlyView: boolean;
  onMeshedOnlyViewChange: (value: boolean) => void;
  meshedGlbCount: number;
  hdStatus: HdGenStatus | null;
  onGenerateHd: () => void;
  isHdGenerating: boolean;
  glbModuleIds: string[];
  selectedModuleId: string | null;
  onSelectedModuleIdChange: (id: string | null) => void;
  perModuleGlbExtraDeg: Record<string, [number, number, number]>;
  onPerModuleGlbExtraDegChange: (
    moduleId: string,
    next: [number, number, number],
  ) => void;
  onSaveViewerEdits: () => void;
  isSavingEdits: boolean;
  saveEditMessage: string | null;
  onMeshGlbCopied?: (toModuleId: string) => void;
  materialStatus: MaterialEnhanceStatus | null;
  onMaterialEnhance: (style?: string, customPrompt?: string) => void;
  isMaterialEnhancing: boolean;
  onModify: (instruction: string) => void;
  isModifying: boolean;
  modifyResult: { tier: string; summary: string } | null;
}

export default function SpecPanel({
  spec,
  runId,
  onDeploy,
  isDeploying,
  deployMessage,
  viewMode,
  meshStatus,
  onGenerateMeshes,
  isMeshGenerating,
  meshedOnlyView,
  onMeshedOnlyViewChange,
  meshedGlbCount,
  hdStatus,
  onGenerateHd,
  isHdGenerating,
  glbModuleIds,
  selectedModuleId,
  onSelectedModuleIdChange,
  perModuleGlbExtraDeg,
  onPerModuleGlbExtraDegChange,
  onSaveViewerEdits,
  isSavingEdits,
  saveEditMessage,
  onMeshGlbCopied,
  materialStatus,
  onMaterialEnhance,
  isMaterialEnhancing,
  onModify,
  isModifying,
  modifyResult,
}: Props) {
  const [copyMeshSourceId, setCopyMeshSourceId] = useState<string>("");
  const [copyMeshBusy, setCopyMeshBusy] = useState(false);
  const [copyMeshMsg, setCopyMeshMsg] = useState<string | null>(null);
  const [matStyle, setMatStyle] = useState("generic_weathered");
  const [modifyInput, setModifyInput] = useState("");
  useEffect(() => {
    if (!selectedModuleId) return;
    const el = document.querySelector(
      `[data-setlab-module="${CSS.escape(selectedModuleId)}"]`,
    );
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedModuleId]);

  if (!spec) {
    return (
      <div className="h-full flex items-center justify-center text-[#555] text-sm">
        Generate a set to see its specification here.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-[#e0e0e8]">{spec.title}</h3>
          {spec.era_style && (
            <span className="text-xs text-[#888]">{spec.era_style}</span>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex gap-1">
            <button
              type="button"
              onClick={onSaveViewerEdits}
              disabled={!runId || isSavingEdits}
              className="px-2.5 py-1.5 bg-[#2a2a3e] hover:bg-[#3a3a4e] disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-xs font-medium text-[#ccc] transition-colors"
              title="모듈별 Δ 회전을 out/&lt;run&gt;/set_spec.json 에 저장"
            >
              {isSavingEdits ? "저장 중…" : "수정 저장"}
            </button>
            <button
              onClick={() => onDeploy(viewMode === "vr")}
              disabled={!runId || isDeploying}
              className={`px-2.5 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-xs font-medium transition-colors ${
                viewMode === "vr"
                  ? "bg-violet-600 hover:bg-violet-500"
                  : "bg-emerald-600 hover:bg-emerald-500"
              }`}
              title={
                viewMode === "vr"
                  ? "Deploy to Unreal with VR Preview"
                  : "Copy glTF to Unreal project"
              }
            >
              {isDeploying
                ? "Deploying…"
                : viewMode === "vr"
                  ? "Deploy (VR)"
                  : "Deploy"}
            </button>
          </div>
          {saveEditMessage && (
            <p className="text-[10px] text-[#888] max-w-[11rem] text-right leading-tight">
              {saveEditMessage}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onGenerateMeshes()}
            disabled={!runId || isMeshGenerating || meshStatus?.status === "completed"}
            className={`flex-1 min-w-0 px-3 py-1.5 ${
              meshStatus?.status === "partial"
                ? "bg-amber-600 hover:bg-amber-500"
                : "bg-indigo-600 hover:bg-indigo-500"
            } disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-xs font-medium transition-colors`}
          >
            {isMeshGenerating
              ? `Generating 3D… (${meshStatus?.done ?? 0}/${meshStatus?.total ?? 0})`
              : meshStatus?.status === "completed"
                ? "3D Models Ready"
                : meshStatus?.status === "partial"
                  ? `Generate Missing 3D (${(meshStatus.total ?? 0) - (meshStatus.done ?? 0)})`
                  : "Generate 3D Models"}
          </button>
        </div>
        {selectedModuleId && (
          <button
            type="button"
            onClick={() => onGenerateMeshes([selectedModuleId])}
            disabled={!runId || isMeshGenerating}
            title="Rodin 텍스트→3D만 이 모듈에 대해 다시 돌립니다. 기존 GLB를 덮어씁니다."
            className="w-full px-3 py-1.5 bg-[#2a2a4e] hover:bg-[#3a3a5e] disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-[11px] font-medium text-[#c8c8e0] border border-[#3e3e5e] transition-colors"
          >
            선택 모듈만 재생성 ·{" "}
            <span className="font-mono text-[#a8b0ff]">{selectedModuleId}</span>
          </button>
        )}
      </div>

      <label className="flex items-center gap-2 text-xs text-[#aaa] cursor-pointer select-none">
        <input
          type="checkbox"
          checked={meshedOnlyView}
          onChange={(e) => onMeshedOnlyViewChange(e.target.checked)}
          className="rounded border-[#444] bg-[#16161e] text-indigo-500 focus:ring-indigo-500/40"
        />
        <span>완료된 3D만 표시 (박스 숨김)</span>
      </label>
      {meshedOnlyView && meshedGlbCount === 0 && (
        <p className="text-[11px] text-amber-400/90 leading-snug">
          브라우저에 로드된 GLB가 없어 필터가 적용되지 않았습니다. 새로고침 후
          히스토리에서 이 씬을 다시 선택하거나 Generate 3D를 완료한 뒤
          다시 시도하세요.
        </p>
      )}
      {meshedOnlyView && meshedGlbCount > 0 && (
        <p className="text-[11px] text-[#666]">
          GLB {meshedGlbCount}개만 표시 · 나머지 박스는 숨김
        </p>
      )}

      {meshStatus && (
        <div className="space-y-1">
          <div className="h-1.5 bg-[#16161e] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                meshStatus.status === "failed" ? "bg-red-500"
                  : meshStatus.status === "partial" ? "bg-amber-500"
                  : "bg-indigo-500"
              }`}
              style={{
                width: `${meshStatus.total > 0 ? (meshStatus.done / meshStatus.total) * 100 : 0}%`,
              }}
            />
          </div>
          {meshStatus.status === "failed" && meshStatus.error && (
            <p className="text-xs text-red-400">{meshStatus.error}</p>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={onGenerateHd}
          disabled={!runId || isHdGenerating || hdStatus?.status === "completed"}
          className="flex-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-xs font-medium transition-colors"
        >
          {isHdGenerating
            ? `Generating HD… (${hdStatus?.done ?? 0}/${hdStatus?.total ?? 0})`
            : hdStatus?.status === "completed"
              ? "HD 3D Ready"
              : "Generate HD 3D"}
        </button>
      </div>
      {isHdGenerating && hdStatus?.phase && (
        <p className="text-[11px] text-[#888]">
          {hdStatus.phase === "images" ? "이미지 생성 중 (FLUX)" : hdStatus.phase === "3d" ? "3D 변환 중 (Rodin Gen-2)" : hdStatus.phase}
        </p>
      )}
      {hdStatus && (
        <div className="space-y-1">
          <div className="h-1.5 bg-[#16161e] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                hdStatus.status === "failed" ? "bg-red-500" : "bg-amber-500"
              }`}
              style={{
                width: `${hdStatus.total > 0 ? (hdStatus.done / hdStatus.total) * 100 : 0}%`,
              }}
            />
          </div>
          {hdStatus.status === "failed" && hdStatus.error && (
            <p className="text-xs text-red-400">{hdStatus.error}</p>
          )}
        </div>
      )}

      {meshedGlbCount > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <select
              value={matStyle}
              onChange={(e) => setMatStyle(e.target.value)}
              disabled={isMaterialEnhancing}
              className="flex-1 min-w-0 text-[11px] bg-[#0e0e18] border border-[#444] rounded px-1.5 py-1.5 text-[#ccc] disabled:opacity-40"
            >
              <option value="generic_weathered">Generic Weathered</option>
              <option value="medieval_stone">Medieval Stone</option>
              <option value="aged_wood">Aged Wood</option>
              <option value="rusty_metal">Rusty Metal</option>
              <option value="worn_brick">Worn Brick</option>
            </select>
            <button
              type="button"
              onClick={() => onMaterialEnhance(matStyle)}
              disabled={!runId || isMaterialEnhancing || materialStatus?.status === "completed"}
              className="shrink-0 px-3 py-1.5 bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-xs font-medium transition-colors"
            >
              {isMaterialEnhancing
                ? `Enhancing… (${materialStatus?.done ?? 0}/${materialStatus?.total ?? 0})`
                : materialStatus?.status === "completed"
                  ? "Materials Enhanced"
                  : "Enhance Materials"}
            </button>
          </div>
          {materialStatus && (
            <div className="space-y-1">
              <div className="h-1.5 bg-[#16161e] rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    materialStatus.status === "failed" ? "bg-red-500" : "bg-teal-500"
                  }`}
                  style={{
                    width: `${materialStatus.total > 0 ? (materialStatus.done / materialStatus.total) * 100 : 0}%`,
                  }}
                />
              </div>
              {materialStatus.status === "failed" && materialStatus.error && (
                <p className="text-xs text-red-400">{materialStatus.error}</p>
              )}
            </div>
          )}
        </div>
      )}

      {meshedGlbCount > 0 && selectedModuleId && (
        <div className="space-y-2 p-2 rounded-md bg-[#16161e] border border-sky-900/50">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-medium text-sky-300/90">
              선택 모듈 추가 회전 Δ (°)
            </p>
            <button
              type="button"
              onClick={() => onSelectedModuleIdChange(null)}
              className="text-[10px] text-[#888] hover:text-[#ccc] shrink-0"
            >
              선택 해제
            </button>
          </div>
          <p className="text-[10px] font-mono text-[#888]">{selectedModuleId}</p>
          {(() => {
            const cur = perModuleGlbExtraDeg[selectedModuleId] ?? [0, 0, 0];
            const setTri = (next: [number, number, number]) =>
              onPerModuleGlbExtraDegChange(selectedModuleId, next);
            return (
              <>
                <div className="flex flex-wrap gap-x-3 gap-y-1.5 items-center text-[11px] text-[#ccc]">
                  {(["ΔRX", "ΔRY", "ΔRZ"] as const).map((label, i) => (
                    <label key={label} className="flex items-center gap-1 font-mono">
                      {label}
                      <input
                        type="number"
                        step={15}
                        value={cur[i]}
                        onChange={(e) => {
                          const v = parseFloat(e.target.value);
                          const n = Number.isFinite(v) ? v : 0;
                          const next: [number, number, number] = [
                            cur[0],
                            cur[1],
                            cur[2],
                          ];
                          next[i] = n;
                          setTri(next);
                        }}
                        className="w-[3.25rem] bg-[#0e0e18] border border-[#444] rounded px-1 py-0.5 text-[#e0e0e8]"
                      />
                    </label>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1">
                  {[-45, 45, -90, 90].map((deg) => (
                    <button
                      key={deg}
                      type="button"
                      onClick={() =>
                        setTri([cur[0], cur[1] + deg, cur[2]])
                      }
                      className="px-2 py-0.5 rounded text-[10px] bg-[#1a3a4e] hover:bg-[#2a4a5e] text-[#ccc]"
                    >
                      RY {deg > 0 ? "+" : ""}
                      {deg}°
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      onPerModuleGlbExtraDegChange(selectedModuleId, [0, 0, 0])
                    }
                    className="px-2 py-0.5 rounded text-[10px] bg-[#2a2a3e] hover:bg-[#3a3a4e] text-[#aaa]"
                  >
                    Δ 초기화
                  </button>
                </div>
                {onMeshGlbCopied && runId && glbModuleIds.length > 1 && (
                  <div className="pt-2 mt-2 border-t border-[#2a2a3a] space-y-1.5">
                    <p className="text-[10px] text-[#888] leading-snug">
                      API 재생성 없이 디스크에서 같은 GLB 파일을 덮어씁니다(바이트 동일).
                    </p>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <select
                        value={copyMeshSourceId}
                        onChange={(e) => {
                          setCopyMeshSourceId(e.target.value);
                          setCopyMeshMsg(null);
                        }}
                        className="flex-1 min-w-[8rem] text-[10px] bg-[#0e0e18] border border-[#444] rounded px-1.5 py-1 text-[#ccc]"
                      >
                        <option value="">원본 모듈 (GLB)</option>
                        {glbModuleIds
                          .filter((id) => id !== selectedModuleId)
                          .map((id) => (
                            <option key={id} value={id}>
                              {id}
                            </option>
                          ))}
                      </select>
                      <button
                        type="button"
                        disabled={
                          !copyMeshSourceId ||
                          copyMeshBusy ||
                          !runId
                        }
                        onClick={async () => {
                          if (
                            !runId ||
                            !copyMeshSourceId ||
                            !onMeshGlbCopied
                          )
                            return;
                          setCopyMeshBusy(true);
                          setCopyMeshMsg(null);
                          try {
                            await copyMeshGlb(
                              runId,
                              copyMeshSourceId,
                              selectedModuleId,
                            );
                            onMeshGlbCopied(selectedModuleId);
                            setCopyMeshMsg("복사됨 · 뷰 갱신됨");
                          } catch (e) {
                            setCopyMeshMsg(
                              e instanceof Error ? e.message : "복사 실패",
                            );
                          } finally {
                            setCopyMeshBusy(false);
                          }
                        }}
                        className="px-2 py-1 rounded text-[10px] bg-[#3d5a40] hover:bg-[#4d6a50] disabled:opacity-40 text-[#e0e8e0]"
                      >
                        {copyMeshBusy ? "…" : "GLB 복사"}
                      </button>
                    </div>
                    {copyMeshMsg && (
                      <p
                        className={`text-[10px] ${copyMeshMsg.startsWith("복사") ? "text-emerald-400/90" : "text-red-400/90"}`}
                      >
                        {copyMeshMsg}
                      </p>
                    )}
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {spec && runId && (
        <div className="space-y-1.5 p-2 rounded-md bg-[#12121e] border border-[#2a2a3e]">
          <p className="text-[11px] font-medium text-orange-300/90">
            실시간 수정 (Director Prompt)
          </p>
          <div className="flex gap-1.5">
            <input
              type="text"
              value={modifyInput}
              onChange={(e) => setModifyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !isModifying && modifyInput.trim()) {
                  onModify(modifyInput.trim());
                }
              }}
              placeholder="예: 조명을 노을로 바꿔줘"
              disabled={isModifying}
              className="flex-1 min-w-0 text-[11px] bg-[#0e0e18] border border-[#444] rounded px-2 py-1.5 text-[#ccc] placeholder-[#555] disabled:opacity-40"
            />
            <button
              type="button"
              onClick={() => {
                if (modifyInput.trim()) onModify(modifyInput.trim());
              }}
              disabled={isModifying || !modifyInput.trim()}
              className="shrink-0 px-2.5 py-1.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-md text-[11px] font-medium transition-colors"
            >
              {isModifying ? "분석 중…" : "적용"}
            </button>
          </div>
          {modifyResult && (
            <p
              className={`text-[10px] leading-snug ${
                modifyResult.tier === "error"
                  ? "text-red-400"
                  : modifyResult.tier === "instant"
                    ? "text-emerald-400"
                    : modifyResult.tier === "fast"
                      ? "text-amber-400"
                      : "text-sky-400"
              }`}
            >
              <span className="font-medium uppercase">[{modifyResult.tier}]</span>{" "}
              {modifyResult.summary}
            </p>
          )}
        </div>
      )}

      {deployMessage && (
        <p className="text-xs px-2 py-1 rounded bg-[#1a2a1a] text-emerald-400">
          {deployMessage}
        </p>
      )}

      {spec.notes && (
        <p className="text-xs text-[#999] italic">{spec.notes}</p>
      )}

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        <p className="text-xs font-medium text-[#888] uppercase tracking-wider">
          Modules ({spec.modules.length})
        </p>
        {spec.modules.map((m, i) => {
          const hasGlb = glbModuleIds.includes(m.id);
          const delta = perModuleGlbExtraDeg[m.id];
          const hasDelta =
            !!delta && (delta[0] !== 0 || delta[1] !== 0 || delta[2] !== 0);
          return (
          <button
            type="button"
            key={`${i}-${m.id}`}
            data-setlab-module={m.id}
            onClick={() =>
              onSelectedModuleIdChange(
                selectedModuleId === m.id ? null : m.id,
              )
            }
            className={`w-full text-left p-2 bg-[#16161e] rounded-md text-xs space-y-0.5 border transition-colors ${
              selectedModuleId === m.id
                ? "border-sky-500/70 ring-1 ring-sky-500/30"
                : "border-transparent hover:border-[#333]"
            }`}
          >
            <div className="flex justify-between items-center">
              <span className="font-medium text-[#c0c0d0]">{m.id}</span>
              <span className="flex items-center gap-1.5">
                {(() => {
                  const st = meshStatus?.modules?.[m.id];
                  const cls =
                    st === "done"
                      ? "bg-emerald-400"
                      : st === "generating" || st === "queued"
                        ? "bg-amber-400 animate-pulse"
                        : st === "failed"
                          ? "bg-red-400"
                          : st === "pending"
                            ? "bg-[#555]"
                            : "bg-[#3a3a44] opacity-70";
                  const title = st
                    ? String(st)
                    : "3D not started (Generate 3D Models)";
                  return (
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${cls}`}
                      title={title}
                    />
                  );
                })()}
                <span className="text-[#666] font-mono">{m.asset}</span>
                {hasGlb && (
                  <span className="text-[9px] text-emerald-500/90 font-medium">
                    GLB
                  </span>
                )}
              </span>
            </div>
            <div className="text-[#555] font-mono text-[11px] flex flex-wrap gap-x-3 gap-y-0.5">
              <span>pos [{m.position.map((v) => v.toFixed(1)).join(", ")}]</span>
              <span>
                rot [{m.rotation_deg.map((v) => v.toFixed(0)).join(", ")}]
              </span>
              <span>
                scl [{m.scale.map((v) => v.toFixed(1)).join(", ")}]
              </span>
              {hasDelta && (
                <span className="text-sky-400/90">
                  Δ[{delta!.map((v) => v.toFixed(0)).join(", ")}]
                </span>
              )}
            </div>
          </button>
          );
        })}
      </div>
    </div>
  );
}
