"use client";

import { useState, useCallback, useEffect, useRef, type FormEvent } from "react";
import { enhancePrompt, searchImages, type SearchImageItem } from "@/lib/api";
import { CLAUDE_SONNET, CLAUDE_HAIKU } from "@/lib/models";
import ImagePickerPanel from "./ImagePickerPanel";

interface Props {
  onGenerate: (
    prompt: string,
    backend: string,
    model: string,
    maxModules?: number,
  ) => Promise<void>;
  onRefine: (instruction: string) => Promise<void>;
  isLoading: boolean;
  /** New Scene: true while auto mesh / HD still running after layout returns. */
  fullPipelineBusy?: boolean;
  backend: string;
  model: string;
  hasCurrentSpec: boolean;
  /** When set, + Add / Modify applies the prompt to this module only. */
  selectedModuleId?: string | null;
}

type EnhanceStage = "idle" | "searching" | "picking" | "enhancing";

export default function PromptPanel({
  onGenerate,
  onRefine,
  isLoading,
  fullPipelineBusy = false,
  backend,
  model,
  hasCurrentSpec,
  selectedModuleId = null,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<"generate" | "refine">("generate");
  const [enhancedOnce, setEnhancedOnce] = useState(false);
  const [enhanceError, setEnhanceError] = useState<string | null>(null);
  const [maxModulesInput, setMaxModulesInput] = useState("");
  const [maxModulesError, setMaxModulesError] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState("");
  const loadingStepRef = useRef(0);

  // Enhance flow state machine
  const [enhanceStage, setEnhanceStage] = useState<EnhanceStage>("idle");
  const [pickerImages, setPickerImages] = useState<SearchImageItem[]>([]);
  const [pickerQuery, setPickerQuery] = useState("");
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [isSearchingMore, setIsSearchingMore] = useState(false);

  const isEnhancing = enhanceStage === "searching" || enhanceStage === "enhancing";

  useEffect(() => {
    if (!isLoading) {
      setLoadingStep("");
      return;
    }
    const steps = [
      "레이아웃 생성 중…",
      "모듈 배치 최적화 중…",
      "glTF 내보내는 중…",
      "거의 다 됐어요…",
    ];
    loadingStepRef.current = 0;
    setLoadingStep(steps[0]);
    const id = setInterval(() => {
      loadingStepRef.current = (loadingStepRef.current + 1) % steps.length;
      setLoadingStep(steps[loadingStepRef.current]);
    }, 5000);
    return () => clearInterval(id);
  }, [isLoading]);

  const isRefineMode = mode === "refine" && hasCurrentSpec;
  const enhanceModel = backend === "claude" ? model : CLAUDE_HAIKU;

  useEffect(() => {
    if (mode === "refine") {
      setEnhancedOnce(false);
      setEnhanceError(null);
      setEnhanceStage("idle");
      setPickerImages([]);
    }
  }, [mode]);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!prompt.trim() || isLoading || fullPipelineBusy) return;
      if (mode === "refine") {
        await onRefine(prompt.trim());
        setPrompt("");
      }
    },
    [prompt, isLoading, fullPipelineBusy, mode, onRefine],
  );

  const doEnhanceStream = useCallback(
    async (referencePaths: string[]) => {
      setEnhanceStage("enhancing");
      setPrompt("");
      try {
        await enhancePrompt(
          prompt.trim(),
          enhanceModel,
          (chunk) => setPrompt((prev) => prev + chunk),
          undefined,
          undefined,
          referencePaths,
        );
        setEnhancedOnce(true);
      } catch (e) {
        setEnhanceError(e instanceof Error ? e.message : "Enhance failed");
      } finally {
        setEnhanceStage("idle");
        setPickerImages([]);
        setSelectedPaths(new Set());
        setPickerQuery("");
      }
    },
    [prompt, enhanceModel],
  );

  const handleEnhance = useCallback(async () => {
    if (!prompt.trim() || isEnhancing) return;
    setEnhanceError(null);

    // First check for search intent + fetch images
    setEnhanceStage("searching");
    try {
      const result = await searchImages({ prompt: prompt.trim() });
      if (result.detected && result.images.length > 0) {
        setPickerImages(result.images);
        setPickerQuery(result.query);
        setSelectedPaths(new Set(result.images.map((i) => i.path)));
        setEnhanceStage("picking");
      } else {
        // No search intent — enhance directly without images
        await doEnhanceStream([]);
      }
    } catch (e) {
      setEnhanceError(e instanceof Error ? e.message : "검색 실패");
      setEnhanceStage("idle");
    }
  }, [prompt, isEnhancing, doEnhanceStream]);

  const handlePickerConfirm = useCallback(async () => {
    await doEnhanceStream(Array.from(selectedPaths));
  }, [doEnhanceStream, selectedPaths]);

  const handlePickerSkip = useCallback(async () => {
    await doEnhanceStream([]);
  }, [doEnhanceStream]);

  const handleSearchMore = useCallback(
    async (query: string) => {
      setIsSearchingMore(true);
      try {
        const combined = pickerQuery ? `${pickerQuery} ${query}` : query;
        const result = await searchImages({ query: combined, maxImages: 10 });
        if (result.images.length > 0) {
          setPickerImages((prev) => {
            const existingPaths = new Set(prev.map((i) => i.path));
            const fresh = result.images.filter((i) => !existingPaths.has(i.path));
            return [...prev, ...fresh];
          });
          setSelectedPaths((prev) => {
            const next = new Set(prev);
            result.images.forEach((i) => next.add(i.path));
            return next;
          });
        }
      } catch {
        /* silently ignore */
      } finally {
        setIsSearchingMore(false);
      }
    },
    [pickerQuery],
  );

  const handleToggle = useCallback((path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedPaths(new Set(pickerImages.map((i) => i.path)));
  }, [pickerImages]);

  const handleDeselectAll = useCallback(() => {
    setSelectedPaths(new Set());
  }, []);

  const handleGenerateClick = useCallback(async () => {
    if (!prompt.trim() || isLoading || fullPipelineBusy) return;
    setMaxModulesError(null);
    let maxModules: number | undefined;
    const rawCap = maxModulesInput.trim();
    if (rawCap !== "") {
      const n = parseInt(rawCap, 10);
      if (!Number.isFinite(n) || n < 1 || n > 256) {
        setMaxModulesError("1–256 사이 정수이거나 비워 두세요.");
        return;
      }
      maxModules = n;
    }
    try {
      await onGenerate(prompt.trim(), backend, model, maxModules);
      setPrompt("");
      setEnhancedOnce(false);
      setEnhanceError(null);
    } catch {
      /* parent sets error */
    }
  }, [prompt, isLoading, fullPipelineBusy, onGenerate, backend, model, maxModulesInput]);

  const busy = isLoading || isEnhancing || fullPipelineBusy;
  const generateSpinner = isLoading || fullPipelineBusy;

  return (
    <div className="space-y-2">
      {hasCurrentSpec && (
        <div className="flex gap-1 text-xs">
          <button
            type="button"
            onClick={() => setMode("generate")}
            className={`px-3 py-1 rounded-md transition-colors ${
              mode === "generate"
                ? "bg-[#4f6df5] text-white"
                : "bg-[#1e1e2e] text-[#888] hover:text-[#c0c0d0] border border-[#2e2e3e]"
            }`}
          >
            New Scene
          </button>
          <button
            type="button"
            onClick={() => setMode("refine")}
            className={`px-3 py-1 rounded-md transition-colors ${
              mode === "refine"
                ? "bg-[#2ea87e] text-white"
                : "bg-[#1e1e2e] text-[#888] hover:text-[#c0c0d0] border border-[#2e2e3e]"
            }`}
          >
            + Add / Modify
          </button>
        </div>
      )}
      {hasCurrentSpec && isRefineMode && selectedModuleId && (
        <p className="text-[11px] text-[#8ab4a8] leading-snug px-0.5">
          선택된 모듈만 수정:{" "}
          <span className="font-mono text-[#c0e0d8]">{selectedModuleId}</span>
          {" · "}
          전체 씬을 바꾸려면 리스트/뷰에서 선택을 해제하세요.
        </p>
      )}

      {!isRefineMode ? (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2 items-stretch">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  if (!prompt.trim() || busy) return;
                  void handleGenerateClick();
                }
              }}
              rows={4}
              placeholder={
                "씬을 설명하세요. Enhance로 프롬프트를 확장하거나 바로 Generate 할 수 있습니다.\n(⌘Enter = Generate)"
              }
              className="flex-1 min-w-0 border rounded-lg px-4 py-3 text-sm text-[#e0e0e8] placeholder-[#555] focus:outline-none transition-colors resize-none leading-relaxed bg-[#1e1e2e] border-[#2e2e3e] focus:border-[#4f6df5]"
              disabled={busy}
            />
            <div className="flex flex-col gap-2 self-stretch shrink-0 w-[7.75rem]">
              <button
                type="button"
                onClick={() => void handleEnhance()}
                disabled={busy || !prompt.trim()}
                className="min-h-[2.5rem] px-3 py-2 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-xs font-medium transition-colors bg-violet-600 hover:bg-violet-500 text-white"
              >
                {enhanceStage === "searching" ? (
                  <span className="flex items-center justify-center gap-1.5">
                    <svg className="animate-spin h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    검색 중…
                  </span>
                ) : enhanceStage === "enhancing" ? (
                  <span className="flex items-center justify-center gap-1.5">
                    <svg className="animate-spin h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Enhancing…
                  </span>
                ) : enhancedOnce ? (
                  "Re-Enhance"
                ) : (
                  "Enhance"
                )}
              </button>
              <button
                type="button"
                onClick={() => void handleGenerateClick()}
                disabled={busy || !prompt.trim()}
                className="flex-1 min-h-[2.75rem] px-3 py-2 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors bg-[#4f6df5] hover:bg-[#3b5de7] text-white"
              >
                {generateSpinner ? (
                  <span className="flex items-center justify-center gap-1.5">
                    <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {fullPipelineBusy && !isLoading
                      ? "파이프라인…"
                      : loadingStep || "Generating…"}
                  </span>
                ) : (
                  "Generate"
                )}
              </button>
            </div>
          </div>

          {/* Image picker panel — shown after search results arrive */}
          {enhanceStage === "picking" && (
            <ImagePickerPanel
              images={pickerImages}
              selectedPaths={selectedPaths}
              query={pickerQuery}
              isSearchingMore={isSearchingMore}
              onToggle={handleToggle}
              onSelectAll={handleSelectAll}
              onDeselectAll={handleDeselectAll}
              onSearchMore={handleSearchMore}
              onConfirm={handlePickerConfirm}
              onSkip={handlePickerSkip}
            />
          )}

          {backend !== "claude" && (
            <p className="text-[10px] text-[#666] px-0.5">
              Enhance uses Claude ({CLAUDE_SONNET}); generation still uses your selected backend.
            </p>
          )}
          {enhanceError && (
            <p className="text-xs text-red-400 px-0.5">{enhanceError}</p>
          )}
          <label className="flex flex-wrap items-center gap-2 text-[11px] text-[#888] px-0.5">
            <span className="shrink-0">최대 모듈 수</span>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={maxModulesInput}
              onChange={(e) => {
                setMaxModulesInput(e.target.value);
                setMaxModulesError(null);
              }}
              placeholder="비움 = 서버 기본"
              title="바닥·벽·건물 등 modules 배열 상한. 비우면 .env의 MAX_MODULES 또는 제한 없음."
              disabled={busy}
              className="w-28 bg-[#1e1e2e] border border-[#2e2e3e] rounded px-2 py-1 text-[#c0c0d0] placeholder-[#555] focus:outline-none focus:border-[#4f6df5] disabled:opacity-50"
            />
            <span className="text-[#666]">(1–256, 하늘·조명은 여기 포함 안 됨)</span>
          </label>
          {maxModulesError && (
            <p className="text-xs text-red-400 px-0.5">{maxModulesError}</p>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (prompt.trim() && !isLoading && !fullPipelineBusy)
                  handleSubmit(e as any);
              }
            }}
            rows={3}
            placeholder={
              selectedModuleId
                ? `e.g. Make this a red brick facade with green awnings…\n(applies only to ${selectedModuleId})\n(⌘Enter to submit)`
                : "Add palm trees every 15m along sidewalks…\n(whole scene — no module selected)\n(⌘Enter to submit)"
            }
            className={`flex-1 border rounded-lg px-4 py-3 text-sm text-[#e0e0e8] placeholder-[#555] focus:outline-none transition-colors resize-none leading-relaxed ${
              selectedModuleId
                ? "bg-[#0e1a1f] border-[#3d8ab8]/50 focus:border-[#3d8ab8]"
                : "bg-[#0e1f1a] border-[#2ea87e]/50 focus:border-[#2ea87e]"
            }`}
            disabled={isLoading || fullPipelineBusy}
          />
          <button
            type="submit"
            disabled={isLoading || fullPipelineBusy || !prompt.trim()}
            className={`px-6 py-3 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors whitespace-nowrap shrink-0 ${
              selectedModuleId
                ? "bg-[#2a7a9e] hover:bg-[#256a8a]"
                : "bg-[#2ea87e] hover:bg-[#25906b]"
            }`}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Refining…
              </span>
            ) : selectedModuleId ? (
              "Edit\nmodule"
            ) : (
              "Add /\nModify"
            )}
          </button>
        </form>
      )}
    </div>
  );
}
