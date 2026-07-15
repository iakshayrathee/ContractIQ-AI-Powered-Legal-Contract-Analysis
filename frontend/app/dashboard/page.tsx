"use client";

import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import { useState, useEffect } from "react";
import {
  Briefcase,
  FileText,
  ShieldAlert,
  TrendingUp,
  BarChart3,
  ArrowRight,
  Scale,
  Activity,
  RotateCw,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const RISK_COLORS: Record<string, string> = {
  low: "#C9A84C",
  medium: "#f59e0b",
  high: "#f97316",
  critical: "#ef4444",
};

const RISK_BG: Record<string, string> = {
  low: "bg-gold/10 text-gold border-gold/20",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/20",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/20",
  critical: "bg-red-500/15 text-red-300 border-red-500/20",
};

const BAR_COLORS = [
  "#C9A84C",
  "#F0C060",
  "#A8883A",
  "#D4B05A",
  "#E8C870",
  "#B89840",
  "#C0A050",
  "#D8B860",
];

function StatCard({
  label,
  value,
  icon: Icon,
  iconColor,
  iconBg,
  subtitle,
  accentBar,
  trend,
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  iconBg: string;
  subtitle?: string;
  accentBar?: string;
  trend?: string;
}) {
  return (
    <div className="relative bg-card border border-border rounded-2xl p-5 shadow-card hover:shadow-card-hover hover:border-border-hover transition-all duration-300 overflow-hidden card-mesh group">
      {accentBar && (
        <div className={`absolute top-0 left-0 right-0 h-0.5 ${accentBar}`} />
      )}
      <div className="flex items-start justify-between mb-4">
        <div className={`w-10 h-10 rounded-xl ${iconBg} flex items-center justify-center shadow-inner`}>
          <Icon className={`w-5 h-5 ${iconColor}`} />
        </div>
        {trend && (
          <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 rounded-full shrink-0">
            {trend}
          </span>
        )}
      </div>
      <p className="text-3xl font-bold text-white font-serif">{value}</p>
      <p className="text-xs text-muted mt-1.5 font-medium">{label}</p>
      {subtitle && (
        <p className="text-xs text-subtle mt-0.5 flex items-center gap-1">
          <Activity className="w-2.5 h-2.5 shrink-0" />
          {subtitle}
        </p>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 pt-6 sm:pt-10 pb-10 space-y-8" aria-busy="true">
      <div className="space-y-2">
        <Skeleton className="w-48 h-8" />
        <Skeleton className="w-72 h-4" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-card border border-border rounded-2xl p-5 space-y-3">
            <Skeleton className="w-10 h-10 rounded-xl" />
            <Skeleton className="w-16 h-8" />
            <Skeleton className="w-24 h-3" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        <div className="col-span-1 xl:col-span-3 bg-card border border-border rounded-2xl p-5">
          <Skeleton className="w-36 h-5 mb-5" />
          <Skeleton className="w-full h-[220px] rounded-xl" />
        </div>
        <div className="col-span-1 xl:col-span-2 bg-card border border-border rounded-2xl p-5">
          <Skeleton className="w-36 h-5 mb-5" />
          <Skeleton className="w-full h-[160px] rounded-xl" />
        </div>
      </div>
    </div>
  );
}

interface TooltipPayload {
  value: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface border border-gold/20 rounded-xl px-3.5 py-2.5 shadow-glow-sm">
      <p className="text-xs font-semibold text-white capitalize">{label?.replace(/_/g, " ")}</p>
      <p className="text-xs text-gold mt-0.5">{payload[0].value} clauses</p>
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.getStats,
  });

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    if (stats) {
      setLastUpdated(new Date());
    }
  }, [stats]);

  const handleRefresh = async () => {
    await refetch();
    setLastUpdated(new Date());
  };

  if (isLoading) return <DashboardSkeleton />;

  if (!stats) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="w-16 h-16 rounded-2xl bg-gold/10 border border-gold/20 flex items-center justify-center shadow-glow">
          <Scale className="w-7 h-7 text-gold" />
        </div>
        <p className="text-white font-semibold">No data yet</p>
        <p className="text-xs text-muted max-w-xs text-center">
          Create a project, upload a contract, and run analysis to populate the dashboard.
        </p>
        <Link
          href="/projects"
          className="mt-2 px-5 py-2.5 rounded-xl bg-gradient-gold text-[#06080F] text-xs font-bold shadow-glow hover:shadow-glow-lg transition-all"
        >
          Go to Projects
        </Link>
      </div>
    );
  }

  const clauseData = Object.entries(stats.clause_type_counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, count]) => ({ name: name.replace(/_/g, " "), count }));

  const riskPieData = (["low", "medium", "high", "critical"] as const)
    .map((level) => ({ name: level, value: stats.risk_distribution[level] ?? 0 }))
    .filter((d) => d.value > 0);

  const totalRiskItems = riskPieData.reduce((s, d) => s + d.value, 0);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 pt-6 sm:pt-10 pb-10 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight font-serif">
            Analytics <span className="gradient-accent-text">Dashboard</span>
          </h1>
          <p className="text-sm text-muted mt-1.5">Overview of all contract analyses and risk assessments</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {lastUpdated && (
            <span className="text-[10px] text-muted">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={handleRefresh}
            title="Refresh dashboard data"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card text-xs text-muted hover:text-white transition-all focus-ring"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gold/20 bg-gold/[0.05]">
            <div className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse-soft" />
            <span className="text-[11px] text-gold font-medium">Live</span>
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <StatCard
          label="Total Projects"
          value={stats.total_projects}
          icon={Briefcase}
          iconColor="text-gold"
          iconBg="bg-gold/10"
          accentBar="bg-gradient-gold"
          trend="+10%"
        />
        <StatCard
          label="Total Documents"
          value={stats.total_documents}
          icon={FileText}
          iconColor="text-blue-400"
          iconBg="bg-blue-500/10"
          accentBar="bg-gradient-to-r from-blue-500 to-cyan-500"
          trend="+25%"
        />
        <StatCard
          label="Avg Risk Score"
          value={stats.avg_risk_score}
          icon={ShieldAlert}
          iconColor={stats.avg_risk_score <= 30 ? "text-gold" : stats.avg_risk_score <= 60 ? "text-amber-400" : "text-red-400"}
          iconBg={stats.avg_risk_score <= 30 ? "bg-gold/10" : stats.avg_risk_score <= 60 ? "bg-amber-500/10" : "bg-red-500/10"}
          subtitle={stats.avg_risk_score <= 30 ? "Low risk" : stats.avg_risk_score <= 60 ? "Medium risk" : "High risk"}
          accentBar={stats.avg_risk_score <= 30 ? "bg-gradient-to-r from-gold/40 to-gold" : stats.avg_risk_score <= 60 ? "bg-gradient-to-r from-amber-500 to-orange-400" : "bg-gradient-to-r from-red-500 to-orange-500"}
          trend="-4.2%"
        />
        <StatCard
          label="Analyses Done"
          value={stats.recent_analyses.length}
          icon={TrendingUp}
          iconColor="text-gold"
          iconBg="bg-gold/10"
          accentBar="bg-gradient-gold"
          trend="+18%"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        {/* Clause Types Bar Chart */}
        <div className="col-span-1 xl:col-span-3 bg-card border border-border rounded-2xl p-5 shadow-card card-mesh">
          <div className="flex items-center gap-2.5 mb-5">
            <div className="w-7 h-7 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center">
              <BarChart3 className="w-3.5 h-3.5 text-gold" />
            </div>
            <h2 className="text-sm font-semibold text-white">Clause Types</h2>
            <span className="text-[10px] text-subtle ml-auto px-2 py-0.5 rounded-md bg-white/[0.04] border border-border">
              Top 8 by frequency
            </span>
          </div>
          {clauseData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={clauseData} layout="vertical" margin={{ left: 10, right: 20, top: 0, bottom: 0 }}>
                <XAxis
                  type="number"
                  tick={{ fill: "#6B6F8A", fontSize: 10 }}
                  tickLine={false}
                  axisLine={{ stroke: "#1A1D2E" }}
                  allowDecimals={false}
                />
                <YAxis
                  dataKey="name"
                  type="category"
                  tick={{ fill: "#8A8FA8", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  width={110}
                />
                <RechartsTooltip content={<CustomTooltip />} cursor={{ fill: "rgba(201,168,76,0.05)" }} />
                <Bar dataKey="count" radius={[0, 5, 5, 0]} maxBarSize={18}>
                  {clauseData.map((_, i) => (
                    <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-[220px] gap-2">
              <BarChart3 className="w-8 h-8 text-subtle" />
              <p className="text-xs text-subtle">No clauses extracted yet</p>
            </div>
          )}
        </div>

        {/* Risk Distribution Pie Chart */}
        <div className="col-span-1 xl:col-span-2 bg-card border border-border rounded-2xl p-5 shadow-card card-mesh">
          <div className="flex items-center gap-2.5 mb-5">
            <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <h2 className="text-sm font-semibold text-white">Risk Distribution</h2>
          </div>
          {totalRiskItems > 0 ? (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie
                    data={riskPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                    strokeWidth={0}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {riskPieData.map((entry) => (
                      <Cell key={entry.name} fill={RISK_COLORS[entry.name]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap justify-center gap-2 mt-4">
                {(["low", "medium", "high", "critical"] as const).map((level) => {
                  const count = stats.risk_distribution[level] ?? 0;
                  if (count === 0) return null;
                  return (
                    <div key={level} className={`flex items-center gap-1.5 text-[10px] font-semibold border rounded-full px-2.5 py-1 ${RISK_BG[level]}`}>
                      <span className="capitalize">{level}</span>
                      <span className="font-bold">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-[160px] gap-2">
              <ShieldAlert className="w-8 h-8 text-subtle" />
              <p className="text-xs text-subtle">No risk data yet</p>
            </div>
          )}
        </div>
      </div>

      {/* Recent Analyses - Desktop */}
      {stats.recent_analyses.length > 0 && (
        <>
          <div className="hidden sm:block bg-card border border-border rounded-2xl shadow-card overflow-hidden">
            <div className="px-5 py-4 border-b border-border flex items-center gap-2.5">
              <div className="w-6 h-6 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center">
                <TrendingUp className="w-3 h-3 text-gold" />
              </div>
              <h2 className="text-sm font-semibold text-white">Recent Analyses</h2>
              <span className="ml-auto text-xs text-subtle">{stats.recent_analyses.length} records</span>
            </div>
            <div className="divide-y divide-border">
              {stats.recent_analyses.map((item, i) => (
                <Link
                  key={i}
                  href={`/projects/${encodeURIComponent(item.project_name)}`}
                  className="flex items-center justify-between px-5 py-3.5 hover:bg-gold/[0.03] transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-surface border border-border flex items-center justify-center group-hover:border-gold/20 group-hover:bg-gold/[0.05] transition-all">
                      <Briefcase className="w-3.5 h-3.5 text-muted group-hover:text-gold transition-colors" />
                    </div>
                    <div>
                      <span className="text-sm font-medium text-white group-hover:text-gold transition-colors">{item.project_name}</span>
                      <p className="text-xs text-subtle">
                        {new Date(item.created_at).toLocaleDateString("en-US", {
                          month: "short", day: "numeric", year: "numeric",
                        })}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                      item.risk_score <= 30 ? RISK_BG.low :
                      item.risk_score <= 60 ? RISK_BG.medium :
                      item.risk_score <= 80 ? RISK_BG.high :
                      RISK_BG.critical
                    }`}>
                      Score {item.risk_score}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 text-gold opacity-0 group-hover:opacity-100 transition-all" />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Recent Analyses - Mobile Cards */}
          <div className="sm:hidden space-y-2">
            <div className="flex items-center gap-2.5 px-4 py-3">
              <div className="w-6 h-6 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center">
                <TrendingUp className="w-3 h-3 text-gold" />
              </div>
              <h2 className="text-sm font-semibold text-white">Recent Analyses</h2>
              <span className="ml-auto text-[10px] text-subtle">{stats.recent_analyses.length}</span>
            </div>
            {stats.recent_analyses.map((item, i) => (
              <Link
                key={i}
                href={`/projects/${encodeURIComponent(item.project_name)}`}
                className="block bg-card border border-border rounded-xl p-4 hover:border-gold/20 hover:bg-gold/[0.02] transition-all"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="text-sm font-medium text-white truncate">
                    {item.project_name}
                  </h3>
                  <span className={`text-[10px] font-semibold px-2 py-1 rounded-full border shrink-0 ${
                    item.risk_score <= 30 ? RISK_BG.low :
                    item.risk_score <= 60 ? RISK_BG.medium :
                    item.risk_score <= 80 ? RISK_BG.high :
                    RISK_BG.critical
                  }`}>
                    {item.risk_score}
                  </span>
                </div>
                <p className="text-[11px] text-muted">
                  {new Date(item.created_at).toLocaleDateString("en-US", {
                    month: "short", day: "numeric", year: "numeric",
                  })}
                </p>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
