"use client";

import { Upload, Scissors, Cpu, Database, MessageSquare } from "lucide-react";

const steps = [
  { icon: Upload,         label: "Upload",  desc: "PDF ingestion & extraction",            color: "text-blue-400",    bg: "bg-blue-500/10" },
  { icon: Scissors,       label: "Chunk",   desc: "Semantic splitting",                    color: "text-violet-400",  bg: "bg-violet-500/10" },
  { icon: Cpu,            label: "Embed",   desc: "Vector embeddings",                     color: "text-gold",        bg: "bg-gold/10" },
  { icon: Database,       label: "Store",   desc: "Index in Qdrant",                       color: "text-cyan-400",    bg: "bg-cyan-500/10" },
  { icon: MessageSquare,  label: "Query",   desc: "Retrieve & generate",                   color: "text-emerald-400", bg: "bg-emerald-500/10" },
];

export default function RAGFlowDiagram() {
  return (
    <div className="px-3 py-4 border-t border-border">
      <p className="text-[10px] uppercase tracking-[0.12em] text-subtle font-semibold px-3 pb-3">
        RAG Pipeline
      </p>
      <div className="space-y-0.5 px-1">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          return (
            <div key={step.label}>
              <div className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-white/[0.03] transition-colors group">
                <div className={`w-6 h-6 rounded-lg ${step.bg} flex items-center justify-center shrink-0`}>
                  <Icon className={`w-3 h-3 ${step.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-white/70 leading-none">{step.label}</p>
                  <p className="text-xs text-subtle leading-relaxed mt-0.5">{step.desc}</p>
                </div>
              </div>
              {idx < steps.length - 1 && (
                <div className="flex ml-[22px]">
                  <div className="w-px h-1.5 bg-gold/20" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
