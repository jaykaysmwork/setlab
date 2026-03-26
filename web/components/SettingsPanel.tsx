"use client";

import { useState, useCallback } from "react";
import FolderBrowser from "./FolderBrowser";

interface Props {
  backend: string;
  model: string;
  ueProject: string;
  onBackendChange: (v: string) => void;
  onModelChange: (v: string) => void;
  onUeProjectChange: (path: string) => Promise<void>;
}

export default function SettingsPanel({
  backend,
  model,
  ueProject,
  onBackendChange,
  onModelChange,
  onUeProjectChange,
}: Props) {
  const [showBrowser, setShowBrowser] = useState(false);

  const handleSelect = useCallback(
    async (path: string) => {
      try {
        await onUeProjectChange(path);
      } catch {
        // handled upstream
      }
      setShowBrowser(false);
    },
    [onUeProjectChange]
  );

  return (
    <>
      <div className="flex items-center gap-4 text-xs">
        <label className="flex items-center gap-1.5 text-[#888]">
          Backend
          <select
            value={backend}
            onChange={(e) => onBackendChange(e.target.value)}
            className="bg-[#1e1e2e] border border-[#2e2e3e] rounded px-2 py-1 text-[#c0c0d0] focus:outline-none focus:border-[#4f6df5]"
          >
            <option value="claude">Claude (API)</option>
            <option value="ollama">Ollama (Local)</option>
            <option value="mock">Mock (Test)</option>
          </select>
        </label>

        <label className="flex items-center gap-1.5 text-[#888]">
          Model
          <input
            type="text"
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            className="w-28 bg-[#1e1e2e] border border-[#2e2e3e] rounded px-2 py-1 text-[#c0c0d0] focus:outline-none focus:border-[#4f6df5]"
            disabled={backend === "mock"}
          />
        </label>

        <button
          onClick={() => setShowBrowser(true)}
          className="flex items-center gap-1.5 px-2 py-1 bg-[#1e1e2e] border border-[#2e2e3e] rounded text-[#c0c0d0] hover:border-[#4f6df5] transition-colors"
        >
          <svg
            className="w-3.5 h-3.5 text-[#888]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
          {ueProject ? (
            <span className="max-w-40 truncate" title={ueProject}>
              {ueProject.split("/").pop()}
            </span>
          ) : (
            <span className="text-[#666]">UE Project</span>
          )}
        </button>
      </div>

      {showBrowser && (
        <FolderBrowser
          initialPath={ueProject || ""}
          onSelect={handleSelect}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </>
  );
}
