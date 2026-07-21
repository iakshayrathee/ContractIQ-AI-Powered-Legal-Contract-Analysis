"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { contractsApi } from "@/lib/api";
import { useAnalysis } from "@/lib/hooks/useProjectQueries";
import type { Project, ContractClause } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import {
  Shield,
  FileSearch,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Scale,
  Calendar,
  Users,
  MapPin,
  Lock,
  XCircle,
  DollarSign,
  Landmark,
  Cpu,
  Eye,
  EyeOff,
  ShieldCheck,
  HelpCircle,
  CheckCircle2,
  Circle,
  Loader2,
} from "lucide-react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useState } from "react";

const CLAUSE_COLORS: Record<string, string> = {
  confidentiality: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  termination: "bg-red-500/20 text-red-300 border-red-500/30",
  indemnification: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  liability: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  payment: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  governing_law: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  intellectual_property: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  data_privacy: "bg-pink-500/20 text-pink-300 border-pink-500/30",
  non_compete: "bg-rose-500/20 text-rose-300 border-rose-500/30",
  warranty: "bg-teal-500/20 text-teal-300 border-teal-500/30",
};

const CLAUSE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  confidentiality: Lock,
  termination: XCircle,
  indemnification: AlertTriangle,
  liability: Shield,
  payment: DollarSign,
  governing_law: Landmark,
  intellectual_property: Cpu,
  data_privacy: EyeOff,
  non_compete: Eye,
  warranty: ShieldCheck,
};

// Pipeline step definitions for the progress indicator (WS-2.4)
const PIPELINE_STEPS = [
  { key: "extracting_clauses", label: "Extracting clauses" },
  { key: "assessing_risk",     label: "Assessing risk" },
  { key: "writing_summary",    label: "Writing summary" },
  { key: "reviewing_quality",  label: "Reviewing quality" },
] as const;

type StageKey = typeof PIPELINE_STEPS[number]["key"] | "completed" | "failed";

interface StageIndicatorProps {
  stage: { stage: StageKey; processed?: number; total?: number } | null | undefined;
}

