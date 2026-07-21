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
import { Layers, FileText, Trash2, AlertTriangle } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

interface Props {
  project: Project;
}

export default function KnowledgeBase({ project }: Props) {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
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
      qc.invalidateQueries({ queryKey: ["chunkStats", project.name] });
      // WS-1.4: corpus changed — clear the analysis cache so the panel shows "no analysis"
      qc.invalidateQueries({ queryKey: ["analysis", project.name] });
      qc.invalidateQueries({ queryKey: ["risks", project.name] });
      qc.invalidateQueries({ queryKey: ["summary", project.name] });
      // Chat history is cleared server-side on delete — refresh the chat panel too
      qc.invalidateQueries({ queryKey: ["chat", project.name] });
      setPendingDelete(null);
    },
    onError: (err: Error) => {
      toast(`Delete failed: ${err.message}`, "error");
      setPendingDelete(null);
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
                    onClick={() => setPendingDelete(doc.filename)}
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
          <p className="text-[10px] text-muted leading-relaxed">
            All uploaded documents are analyzed together as a single corpus.
            Add multiple files to build shared context for chat and analysis.
          </p>
          <UploadArea
            projectName={project.name}
            onJobStarted={(jobId) => {
              setActiveJobId(jobId);
              qc.invalidateQueries({ queryKey: ["project", project.name] });
              qc.invalidateQueries({ queryKey: ["projects"] });
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

      {/* Delete confirmation modal */}
      <Modal
        open={pendingDelete !== null}
        onClose={() => {
          if (!deleteMutation.isPending) setPendingDelete(null);
        }}
        title="Delete document"
      >
        {(() => {
          // isLastDocument: deleting this removes the entire corpus.
          const isLastDocument = documents.length <= 1;
          return (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-3.5 rounded-xl bg-red-500/[0.06] border border-red-500/20">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div className="space-y-1.5">
                  <p className="text-sm text-white">
                    Delete <span className="font-semibold break-all">&ldquo;{pendingDelete}&rdquo;</span>?
                  </p>

                  {isLastDocument ? (
                    <>
                      <p className="text-xs text-muted leading-relaxed">
                        This is the last document in the project. Removing it empties the
                        knowledge base, so the following will also be cleared:
                      </p>
                      <ul className="text-xs text-muted list-disc list-inside space-y-0.5">
                        <li>The contract analysis, risks, and summary</li>
                        <li>All chat history and Q&amp;A for this project</li>
                      </ul>
                    </>
                  ) : (
                    <>
                      <p className="text-xs text-muted leading-relaxed">
                        Analysis covers all documents together, so removing this one from the
                        corpus will:
                      </p>
                      <ul className="text-xs text-muted list-disc list-inside space-y-0.5">
                        <li>Reset the current analysis — re-run it over the remaining {documents.length - 1} document{documents.length - 1 !== 1 ? "s" : ""}</li>
                        <li>Keep your chat history (still supported by the remaining documents)</li>
                      </ul>
                    </>
                  )}

                  <p className="text-xs text-muted leading-relaxed">
                    This action cannot be undone.
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2.5">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingDelete(null)}
                  disabled={deleteMutation.isPending}
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  loading={deleteMutation.isPending}
                  onClick={() => {
                    if (pendingDelete) deleteMutation.mutate(pendingDelete);
                  }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete document
                </Button>
              </div>
            </div>
          );
        })()}
      </Modal>

      {/* Pipeline modal */}
      <PipelineModal
        jobId={activeJobId}
        projectName={project.name}
        onComplete={() => {
          // Invalidate stats as soon as the job finishes (before user closes modal)
          qc.invalidateQueries({ queryKey: ["chunkStats", project.name] });
          qc.invalidateQueries({ queryKey: ["project", project.name] });
          qc.invalidateQueries({ queryKey: ["projects"] });
          qc.invalidateQueries({ queryKey: ["documents", project.name] });
          // WS-1.5: new document ingested — clear stale analysis cache
          qc.invalidateQueries({ queryKey: ["analysis", project.name] });
          qc.invalidateQueries({ queryKey: ["risks", project.name] });
          qc.invalidateQueries({ queryKey: ["summary", project.name] });
        }}
        onClose={() => {
          setActiveJobId(null);
          qc.invalidateQueries({ queryKey: ["project", project.name] });
          qc.invalidateQueries({ queryKey: ["projects"] });
          qc.invalidateQueries({ queryKey: ["documents", project.name] });
          qc.invalidateQueries({ queryKey: ["chunkStats", project.name] });
          // WS-1.5: also invalidate on modal close in case onComplete was missed
          qc.invalidateQueries({ queryKey: ["analysis", project.name] });
          qc.invalidateQueries({ queryKey: ["risks", project.name] });
          qc.invalidateQueries({ queryKey: ["summary", project.name] });
        }}
      />
    </div>
  );
}
