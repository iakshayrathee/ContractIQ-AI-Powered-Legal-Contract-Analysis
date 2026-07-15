"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "@/lib/api";
import type { Job } from "@/lib/types";
import { CheckCircle, Circle, AlertCircle, Clock, HelpCircle, Upload, Scissors, Brain, Database, BarChart2, X } from "lucide-react";

// Maps frontend display steps to backend step names
const PIPELINE_STEPS = [
  {
    name: "File Upload",
    stepKey: null, // Not a backend step — completes when job is created
    icon: Upload,
    description: "Contract file received and saved to server storage",
    statKeys: [], // No details for this step
  },
  {
    name: "Parsing",
    stepKey: "Parsing",
    icon: Scissors,
    description: "Extract text, tables, and images from PDF (PyMuPDF) or DOCX (python-docx) — page by page",
    statKeys: [
      { key: "total_pages", label: "Pages" },
      { key: "non_empty_pages", label: "Non-empty" },
      { key: "total_characters", label: "Characters", format: (v: number) => v.toLocaleString() },
      { key: "total_tables", label: "Tables" },
      { key: "total_images", label: "Images" },
    ],
  },
  {
    name: "Chunking",
    stepKey: "Chunking",
    icon: BarChart2,
    description: "Split text into overlapping chunks (size=1024, overlap=200) with accurate page tracking",
    statKeys: [
      { key: "chunks_count", label: "Chunks" },
      { key: "avg_chunk_size", label: "Avg size (chars)" },
      { key: "image_description_chunks", label: "Image chunks" },
    ],
  },
  {
    name: "Embedding Prep",
    stepKey: "Embedding Prep",
    icon: Brain,
    description: "Build contextual embeddings with metadata (document, page, clause type, section) for better retrieval",
    statKeys: [
      { key: "total_chunks", label: "Total chunks" },
      { key: "processed_chunks", label: "Processed" },
    ],
  },
  {
    name: "Vectorization & Storage",
    stepKey: "Embedding",
    icon: Database,
    description: "Generate dense (text-embedding-3-small) + sparse (BM25) vectors with hybrid RRF scoring → store in Qdrant",
    statKeys: [
      { key: "vectors_stored", label: "Vectors stored" },
      { key: "collection_name", label: "Collection" },
    ],
  },
];

interface Props {
  jobId: string | null;
  projectName: string;
  onClose: () => void;
}

function QueueTooltip() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block">
      <button
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] text-subtle hover:text-gold transition-colors"
        aria-label="What is the queue?"
      >
        <HelpCircle className="w-3.5 h-3.5" />
        <span>What is the queue?</span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-72 bg-card border border-border rounded-xl p-3.5 shadow-2xl z-50 text-left pointer-events-none">
          <p className="text-xs font-semibold text-gold mb-1.5">📋 About the Job Queue</p>
          <p className="text-xs text-muted leading-relaxed mb-2">
            When you upload a contract, ContractIQ creates a <span className="text-white font-medium">background job</span> and returns a <code className="bg-surface px-1 rounded text-accent-light">job_id</code> immediately — so you can keep using the app while processing happens.
          </p>
          <p className="text-xs text-muted leading-relaxed mb-2">
            The <span className="text-white font-medium">improved pipeline</span> uses contextual embeddings and hybrid search (RRF) for accurate retrieval:
          </p>
          <ol className="text-xs text-muted space-y-1 ml-3 list-decimal">
            <li><span className="text-white">Parsing</span> — Extracts text, tables, and images</li>
            <li><span className="text-white">Chunking</span> — Splits text with accurate page tracking</li>
            <li><span className="text-white">Embedding Prep</span> — Adds contextual metadata (doc, page, clause type)</li>
            <li><span className="text-white">Vectorization</span> — Dense + sparse vectors with RRF scoring</li>
          </ol>
          <p className="text-[10px] text-subtle mt-2">
            Poll <code className="bg-surface px-1 rounded">GET /jobs/{"{job_id}"}</code> every 1.5s for live progress.
          </p>
        </div>
      )}
    </div>
  );
}

