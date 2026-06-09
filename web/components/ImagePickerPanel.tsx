"use client";

import { useState, useCallback, type KeyboardEvent } from "react";
import type { SearchImageItem } from "@/lib/api";

interface Props {
  images: SearchImageItem[];
  selectedPaths: Set<string>;
  query: string;        // original base query
  isSearchingMore: boolean;
  onToggle: (path: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onSearchMore: (additionalQuery: string) => void;
  onConfirm: () => void;
  onSkip: () => void;
}

export default function ImagePickerPanel({
  images,
  selectedPaths,
  query,
  isSearchingMore,
  onToggle,
  onSelectAll,
  onDeselectAll,
  onSearchMore,
  onConfirm,
  onSkip,
}: Props) {
  const [moreQuery, setMoreQuery] = useState("");
  const [failedUrls, setFailedUrls] = useState<Set<string>>(new Set());

  const handleSearchMore = useCallback(() => {
    const q = moreQuery.trim();
    if (!q || isSearchingMore) return;
    onSearchMore(q);
    setMoreQuery("");
  }, [moreQuery, isSearchingMore, onSearchMore]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") handleSearchMore();
    },
    [handleSearchMore],
  );

  const selectedCount = selectedPaths.size;
  const allSelected = images.length > 0 && selectedCount === images.length;

  return (
    <div className="rounded-xl border border-[#3a3a50] bg-[#13131f] p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <p className="text-xs font-medium text-[#c0c0d0]">
            검색 결과:{" "}
            <span className="text-violet-400 font-mono">{query}</span>
          </p>
          <p className="text-[11px] text-[#666]">
            {images.length}장 다운로드 · 사용할 이미지를 선택하세요
          </p>
        </div>
        <div className="flex gap-1.5 shrink-0">
          <button
            type="button"
            onClick={allSelected ? onDeselectAll : onSelectAll}
            className="px-2 py-1 text-[11px] rounded-md border border-[#2e2e3e] text-[#888] hover:text-[#c0c0d0] hover:border-[#4e4e6e] transition-colors"
          >
            {allSelected ? "전체 해제" : "전체 선택"}
          </button>
        </div>
      </div>

      {/* Image grid */}
      {images.length === 0 ? (
        <p className="text-[11px] text-[#555] text-center py-4">
          다운로드된 이미지가 없습니다.
        </p>
      ) : (
        <div className="grid grid-cols-5 gap-1.5 max-h-64 overflow-y-auto pr-0.5">
          {images.map((img) => {
            const selected = selectedPaths.has(img.path);
            const failed = failedUrls.has(img.url);
            return (
              <button
                key={img.path}
                type="button"
                onClick={() => onToggle(img.path)}
                className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all focus:outline-none ${
                  selected
                    ? "border-violet-500 ring-1 ring-violet-500/40"
                    : "border-[#2e2e3e] opacity-50 hover:opacity-70"
                }`}
              >
                {failed ? (
                  <div className="w-full h-full bg-[#1e1e2e] flex items-center justify-center">
                    <span className="text-[10px] text-[#555]">로드 실패</span>
                  </div>
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={img.url}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={() =>
                      setFailedUrls((prev) => new Set(prev).add(img.url))
                    }
                  />
                )}
                {/* Checkmark */}
                <div
                  className={`absolute top-1 right-1 w-4 h-4 rounded-full flex items-center justify-center transition-all ${
                    selected
                      ? "bg-violet-500"
                      : "bg-black/60 border border-[#555]"
                  }`}
                >
                  {selected && (
                    <svg
                      viewBox="0 0 12 12"
                      className="w-2.5 h-2.5 text-white"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Search more */}
      <div className="flex gap-1.5 items-center">
        <input
          type="text"
          value={moreQuery}
          onChange={(e) => setMoreQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`"${query}" + 추가어 입력… (예: exterior, interior, aerial)`}
          disabled={isSearchingMore}
          className="flex-1 bg-[#1e1e2e] border border-[#2e2e3e] rounded-lg px-3 py-1.5 text-xs text-[#c0c0d0] placeholder-[#444] focus:outline-none focus:border-[#4f6df5] disabled:opacity-50"
        />
        <button
          type="button"
          onClick={handleSearchMore}
          disabled={!moreQuery.trim() || isSearchingMore}
          className="px-3 py-1.5 text-xs rounded-lg bg-[#1e1e2e] border border-[#2e2e3e] text-[#888] hover:text-[#c0c0d0] hover:border-[#4e4e6e] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          {isSearchingMore ? (
            <span className="flex items-center gap-1.5">
              <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12" cy="12" r="10"
                  stroke="currentColor" strokeWidth="4" fill="none"
                />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              검색 중…
            </span>
          ) : (
            "추가 검색"
          )}
        </button>
      </div>

      {/* Footer actions */}
      <div className="flex items-center justify-between pt-0.5">
        <button
          type="button"
          onClick={onSkip}
          className="text-[11px] text-[#555] hover:text-[#888] transition-colors underline underline-offset-2"
        >
          이미지 없이 Enhance
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={selectedCount === 0}
          className="px-4 py-1.5 text-xs font-medium rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
        >
          선택한 이미지 {selectedCount}장으로 Enhance
        </button>
      </div>
    </div>
  );
}
