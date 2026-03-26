"use client";

import type { HistoryItem } from "@/lib/api";

interface Props {
  items: HistoryItem[];
  activeId: string | null;
  onSelect: (item: HistoryItem) => void;
}

export default function HistoryPanel({ items, activeId, onSelect }: Props) {
  if (items.length === 0) {
    return (
      <div className="text-[#555] text-xs p-2">
        No previous generations yet.
      </div>
    );
  }

  return (
    <div className="space-y-1 overflow-y-auto">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item)}
          className={`w-full text-left p-2.5 rounded-lg text-xs transition-colors ${
            activeId === item.id
              ? "bg-[#2a2a4a] border border-[#4f6df5]/40"
              : "bg-[#16161e] hover:bg-[#1e1e2e] border border-transparent"
          }`}
        >
          <p className="font-medium text-[#c0c0d0] truncate">{item.title}</p>
          <div className="flex justify-between mt-0.5 text-[#666]">
            <span>{item.era_style || "—"}</span>
            <span>{item.moduleCount} modules</span>
          </div>
        </button>
      ))}
    </div>
  );
}
