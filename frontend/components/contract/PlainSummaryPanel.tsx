"use client";

import { useAnalysis } from "@/lib/hooks/useProjectQueries";
import { contractsApi } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Spinner } from "@/components/ui/Spinner";
import { FileText, Users, Calendar, AlertTriangle, CheckCircle2, Copy, Check, Loader2 } from "lucide-react";
import { useState } from "react";

interface Props {
  project: Project;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <Check className="w-3 h-3 text-emerald-400" />
      ) : (
        <Copy className="w-3 h-3 text-muted" />
      )}
    </button>
  );
}

function Section({ title, icon: Icon, iconColor, children, copyText }: {
  title: string;
  icon: any;
  iconColor: string;
  children: React.ReactNode;
  copyText?: string;
}) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4 shadow-card card-mesh gold-border-left">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-5 h-5 rounded-md flex items-center justify-center`} style={{ background: 'rgba(201,168,76,0.1)' }}>
            <Icon className={`w-3 h-3 ${iconColor}`} />
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-subtle">{title}</span>
        </div>
        {copyText && <CopyButton text={copyText} />}
      </div>
      {children}
    </div>
  );
}

export default function PlainSummaryPanel({ project }: Props) {
  const { data: analysisData, isLoading } = useAnalysis(project.name, project.document_count > 0);

  const summary = analysisData?.summary;

  if (isLoading) {
    return <div className="flex items-center justify-center py-12"><Spinner /></div>;
  }

  if (project.document_count === 0) {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 rounded-2xl bg-gold/[0.07] border border-gold/20 flex items-center justify-center mx-auto mb-4 shadow-glow">
          <FileText className="w-7 h-7 text-gold" />
        </div>
        <p className="text-sm font-semibold text-white">No summary available</p>
        <p className="text-xs text-muted mt-1.5">Upload a contract first to see plain summary</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 rounded-2xl bg-gold/[0.07] border border-gold/20 flex items-center justify-center mx-auto mb-4 shadow-glow">
          <FileText className="w-7 h-7 text-gold" />
        </div>
        <p className="text-sm font-semibold text-white">No summary available</p>
        <p className="text-xs text-muted mt-1.5">Run contract analysis first to see plain summary</p>
        <div className="flex items-center justify-center gap-2 mt-3">
          <Loader2 className="w-3.5 h-3.5 text-subtle animate-spin" />
          <p className="text-xs text-subtle">Checking for results…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Executive Summary */}
      <Section title="Executive Summary" icon={FileText} iconColor="text-gold" copyText={summary.executive_summary}>
        <p className="text-sm text-white/80 leading-relaxed">{summary.executive_summary}</p>
      </Section>

      {/* What This Does */}
      {summary.what_this_does && (
        <Section title="What This Contract Does" icon={FileText} iconColor="text-blue-400" copyText={summary.what_this_does}>
          <p className="text-sm text-white/80 leading-relaxed">{summary.what_this_does}</p>
        </Section>
      )}

      {/* Obligations by Party */}
      {Object.keys(summary.obligations_by_party).length > 0 && (
        <Section title="Obligations by Party" icon={Users} iconColor="text-emerald-400">
          <div className="space-y-3">
            {Object.entries(summary.obligations_by_party).map(([party, obligations]) => (
              <div key={party}>
                <p className="text-xs font-semibold text-white mb-1.5">{party}</p>
                <ul className="space-y-1">
                  {obligations.map((ob, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-muted">
                      <span className="w-1 h-1 rounded-full bg-subtle mt-1.5 shrink-0" />
                      {ob}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Key Dates */}
      {summary.key_dates.length > 0 && (
        <Section title="Key Dates" icon={Calendar} iconColor="text-amber-400">
          <ul className="space-y-1.5">
            {summary.key_dates.map((date, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/80">
                <Calendar className="w-3 h-3 text-amber-400 mt-0.5 shrink-0" />
                {date}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Watch Out For */}
      {summary.watch_out_for.length > 0 && (
        <Section title="Watch Out For" icon={AlertTriangle} iconColor="text-red-400">
          <ul className="space-y-1.5">
            {summary.watch_out_for.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/80">
                <AlertTriangle className="w-3 h-3 text-red-400 mt-0.5 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Action Items */}
      {summary.action_items.length > 0 && (
        <Section title="Action Items" icon={CheckCircle2} iconColor="text-emerald-400">
          <ul className="space-y-1.5">
            {summary.action_items.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/80">
                <CheckCircle2 className="w-3 h-3 text-emerald-400 mt-0.5 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
