"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import type { Project } from "@/lib/types";
import { useToast } from "@/components/ui/Toast";
import { Trash2, FileText, Calendar, ArrowRight, AlertTriangle } from "lucide-react";

function formatRelativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;
  
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

const ACCENTS = [
  { left: "bg-gradient-gold",                             badge: "bg-gold/10 text-gold border-gold/25" },
  { left: "bg-gradient-to-b from-blue-500 to-cyan-500",  badge: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  { left: "bg-gradient-to-b from-emerald-500 to-teal-500", badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  { left: "bg-gradient-to-b from-amber-500 to-orange-500", badge: "bg-amber-500/10 text-amber-300 border-amber-500/30" },
  { left: "bg-gradient-to-b from-yellow-500 to-gold",      badge: "bg-gold/15 text-gold border-gold/30" },
  { left: "bg-gradient-to-b from-cyan-500 to-blue-500",  badge: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" },
];

function hashName(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xFFFF;
  return h % ACCENTS.length;
}

export default function ProjectCard({ project }: { project: Project }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const accent = ACCENTS[hashName(project.name)];
  const [confirmDelete, setConfirmDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => projectsApi.delete(project.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      // Also invalidate the chat history cache for this project
      qc.removeQueries({ queryKey: ["chat", project.name] });
      toast(`"${project.name}" deleted`, "success");
    },
  });

  const href = `/projects/${encodeURIComponent(project.name)}`;

  return (
    <div className="group relative bg-card border border-border rounded-2xl overflow-hidden
      hover:border-gold/20 hover:shadow-card-hover transition-all duration-300 card-mesh">
      {/* Left accent stripe */}
      <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${accent.left}`} />

      <Link href={href} className="block p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="w-10 h-10 rounded-xl bg-surface border border-border flex items-center justify-center shrink-0 shadow-inner group-hover:border-gold/20 group-hover:bg-gold/[0.04] transition-all">
            <FileText className="w-4.5 h-4.5 text-muted group-hover:text-gold transition-colors" />
          </div>
          <span className={`text-[10px] font-semibold border rounded-full px-3 py-1 shrink-0 whitespace-nowrap ${accent.badge}`}>
            {project.document_count} {project.document_count === 1 ? "doc" : "docs"}
          </span>
        </div>

        <h3 className="font-semibold text-[14px] text-white mb-1.5 truncate group-hover:text-gold transition-colors font-serif">
          {project.name}
        </h3>
        {project.description ? (
          <p className="text-xs text-muted line-clamp-2 mb-4 leading-relaxed">{project.description}</p>
        ) : (
          <p className="text-xs text-subtle mb-4 italic">No description</p>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-subtle">
            <Calendar className="w-3 h-3" />
            <p className="text-xs">{formatRelativeTime(project.created_at)}</p>
          </div>
          <div className="flex items-center gap-1 text-gold opacity-0 group-hover:opacity-100 transition-all text-xs font-semibold">
            Open
            <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
          </div>
        </div>
      </Link>

      {/* Delete button */}
      <button
        onClick={(e) => { e.preventDefault(); setConfirmDelete(true); }}
        aria-label={`Delete ${project.name}`}
        className="absolute top-3 right-3 transition-all
          w-8 h-8 flex items-center justify-center rounded-lg
          text-subtle hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 z-20"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-primary/80 backdrop-blur-sm" onClick={() => setConfirmDelete(false)} />
          <div className="relative z-10 bg-card border border-border rounded-2xl p-6 w-full max-w-md shadow-glow animate-in scale-in">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-white mb-1">Delete &ldquo;{project.name}&rdquo;?</p>
                <p className="text-xs text-muted">This action cannot be undone.</p>
              </div>
              <div className="flex gap-3 w-full pt-2">
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="flex-1 h-10 rounded-lg border border-border text-xs font-medium text-muted hover:text-white hover:bg-white/[0.04] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  className="flex-1 h-10 rounded-lg bg-red-500/10 border border-red-500/25 text-xs font-semibold text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-50"
                >
                  {deleteMutation.isPending ? "Deleting…" : "Delete"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
