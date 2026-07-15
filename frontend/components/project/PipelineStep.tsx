"use client";

import type { JobStep } from "@/lib/types";
import { Check, X, FileText, Scissors, Brain, Cpu } from "lucide-react";

interface Props {
  step: JobStep;
  isLast: boolean;
  index: number;
}

function StatusIcon({ status }: { status: JobStep["status"] }) {
  if (status === "completed") {
    return (
      <div className="w-7 h-7 rounded-full bg-emerald-950 border border-emerald-700/50 flex items-center justify-center animate-in zoom-in duration-300">
        <Check className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2.5} />
      </div>
    );
  }
  if (status === "running") {
    return (
      <div className="w-7 h-7 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center relative">
        <span className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        <div className="absolute inset-[-3px] rounded-full border border-accent/20 animate-ping" style={{ animationDuration: "2s" }} />
      </div>
    );
  }
  if (status === "failed") {
    return (
      <div className="w-7 h-7 rounded-full bg-red-950 border border-red-700/50 flex items-center justify-center">
        <X className="w-3.5 h-3.5 text-red-400" strokeWidth={2.5} />
      </div>
    );
  }
  return (
    <div className="w-7 h-7 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center">
      <span className="w-1.5 h-1.5 rounded-full bg-subtle" />
    </div>
  );
}

const statusLabel: Record<JobStep["status"], string> = {
  pending: "Waiting",
  running: "Processing",
  completed: "Done",
  failed: "Failed",
};

const statusColor: Record<JobStep["status"], string> = {
  pending: "text-subtle",
  running: "text-accent-light",
  completed: "text-emerald-400",
  failed: "text-red-400",
};

const stepDescriptions: Record<string, string> = {
  partitioning: "Extracting text, tables & images from PDF",
  chunking: "Splitting content into semantic chunks",
  summarisation: "AI-powered summaries for each chunk",
  embedding: "Converting chunks to vector embeddings",
};

const stepIcons: Record<string, React.ElementType> = {
  partitioning: FileText,
  chunking: Scissors,
  summarisation: Brain,
  embedding: Cpu,
};

export default function PipelineStepRow({ step, isLast, index }: Props) {
  const duration =
    step.started_at && step.completed_at
      ? ((new Date(step.completed_at).getTime() - new Date(step.started_at).getTime()) / 1000).toFixed(1)
      : null;

  const key = step.name.toLowerCase();
  const isActive = step.status === "running";
  const isDone = step.status === "completed";
  const StepIcon = stepIcons[key];

  return (
    <div className="flex gap-3" style={{ animationDelay: `${index * 100}ms` }}>
      {/* Timeline */}
      <div className="flex flex-col items-center">
        <StatusIcon status={step.status} />
        {!isLast && (
          <div
            className={`w-px flex-1 mt-1 min-h-[20px] transition-colors duration-500 ${
              isDone ? "bg-emerald-500/40" : "bg-zinc-800"
            }`}
          />
        )}
      </div>

      {/* Content */}
      <div className={`pb-4 flex-1 transition-opacity duration-300 ${step.status === "pending" ? "opacity-40" : "opacity-100"}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            {StepIcon && (
              <div className={`w-5 h-5 rounded flex items-center justify-center
                ${isDone ? "bg-emerald-950" : isActive ? "bg-accent/15" : "bg-zinc-800"}`}>
                <StepIcon className={`w-3 h-3 ${isDone ? "text-emerald-400" : isActive ? "text-accent-light" : "text-zinc-500"}`} />
              </div>
            )}
            <div>
              <span className={`text-sm font-semibold ${isActive || isDone ? "text-white" : "text-zinc-500"}`}>
                {step.name}
              </span>
              {stepDescriptions[key] && (
                <p className="text-xs text-subtle mt-0.5 leading-snug">
                  {stepDescriptions[key]}
                </p>
              )}
            </div>
          </div>
          <div className="text-right shrink-0">
            <span className={`text-xs font-medium ${statusColor[step.status]}`}>
              {statusLabel[step.status]}
            </span>
            {duration && (
              <p className="text-[10px] text-subtle mt-0.5">{duration}s</p>
            )}
          </div>
        </div>

        {/* Active step progress bar */}
        {isActive && (
          <div className="mt-2 h-1 bg-surface rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent via-accent-light to-accent"
              style={{ width: "100%", animation: "shimmer 1.5s ease-in-out infinite" }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
