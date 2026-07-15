"use client";

import { useState } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import { useProject, useDocuments } from "@/lib/hooks/useProjectQueries";
import type { Project } from "@/lib/types";
import UploadArea from "./UploadArea";
import PipelineModal from "./PipelineModal";
import KnowledgeBaseStats from "./KnowledgeBaseStats";
import Link from "next/link";
import { Layers, FileText, Trash2 } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

interface Props {
  project: Project;
}

export default function KnowledgeBase({ project }: Props) {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const qc = useQueryClient();
  const { toast } = useToast();

  // Use shared hooks with polling enabled during active job
  const pollingInterval = activeJobId ? 3000 : false;
  const { data: refreshedProject } = useProject(project.name, pollingInterval);
  const { data: documentsData } = useDocuments(project.name, pollingInterval);

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => projectsApi.deleteDocument(project.name, filename),
    onSuccess: (_, filename) => {
      toast(`Deleted "${filename}"`, "success");
      qc.invalidateQueries({ queryKey: ["documents", project.name] });
      qc.invalidateQueries({ queryKey: ["project", project.name] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (err: Error) => {
      toast(`Delete failed: ${err.message}`, "error");
    },
  });

  const docCount = refreshedProject?.document_count ?? project.document_count;
  const documents = documentsData?.documents ?? [];

  return (
    <div className="w-80 shrink-0 border-l border-border flex flex-col bg-surface">
      {/* Header */}
      <div className="h-16 px-5 flex items-center border-b border-border gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shadow-glow-sm">
          <Layers className="w-3.5 h-3.5 text-gold" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white leading-none">Knowledge Base</p>
          <p className="text-xs text-muted mt-0.5">{docCount} document{docCount !== 1 ? "s" : ""}</p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* Stats */}
        {docCount > 0 && <KnowledgeBaseStats project={refreshedProject || project} />}

        {/* Documents List */}
        {documents.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">Documents</p>
            <div className="space-y-1.5">
              {documents.map((doc) => (
                <div
                  key={doc.filename}
                  className="flex items-center gap-2 p-2.5 rounded-lg bg-card border border-border
                    hover:bg-card-hover transition-colors group"
                >
                  <FileText className="w-3.5 h-3.5 text-gold shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-white truncate">{doc.filename}</p>
                    <p className="text-[10px] text-muted">
                      {(doc.size_bytes / 1024 / 1024).toFixed(1)} MB
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      if (confirm(`Delete "${doc.filename}"?`)) {
                        deleteMutation.mutate(doc.filename);
                      }
                    }}
                    disabled={deleteMutation.isPending}
                    className="p-1.5 rounded-md opacity-0 group-hover:opacity-100 transition-opacity
                      hover:bg-red-500/10 hover:text-red-400 text-muted disabled:opacity-50"
                    title="Delete document"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upload */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">Upload</p>
          <UploadArea
            projectName={project.name}
            onJobStarted={(jobId) => {
              setActiveJobId(jobId);
              qc.invalidateQueries({ queryKey: ["project", project.name] });
              qc.invalidateQueries({ queryKey: ["documents", project.name] });
            }}
          />
        </div>

        {/* Quick actions */}
        {docCount > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">Actions</p>
            <Link
              href={`/projects/${encodeURIComponent(project.name)}/chunks`}
              className="flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl
                bg-card border border-border hover:bg-card-hover hover:border-border-hover
                text-sm text-muted hover:text-white transition-all"
            >
              <Layers className="w-3.5 h-3.5" />
              View all chunks
              <span className="ml-auto text-xs font-medium bg-surface rounded-lg px-2 py-0.5 text-muted border border-border">
                {docCount}
              </span>
            </Link>
          </div>
        )}
      </div>

      {/* Pipeline modal */}
      <PipelineModal
        jobId={activeJobId}
        projectName={project.name}
        onClose={() => {
          setActiveJobId(null);
          qc.invalidateQueries({ queryKey: ["project", project.name] });
          qc.invalidateQueries({ queryKey: ["projects"] });
          qc.invalidateQueries({ queryKey: ["documents", project.name] });
        }}
      />
    </div>
  );
}
