"use client";

import { useAnalysis } from "@/lib/hooks/useProjectQueries";
import { contractsApi } from "@/lib/api";
import type { Project, RiskItem } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { ShieldAlert, AlertTriangle, ChevronDown, ChevronRight, Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { exportToText, generateAnalysisReport } from "@/lib/export";

interface Props {
  project: Project;
}

const SEVERITY_CONFIG = {
  low: { color: "text-emerald-300", bg: "bg-emerald-500/20", border: "border-emerald-500/30", label: "Low" },
  medium: { color: "text-amber-300", bg: "bg-amber-500/20", border: "border-amber-500/30", label: "Medium" },
  high: { color: "text-orange-300", bg: "bg-orange-500/20", border: "border-orange-500/30", label: "High" },
  critical: { color: "text-red-300", bg: "bg-red-500/20", border: "border-red-500/30", label: "Critical" },
};

function ScoreGauge({ score }: { score: number }) {
  const circumference = 2 * Math.PI * 42;
  const filled = (score / 100) * circumference;
  const color = score <= 30 ? "#C9A84C" : score <= 60 ? "#f59e0b" : score <= 80 ? "#f97316" : "#ef4444";
  const trackColor = score <= 30 ? "rgba(201,168,76,0.12)" : score <= 60 ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)";

  return (
    <div className="relative w-36 h-36 mx-auto">
      <svg className="w-36 h-36 -rotate-90" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" fill="none" stroke={trackColor} strokeWidth="7" />
        <circle
          cx="50" cy="50" r="42" fill="none"
          stroke={color} strokeWidth="7"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - filled}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
          filter="url(#riskGlow)"
        />
        <defs>
          <filter id="riskGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold font-serif" style={{ color }}>{score}</span>
        <span className="text-xs text-subtle font-medium mt-0.5">/ 100</span>
      </div>
    </div>
  );
}

function RiskCard({ item }: { item: RiskItem }) {
  const [expanded, setExpanded] = useState(false);
  const sev = SEVERITY_CONFIG[item.severity] ?? SEVERITY_CONFIG.medium;

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden hover:border-border-hover transition-all duration-200">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-white/[0.02] transition-colors text-left"
      >
        <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded-md border ${sev.bg} ${sev.color} ${sev.border}`}>
          {sev.label}
        </span>
        <span className="text-sm text-white font-medium flex-1 truncate">{item.title}</span>
        {expanded ? <ChevronDown className="w-3.5 h-3.5 text-muted" /> : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-border">
          <p className="text-xs text-muted leading-relaxed mt-3">{item.description}</p>
          {item.clause_reference && (
            <p className="text-xs text-subtle">
              Related clause: <span className="text-white/70 font-mono">{item.clause_reference}</span>
            </p>
          )}
          {item.recommendation && (
            <div className="bg-surface/80 border border-border rounded-lg p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle mb-1.5">Recommendation</p>
              <p className="text-xs text-white/80 leading-relaxed">{item.recommendation}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function RiskDashboard({ project }: Props) {
  const { data: analysisData, isLoading } = useAnalysis(project.name, project.document_count > 0);

  const report = analysisData?.risk_report;

  if (isLoading) {
    return <div className="flex items-center justify-center py-12"><Spinner /></div>;
  }

  if (project.document_count === 0) {
    return (
      <div className="text-center py-16">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/[0.07] border border-amber-500/20 flex items-center justify-center mx-auto mb-4 shadow-card">
          <ShieldAlert className="w-7 h-7 text-amber-400" />
        </div>
        <p className="text-sm font-semibold text-white">No risk report available</p>
        <p className="text-xs text-muted mt-1.5">Upload a contract first to see risk assessment</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-16">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/[0.07] border border-amber-500/20 flex items-center justify-center mx-auto mb-4 shadow-card">
          <ShieldAlert className="w-7 h-7 text-amber-400" />
        </div>
        <p className="text-sm font-semibold text-white">No risk report available</p>
        <p className="text-xs text-muted mt-1.5">Run contract analysis first to see risk assessment</p>
        <div className="flex items-center justify-center gap-2 mt-3">
          <Loader2 className="w-3.5 h-3.5 text-subtle animate-spin" />
          <p className="text-xs text-subtle">Checking for results…</p>
        </div>
      </div>
    );
  }

  const severityCounts = { low: 0, medium: 0, high: 0, critical: 0 };
  report.items.forEach((item) => { severityCounts[item.severity]++; });

  const handleExport = () => {
    if (!report) return;
    const reportText = generateAnalysisReport({
      projectName: project.name,
      riskScore: report.overall_score,
      riskLevel: report.risk_level,
      summary: report.summary,
      clauses: report.items.map(item => ({ title: item.title, type: item.category })),
      missingClauses: report.missing_clauses,
      actionItems: report.items.filter(i => i.recommendation).map(i => i.recommendation),
    });
    exportToText(reportText, `${project.name}-risk-analysis`);
  };

  return (
    <div className="space-y-6">
      {/* Header with export button */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Risk Assessment</h2>
        <button
          onClick={handleExport}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
            bg-card border border-border text-muted hover:text-gold hover:border-gold/30
            transition-all focus:ring-2 focus:ring-gold/50"
          title="Export risk analysis"
        >
          <Download className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Export</span>
        </button>
      </div>

      {/* Score + Summary */}
      <div className="bg-card border border-gold/15 rounded-2xl p-6 shadow-card card-mesh">
        <div className="flex items-start gap-6">
          <div className="shrink-0">
            <ScoreGauge score={report.overall_score} />
            <p className="text-center text-xs font-semibold mt-2 capitalize" style={{
              color: report.risk_level === "low" ? "#C9A84C" :
                     report.risk_level === "medium" ? "#f59e0b" :
                     report.risk_level === "high" ? "#f97316" : "#ef4444"
            }}>
              {report.risk_level} risk
            </p>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-muted leading-relaxed mb-4">{report.summary}</p>
            {/* Severity breakdown */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(["critical", "high", "medium", "low"] as const).map((sev) => {
                const cfg = SEVERITY_CONFIG[sev];
                return (
                  <div key={sev} className={`flex items-center gap-2 px-3 py-2 rounded-xl ${cfg.bg} border ${cfg.border}`}>
                    <span className={`text-base font-bold font-serif ${cfg.color}`}>{severityCounts[sev]}</span>
                    <span className="text-xs text-muted">{cfg.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Action Items */}
      {report.items.some(item => item.recommendation) && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-amber-400 mb-3">
                Recommended Actions
              </h3>
              <ul className="space-y-2">
                {report.items
                  .filter(item => item.recommendation)
                  .slice(0, 5)
                  .map((item, i) => (
                    <li
                      key={i}
                      className="text-xs text-white/80 flex items-start gap-2"
                    >
                      <span className="text-amber-400 font-bold mt-0.5">•</span>
                      <span>{item.recommendation}</span>
                    </li>
                  ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Missing Clauses */}
      {report.missing_clauses.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.1em] text-subtle mb-3">Missing Clauses</p>
          <div className="flex flex-wrap gap-2">
            {report.missing_clauses.map((clause, i) => (
              <span key={i} className="text-xs px-3 py-1.5 rounded-lg bg-red-500/8 border border-red-500/15 text-red-400 font-medium">
                <AlertTriangle className="w-3 h-3 inline mr-1.5" />
                {clause}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Risk Items */}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle mb-3">
          Risk Items ({report.items.length})
        </p>
        <div className="space-y-2">
          {report.items.map((item, i) => (
            <RiskCard key={i} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