export default function PipelineModal({ jobId, projectName, onClose }: Props) {
  const [elapsedTime, setElapsedTime] = useState(0);

  const { data: job } = useQuery<Job>({
    queryKey: ["job", jobId],
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      if (s === "completed" || s === "failed") return false;
      return 1500;
    },
  });

  const isDone = job?.status === "completed" || job?.status === "failed";

  // Escape key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isDone) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isDone, onClose]);

  // Timer for elapsed processing time
  useEffect(() => {
    if (!jobId || isDone) return;
    const interval = setInterval(() => {
      setElapsedTime((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [jobId, isDone]);

  if (!jobId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={isDone ? onClose : undefined}
      />

      {/* Modal Container */}
      <div className="relative z-10 w-[95vw] max-w-[580px] bg-primary border border-border rounded-2xl shadow-2xl scale-in overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <p className="text-sm font-semibold text-white truncate max-w-[340px]">
              {job?.document_name || "Processing..."}
            </p>
            <p className="text-xs text-muted">Ingestion Pipeline · {projectName}</p>
          </div>
          <button
            onClick={isDone ? onClose : undefined}
            disabled={!isDone}
            aria-label="Close modal"
            className={`w-8 h-8 flex items-center justify-center rounded-lg transition-colors ${
              isDone
                ? "text-muted hover:text-white hover:bg-card focus-ring"
                : "text-subtle cursor-not-allowed opacity-50"
            }`}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Timeline body */}
        <div className="px-6 py-5 space-y-4 max-h-[65vh] overflow-y-auto">
          {PIPELINE_STEPS.map((step, i) => {
            // File Upload step: always completed as soon as job exists
            const isFileUpload = step.stepKey === null;
            const jobStep = isFileUpload
              ? null
              : job?.steps.find((s) => s.name === step.stepKey);

            const status = isFileUpload
              ? (job ? "completed" : "pending")
              : (jobStep?.status || "pending");

            const isCompleted = status === "completed";
            const isRunning = status === "running";
            const isFailed = status === "failed";
            const isPending = status === "pending";

            const details = jobStep?.details ?? {};
            const hasStats = step.statKeys.length > 0 && Object.keys(details).length > 0;

            const StepIcon = step.icon;

            return (
              <div key={step.name} className="flex gap-4">
                {/* Timeline connector */}
                <div className="flex flex-col items-center">
                  <div
                    className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                      isCompleted
                        ? "bg-emerald-500/20 border border-emerald-500/30"
                        : isRunning
                        ? "bg-gold/20 border border-gold/30 animate-pulse"
                        : isFailed
                        ? "bg-red-500/20 border border-red-500/30"
                        : "bg-card border border-border"
                    }`}
                  >
                    {isCompleted ? (
                      <CheckCircle className="w-4 h-4 text-emerald-400" />
                    ) : isRunning ? (
                      <Clock className="w-4 h-4 text-gold animate-spin" />
                    ) : isFailed ? (
                      <AlertCircle className="w-4 h-4 text-red-400" />
                    ) : (
                      <StepIcon className="w-4 h-4 text-subtle" />
                    )}
                  </div>

                  {/* Connecting Line */}
                  {i < PIPELINE_STEPS.length - 1 && (
                    <div
                      className={`w-0.5 h-8 mt-1 transition-colors ${
                        isCompleted ? "bg-emerald-500/30" : "bg-border"
                      }`}
                    />
                  )}
                </div>

                {/* Step content */}
                <div className="flex-1 pt-0.5 pb-2">
                  <div className="flex items-center gap-2 mb-0.5">
                    <p className={`text-sm font-semibold ${
                      isRunning ? "text-gold" : isCompleted ? "text-white" : isFailed ? "text-red-400" : "text-muted"
                    }`}>
                      {step.name}
                    </p>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                      isCompleted
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                        : isRunning
                        ? "bg-gold/10 border-gold/20 text-gold"
                        : isFailed
                        ? "bg-red-500/10 border-red-500/20 text-red-400"
                        : "bg-card border-border text-subtle"
                    }`}>
                      {isCompleted ? "Done" : isRunning ? "Running" : isFailed ? "Failed" : "Queued"}
                    </span>
                  </div>
                  <p className="text-[11px] text-subtle leading-relaxed mb-1.5">{step.description}</p>

                  {/* Step stats from job details */}
                  {hasStats && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {step.statKeys.map(({ key, label, format }) => {
                        const val = details[key as string];
                        if (val === undefined || val === null) return null;
                        const display = format ? format(val as number) : String(val);
                        return (
                          <div key={key} className="flex items-center gap-1.5 bg-surface/80 border border-border rounded-lg px-2.5 py-1.5">
                            <span className="text-[10px] text-subtle uppercase tracking-wide">{label}:</span>
                            <span className="text-xs font-semibold text-white">{display}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Chunk count from job root (final tally) */}
                  {isCompleted && step.stepKey === "Embedding" && job?.chunk_count != null && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-2.5 py-1.5">
                        <span className="text-[10px] text-subtle uppercase tracking-wide">Total vectors:</span>
                        <span className="text-xs font-semibold text-emerald-400">{job.chunk_count}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border bg-surface/50">
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-3 text-xs text-muted">
                <span>
                  Status:{" "}
                  <span className={`font-semibold capitalize ${
                    job?.status === "completed" ? "text-emerald-400" :
                    job?.status === "failed" ? "text-red-400" : "text-gold"
                  }`}>
                    {job?.status || "queued"}
                  </span>
                </span>
                <span>·</span>
                <span>Elapsed: <span className="text-white font-medium">{elapsedTime}s</span></span>
                {job?.chunk_count != null && (
                  <>
                    <span>·</span>
                    <span>Vectors: <span className="text-emerald-400 font-medium">{job.chunk_count}</span></span>
                  </>
                )}
              </div>
              <QueueTooltip />
            </div>
            {isDone && (
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-xl bg-gradient-gold text-[#000000] text-xs font-semibold
                  hover:shadow-glow-md hover:scale-105 transition-all focus-ring"
              >
                Done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
