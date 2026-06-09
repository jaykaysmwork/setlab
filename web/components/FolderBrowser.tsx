"use client";

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { apiBase, authHeaders } from "@/lib/api";

interface Entry {
  name: string;
  path: string;
  is_project: boolean;
}

interface BrowseResult {
  current: string;
  parent: string | null;
  entries: Entry[];
}

interface Props {
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export default function FolderBrowser({ initialPath, onSelect, onClose }: Props) {
  const [result, setResult] = useState<BrowseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [manualPath, setManualPath] = useState(initialPath);

  const browse = useCallback(async (path: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase()}/api/browse?path=${encodeURIComponent(path)}`, {
        headers: { ...authHeaders() },
      });
      if (res.ok) {
        setResult(await res.json());
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    browse(initialPath || "");
  }, [initialPath, browse]);

  const pathSegments = result?.current.split("/").filter(Boolean) ?? [];

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="relative w-[560px] max-h-[480px] bg-[#15151f] border border-[#2a2a3a] rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title bar */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#222230]">
          <h2 className="text-[13px] font-semibold text-[#d0d0d8]">
            Select Unreal Project Folder
          </h2>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded-md text-[#666] hover:text-[#ccc] hover:bg-[#2a2a3a] transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Quick access + Breadcrumb */}
        <div className="px-4 py-2.5 border-b border-[#222230] space-y-2">
          <div className="flex gap-1.5">
            {[
              { label: "Home", path: "" },
              { label: "Desktop", path: "~/Desktop" },
              { label: "Documents", path: "~/Documents" },
            ].map((loc) => (
              <button
                key={loc.label}
                onClick={() => {
                  const resolved = loc.path.startsWith("~")
                    ? (result?.current.split("/").slice(0, 3).join("/") ?? "") + loc.path.slice(1)
                    : loc.path;
                  browse(resolved);
                }}
                className="px-2.5 py-1 bg-[#1c1c2c] hover:bg-[#2a2a3e] border border-[#2a2a3a] rounded-md text-[11px] text-[#999] hover:text-[#ccc] transition-colors"
              >
                {loc.label}
              </button>
            ))}
          </div>

          {/* Breadcrumb */}
          <div className="flex items-center gap-0.5 text-[11px] overflow-x-auto">
            <button
              onClick={() => browse("/")}
              className="text-[#666] hover:text-[#aaa] transition-colors shrink-0 px-1"
            >
              /
            </button>
            {pathSegments.map((seg, i) => {
              const fullPath = "/" + pathSegments.slice(0, i + 1).join("/");
              const isLast = i === pathSegments.length - 1;
              return (
                <span key={fullPath} className="flex items-center gap-0.5 shrink-0">
                  <span className="text-[#333]">/</span>
                  <button
                    onClick={() => browse(fullPath)}
                    className={`px-1 rounded transition-colors ${
                      isLast
                        ? "text-[#c0c0d0] font-medium"
                        : "text-[#666] hover:text-[#aaa]"
                    }`}
                  >
                    {seg}
                  </button>
                </span>
              );
            })}
          </div>
        </div>

        {/* Folder list */}
        <div className="flex-1 overflow-y-auto px-3 py-2 min-h-[200px]">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-[#555] text-xs">
              Loading...
            </div>
          ) : (
            <div className="space-y-0.5">
              {result?.parent && (
                <button
                  onClick={() => browse(result.parent!)}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs hover:bg-[#1e1e2e] transition-colors flex items-center gap-2.5 text-[#777]"
                >
                  <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                  <span>..</span>
                </button>
              )}

              {result?.entries.map((entry) => (
                <button
                  key={entry.path}
                  onClick={() =>
                    entry.is_project ? onSelect(entry.path) : browse(entry.path)
                  }
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-xs transition-colors flex items-center gap-2.5 group ${
                    entry.is_project
                      ? "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300"
                      : "hover:bg-[#1e1e2e] text-[#c0c0d0]"
                  }`}
                >
                  <svg
                    className={`w-4 h-4 shrink-0 ${
                      entry.is_project ? "text-emerald-400" : "text-[#4a4a5a]"
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.8}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                  <span className="flex-1 truncate">{entry.name}</span>
                  {entry.is_project ? (
                    <span className="text-[10px] font-medium uppercase tracking-wider text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded shrink-0">
                      Unreal Project
                    </span>
                  ) : (
                    <svg
                      className="w-3.5 h-3.5 text-[#333] group-hover:text-[#555] shrink-0 transition-colors"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                  )}
                </button>
              ))}

              {result?.entries.length === 0 && (
                <div className="flex items-center justify-center h-24 text-[#444] text-xs">
                  No subfolders
                </div>
              )}
            </div>
          )}
        </div>

        {/* Manual path input + footer */}
        <div className="px-4 py-3 border-t border-[#222230] bg-[#12121a] space-y-2.5">
          <div className="flex gap-1.5">
            <input
              type="text"
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSelect(manualPath.trim());
                }
              }}
              placeholder="Or paste path here — /Users/.../MyProject"
              className="flex-1 bg-[#1a1a28] border border-[#2a2a3a] rounded-lg px-3 py-2 text-xs text-[#c0c0d0] font-mono focus:outline-none focus:border-[#4f6df5] placeholder-[#444]"
            />
            <button
              onClick={() => manualPath.trim() && onSelect(manualPath.trim())}
              disabled={!manualPath.trim()}
              className="px-4 py-2 bg-[#4f6df5] hover:bg-[#3b5de7] disabled:opacity-40 rounded-lg text-xs font-medium transition-colors whitespace-nowrap"
            >
              Select
            </button>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-[#555]">
              .uproject 폴더는 초록색 — 클릭하면 바로 선택됩니다
            </p>
            <button
              onClick={onClose}
              className="px-3.5 py-1.5 text-xs text-[#888] hover:text-[#ccc] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
