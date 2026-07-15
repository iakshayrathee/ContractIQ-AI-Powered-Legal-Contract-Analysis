"use client";

import type { Project } from "@/lib/types";
import { useChunkStats } from "@/lib/hooks/useProjectQueries";
import { FileText, Layers, AlignLeft, Table2, Image } from "lucide-react";

interface Props {
  project: Project;
}

const STATS = [
  { key: "documents", label: "Documents", icon: FileText, iconColor: "text-white/80",   iconBg: "bg-white/[0.06]" },
  { key: "chunks",    label: "Chunks",    icon: Layers,   iconColor: "text-blue-400",   iconBg: "bg-blue-500/10" },
  { key: "text",      label: "Text",      icon: AlignLeft,iconColor: "text-emerald-400", iconBg: "bg-emerald-500/10" },
  { key: "tables",    label: "Tables",    icon: Table2,   iconColor: "text-amber-400",  iconBg: "bg-amber-500/10" },
  { key: "images",    label: "Images",    icon: Image,    iconColor: "text-pink-400",   iconBg: "bg-pink-500/10" },
];

export default function KnowledgeBaseStats({ project }: Props) {
  const { data: stats, isLoading } = useChunkStats(project.name);

  const values: Record<string, number> = {
    documents: project.document_count,
    chunks: stats?.total ?? 0,
    text:   stats?.by_type.text ?? 0,
    tables: stats?.by_type.table ?? 0,
    images: stats?.by_type.image ?? 0,
  };

  // Whether a stat value comes from the async stats query (not immediately available)
  const chunksLoading = isLoading;

  if (project.document_count === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle">Stats</p>
      <div className="grid grid-cols-2 gap-2">
        {STATS.map(({ key, label, icon: Icon, iconColor, iconBg }) => (
          <div key={key} className={`bg-card border border-border rounded-xl p-3 flex items-center gap-2.5 ${key === "documents" ? "col-span-2" : ""}`}>
            <div className={`w-7 h-7 rounded-lg ${iconBg} flex items-center justify-center shrink-0`}>
              <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
            </div>
            <div className="min-w-0">
              <p className="text-lg font-bold text-white leading-none">
                {chunksLoading && key !== "documents" ? (
                  <span className="text-subtle">—</span>
                ) : (
                  values[key]
                )}
              </p>
              <p className="text-[10px] text-muted mt-0.5">{label}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