function StageIndicator({ stage }: StageIndicatorProps) {
  const currentIdx = stage
    ? PIPELINE_STEPS.findIndex((s) => s.key === stage.stage)
    : -1;

  return (
    <div className="flex flex-col gap-3 w-full">
      {PIPELINE_STEPS.map((step, idx) => {
        const isDone    = currentIdx > idx;
        const isActive  = currentIdx === idx;

        return (
          <div key={step.key} className="flex items-center gap-3">
            <div className="shrink-0 w-5 h-5 flex items-center justify-center">
              {isDone ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              ) : isActive ? (
                <Loader2 className="w-4 h-4 text-gold animate-spin" />
              ) : (
                <Circle className="w-4 h-4 text-white/20" />
              )}
            </div>
            <span
              className={`text-sm ${
                isDone   ? "text-emerald-400" :
                isActive ? "text-gold font-medium" :
                           "text-white/30"
              }`}
            >
              {step.label}
              {isActive && step.key === "extracting_clauses" && stage?.total
                ? ` ${stage.processed ?? 0}/${stage.total}`
                : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ClauseCard({ clause }: { clause: ContractClause }) {
  const [expanded, setExpanded] = useState(false);
  const colors = CLAUSE_COLORS[clause.clause_type] ?? "bg-white/5 text-muted border-border";
  const IconComponent = CLAUSE_ICONS[clause.clause_type] || HelpCircle;

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden hover:border-gold/20 hover:shadow-card-hover transition-all duration-200">
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-white/[0.02] transition-colors text-left group"
      >
        <span className={`inline-flex items-center gap-1.5 text-xs font-semibold uppercase px-3 py-1.5 rounded-lg border ${colors}`}>
          <IconComponent className="w-3.5 h-3.5 shrink-0" />
          {clause.clause_type.replace(/_/g, " ")}
        </span>
        <span className="text-sm text-white font-medium flex-1 truncate group-hover:text-gold transition-colors">
          {clause.title}
        </span>
        {clause.section_reference && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-white/5 border border-white/10 rounded-lg" title="Section where this clause appears in the contract">
            <FileSearch className="w-3 h-3 text-gold" />
            <span className="text-xs text-white/80">Section {clause.section_reference}</span>
          </div>
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted group-hover:text-gold transition-colors" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted group-hover:text-gold transition-colors" />
        )}
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border">
          <p className="text-xs text-muted leading-relaxed mt-3">{clause.text}</p>
          {clause.obligations.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">Obligations</p>
              {clause.obligations.map((ob, i) => (
                <div key={i} className="flex items-start gap-3 text-xs bg-surface/60 border border-border/50 rounded-lg p-3">
                  <span className={`shrink-0 px-2 py-1 rounded text-[10px] font-bold ${
                    ob.type === "must" ? "bg-red-500/20 text-red-300 border border-red-500/30" :
                    ob.type === "must_not" ? "bg-orange-500/20 text-orange-300 border border-orange-500/30" :
                    "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  }`}>
                    {ob.type.replace(/_/g, " ").toUpperCase()}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white">{ob.party}</p>
                    <p className="text-xs text-muted mt-1">{ob.description}</p>
                    {ob.deadline && <p className="text-[10px] text-subtle mt-1.5 flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-gold" />
                      Due: {ob.deadline}
                    </p>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface Props {
  project: Project;
}

export default function ContractAnalysisPanel({ project }: Props) {
  const qc = useQueryClient();
  
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const typeFilter = searchParams.get("filter") || "";

  const setTypeFilter = (filter: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (filter) {
      params.set("filter", filter);
    } else {
      params.delete("filter");
    }
    router.replace(`${pathname}?${params.toString()}`);
  };

  const { data: analysisData, isLoading } = useAnalysis(project.name, project.document_count > 0);

  const status = analysisData?.status ?? "none";
  const stage = analysisData?.stage as StageIndicatorProps["stage"] | undefined;

  // Analysis hook handles polling automatically - no manual effect needed

  const analyzeMutation = useMutation({
    mutationFn: () => contractsApi.analyze(project.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["analysis", project.name] });
      // Also reset risk/summary so they start polling for the new analysis
      qc.invalidateQueries({ queryKey: ["risks", project.name] });
      qc.invalidateQueries({ queryKey: ["summary", project.name] });
    },
  });

  const analysis = analysisData?.analysis;

  const filteredClauses = analysis?.clauses?.filter(
    (c) => !typeFilter || c.clause_type === typeFilter
  ) ?? [];

  const clauseTypes = [...new Set(analysis?.clauses?.map((c) => c.clause_type) ?? [])];

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-6 h-16 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center">
            <FileSearch className="w-4 h-4 text-gold" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Contract Analysis</h2>
            <p className="text-xs text-muted">Two-pass clause extraction with GPT-4o</p>
          </div>
        </div>
        <button
          onClick={() => analyzeMutation.mutate()}
          disabled={status === "running" || analyzeMutation.isPending || project.document_count === 0}
          className="px-4 py-2 text-xs font-bold rounded-xl bg-gradient-gold text-[#000000]
            shadow-glow-sm hover:shadow-glow focus:outline-none focus:ring-2 focus:ring-gold/50 focus:ring-offset-2 focus:ring-offset-primary
            disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none transition-all duration-200"
        >
          {status === "running" ? "Analyzing…" : "Analyze Contract"}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {isLoading && (
          <div className="flex items-center justify-center py-12"><Spinner /></div>
        )}

        {status === "running" && (
          <div className="space-y-5">
            {/* Step indicator */}
            <div className="p-5 bg-gold/[0.05] border border-gold/20 rounded-xl">
              <div className="flex items-center gap-3 mb-4">
                <Spinner />
                <div>
                  <p className="text-sm font-semibold text-gold">Analysis in progress</p>
                  <p className="text-xs text-muted mt-0.5">Results appear as each stage completes</p>
                </div>
              </div>
              <StageIndicator stage={stage} />
            </div>

            {/* WS-2.3: Render partial results as they arrive while still running */}
            {analysis && (
              <div className="space-y-6 opacity-90">
                {/* Metadata */}
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { icon: Scale, color: "text-gold", bg: "bg-gold/10", border: "border-gold/20", label: "Contract Type", value: analysis.metadata.contract_type },
                    { icon: Users, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20", label: "Parties", value: analysis.metadata.parties.join(", ") || "Unknown" },
                  ].map(({ icon: Icon, color, bg, border, label, value }) => (
                    <div key={label} className={`bg-card border ${border} rounded-xl p-4 shadow-card gold-border-left`}>
                      <div className="flex items-center gap-2 mb-2.5">
                        <div className={`w-6 h-6 rounded-lg ${bg} flex items-center justify-center`}>
                          <Icon className={`w-3 h-3 ${color}`} />
                        </div>
                        <span className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">{label}</span>
                      </div>
                      <p className="text-sm text-white font-medium capitalize">{value}</p>
                    </div>
                  ))}
                </div>

                {/* Partial clauses */}
                {analysis.clauses && analysis.clauses.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle mb-3">
                      Clauses found so far ({analysis.clauses.length})
                    </p>
                    <div className="space-y-2">
                      {analysis.clauses.filter((c) => !typeFilter || c.clause_type === typeFilter).map((clause, i) => (
                        <ClauseCard key={i} clause={clause} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {status === "none" && !isLoading && (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-2xl bg-gold/[0.07] border border-gold/20 flex items-center justify-center mx-auto mb-4 shadow-glow">
              <FileSearch className="w-7 h-7 text-gold" />
            </div>
            <p className="text-sm font-semibold text-white">No analysis yet</p>
            <p className="text-xs text-muted mt-1.5 max-w-xs mx-auto leading-relaxed">
              {project.document_count > 0
                ? 'Click "Analyze Contract" to extract clauses, identify risks, and generate a summary'
                : "Upload a contract first, then analyze"}
            </p>
          </div>
        )}

        {status === "completed" && analysis && (
          <div className="space-y-6">
            {/* Multi-document coverage notice (WS-3.4) */}
            {project.document_count > 1 && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/[0.08] border border-blue-500/20 text-xs text-blue-300">
                <Shield className="w-3.5 h-3.5 shrink-0 text-blue-400" />
                Analysis covers all {project.document_count} uploaded documents as a combined corpus.
              </div>
            )}

            {/* Metadata */}
            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: Scale, color: "text-gold", bg: "bg-gold/10", border: "border-gold/20", label: "Contract Type", value: analysis.metadata.contract_type },
                { icon: Users, color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20", label: "Parties", value: analysis.metadata.parties.join(", ") || "Unknown" },
                {
                  icon: Calendar, color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", label: "Dates",
                  value: analysis.metadata.effective_date
                    ? `${analysis.metadata.effective_date}${analysis.metadata.expiration_date ? ` → ${analysis.metadata.expiration_date}` : ""}`
                    : "Not specified"
                },
                { icon: MapPin, color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20", label: "Jurisdiction", value: analysis.metadata.governing_law || analysis.metadata.jurisdiction || "Not specified" },
              ].map(({ icon: Icon, color, bg, border, label, value }) => (
                <div key={label} className={`bg-card border ${border} rounded-xl p-4 shadow-card gold-border-left`}>
                  <div className="flex items-center gap-2 mb-2.5">
                    <div className={`w-6 h-6 rounded-lg ${bg} flex items-center justify-center`}>
                      <Icon className={`w-3 h-3 ${color}`} />
                    </div>
                    <span className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">{label}</span>
                  </div>
                  <p className="text-sm text-white font-medium capitalize">{value}</p>
                </div>
              ))}
            </div>

            {/* Summary */}
            {analysis.summary && (
              <div className="bg-card border border-border rounded-xl p-5 shadow-card">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle mb-2.5">Executive Summary</p>
                <p className="text-sm text-white/80 leading-relaxed">{analysis.summary}</p>
              </div>
            )}

            {/* Clauses */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle">
                  Clauses ({filteredClauses.length})
                </p>
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="text-sm bg-card border border-border text-white/80 rounded-lg px-3 py-2
                    focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 transition-all cursor-pointer"
                >
                  <option value="">All types</option>
                  {clauseTypes.map((t) => (
                    <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
              
              {/* Legend */}
              <div className="mb-4 p-3 bg-white/[0.02] border border-white/5 rounded-lg">
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-gold font-semibold">§</span>
                    <span className="text-muted">= Section number in contract</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded text-[10px] font-semibold">TYPE</span>
                    <span className="text-muted">= Clause category</span>
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                {filteredClauses.map((clause, i) => (
                  <ClauseCard key={i} clause={clause} />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
