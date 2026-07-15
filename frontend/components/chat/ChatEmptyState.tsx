"use client";

import type { Project } from "@/lib/types";
import { Scale, UploadCloud } from "lucide-react";

interface Props {
  project: Project;
  onSuggestionClick?: (text: string) => void;
}

const SUGGESTIONS = [
  "What are the key obligations in this contract?",
  "Summarize the main risk factors",
  "What are the termination clauses?",
  "List all dates and deadlines",
];

export default function ChatEmptyState({ project, onSuggestionClick }: Props) {
  const hasDocuments = project.document_count > 0;

  return (
    <div className="h-full flex flex-col items-center justify-center text-center px-8 py-12 gap-6 max-w-lg mx-auto">
      {hasDocuments ? (
        <>
          <div className="w-16 h-16 rounded-2xl bg-gold/[0.08] border border-gold/25 flex items-center justify-center shadow-glow animate-glow-pulse">
            <Scale className="w-7 h-7 text-gold" />
          </div>
          <div>
            <p className="text-lg font-semibold text-white font-serif">Ask your contract</p>
            <p className="text-sm text-muted mt-1.5 leading-relaxed">
              <span className="font-semibold text-gold">{project.document_count}</span> document{project.document_count !== 1 ? "s" : ""} indexed. Ask anything in plain English.
            </p>
          </div>
          <div className="w-full grid grid-cols-2 gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestionClick?.(s)}
                className="text-left text-xs text-muted px-3.5 py-3 rounded-xl border border-gold/15 bg-gold/[0.04] hover:bg-gold/[0.08] hover:text-white hover:border-gold/30 transition-all leading-relaxed"
              >
                {s}
              </button>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="w-16 h-16 rounded-2xl bg-card border border-border flex items-center justify-center shadow-card">
            <UploadCloud className="w-7 h-7 text-subtle" />
          </div>
          <div>
            <p className="text-lg font-semibold text-white">No documents yet</p>
            <p className="text-sm text-muted mt-1.5 leading-relaxed">
              Upload PDFs using the Knowledge Base panel on the right to get started.
            </p>
          </div>
          <div className="mt-2 w-full text-left space-y-2">
            {[
              "PDF uploaded and text extracted",
              "Content split into searchable chunks",
              "Chunks converted to vector embeddings",
              "Everything indexed and ready to search",
            ].map((step, i) => (
              <div key={i} className="flex items-center gap-3 px-3.5 py-2.5 bg-card/60 rounded-xl border border-border">
                <span className="w-6 h-6 rounded-full bg-gold/10 flex items-center justify-center text-[10px] font-bold text-gold shrink-0 border border-gold/20">
                  {i + 1}
                </span>
                <span className="text-xs text-muted">{step}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
