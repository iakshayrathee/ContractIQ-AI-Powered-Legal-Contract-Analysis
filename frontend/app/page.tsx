import Link from "next/link";
import {
  Scale,
  FileSearch,
  ShieldAlert,
  MessageSquare,
  Sparkles,
  ArrowRight,
  CheckCircle,
  Zap,
  Brain,
} from "lucide-react";

const features = [
  {
    icon: FileSearch,
    title: "Two-Pass Extraction",
    description:
      "Parallel per-chunk extraction followed by LLM-powered merge for comprehensive clause identification, metadata, and obligation tracking.",
    iconColor: "text-amber-400",
    iconBg: "bg-amber-500/10",
    borderColor: "border-amber-500/20",
    glowColor: "rgba(245,158,11,0.08)",
  },
  {
    icon: ShieldAlert,
    title: "Hybrid Risk Scoring",
    description:
      "40% rule-based checks + 60% LLM analysis. Detects missing clauses, unfavorable terms, and compliance gaps with a 0–100 risk score.",
    iconColor: "text-red-400",
    iconBg: "bg-red-500/10",
    borderColor: "border-red-500/20",
    glowColor: "rgba(239,68,68,0.07)",
  },
  {
    icon: MessageSquare,
    title: "Multi-Modal RAG Chat",
    description:
      "Ask natural-language questions about your contracts with SSE streaming, source citations, and smart query caching powered by Qdrant.",
    iconColor: "text-blue-400",
    iconBg: "bg-blue-500/10",
    borderColor: "border-blue-500/20",
    glowColor: "rgba(59,130,246,0.07)",
  },
  {
    icon: Sparkles,
    title: "Plain-English Summaries",
    description:
      "Executive summary, obligations by party, key dates, watch-outs, and action items — instantly readable for non-legal stakeholders.",
    iconColor: "text-gold",
    iconBg: "bg-gold/10",
    borderColor: "border-gold/20",
    glowColor: "rgba(201,168,76,0.08)",
  },
];

const techStack = [
  { name: "GPT-4o", sub: "Vision + Chat", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  { name: "Qdrant", sub: "Vector DB", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  { name: "FastAPI", sub: "Backend", color: "text-teal-400", bg: "bg-teal-500/10", border: "border-teal-500/20" },
  { name: "PostgreSQL", sub: "Database", color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/20" },
  { name: "Next.js 14", sub: "App Router", color: "text-white", bg: "bg-white/[0.06]", border: "border-white/10" },
  { name: "Langfuse", sub: "Observability", color: "text-violet-400", bg: "bg-violet-500/10", border: "border-violet-500/20" },
];

const stats = [
  { value: "10+", label: "Clause Types Detected" },
  { value: "2-Pass", label: "LLM Extraction" },
  { value: "Hybrid", label: "Risk Scoring" },
  { value: "SSE", label: "Streaming Chat" },
];

const highlights = [
  "GPT-4o Vision for PDF parsing",
  "Async job-based ingestion pipeline",
  "Qdrant vector similarity search",
  "Real-time RAG chat with SSE",
  "Docker Compose ready",
];

export default function LandingPage() {
  return (
    <div className="min-h-full bg-primary">
      {/* ── Hero ───────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* Mesh background */}
        <div className="absolute inset-0 hero-mesh pointer-events-none" />
        {/* Subtle grid overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.025]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(201,168,76,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(201,168,76,0.4) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />

        <div className="relative max-w-5xl mx-auto px-6 pt-20 pb-24 text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-gold/30 bg-gold/[0.06] text-gold text-xs font-semibold tracking-wide mb-8 animate-in">
            <Zap className="w-3 h-3" />
            AI-Powered Legal Intelligence
          </div>

          {/* Main headline */}
          <h1
            className="font-serif text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] mb-6"
            style={{ animationDelay: "60ms" }}
          >
            <span className="text-white">Contract</span>
            <span className="gradient-accent-text-lg">IQ</span>
          </h1>
          <p
            className="text-xl sm:text-2xl font-serif text-white/70 mb-4 animate-in"
            style={{ animationDelay: "100ms" }}
          >
            Understand any legal contract in minutes.
          </p>
          <p
            className="max-w-2xl mx-auto text-base text-muted leading-relaxed mb-10 animate-in"
            style={{ animationDelay: "140ms" }}
          >
            Upload PDFs, extract clauses automatically, assess risks with hybrid AI scoring,
            and query your contracts in plain English — powered by GPT-4o, Qdrant, and FastAPI.
          </p>

          {/* CTAs */}
          <div
            className="flex flex-col sm:flex-row items-center justify-center gap-3 animate-in"
            style={{ animationDelay: "180ms" }}
          >
            <Link
              href="/login"
              className="group inline-flex items-center gap-2.5 px-7 py-3.5 rounded-xl font-semibold text-sm
                bg-gradient-gold text-[#000000] shadow-glow hover:shadow-glow-lg transition-all duration-300
                hover:scale-[1.03]"
            >
              Start Analyzing
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl font-semibold text-sm
                border border-border hover:border-gold/40 text-muted hover:text-white
                bg-card/60 hover:bg-card transition-all duration-300"
            >
              View Dashboard
            </Link>
          </div>

          {/* Highlights strip */}
          <div
            className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 mt-10 animate-in"
            style={{ animationDelay: "220ms" }}
          >
            {highlights.map((h) => (
              <span key={h} className="flex items-center gap-1.5 text-xs text-muted">
                <CheckCircle className="w-3 h-3 text-gold/70" />
                {h}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── Gold divider ──────────────────────────────────────── */}
      <div className="gold-line mx-auto max-w-3xl" />

      {/* ── Stats strip ───────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {stats.map((s, i) => (
            <div
              key={s.label}
              className="text-center p-4 bg-card border border-border rounded-xl shadow-card card-mesh animate-in"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <p className="text-2xl font-bold gradient-accent-text font-serif">{s.value}</p>
              <p className="text-xs text-muted mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features grid ─────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 py-8 pb-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl sm:text-3xl font-serif font-bold text-white mb-3">
            Everything you need to{" "}
            <span className="gradient-accent-text">understand contracts</span>
          </h2>
          <p className="text-sm text-muted max-w-xl mx-auto">
            From raw PDF to structured insights — all powered by state-of-the-art AI.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`group relative bg-card border ${f.borderColor} rounded-2xl p-6 
                shadow-card hover:shadow-card-hover transition-all duration-300 
                hover:scale-[1.015] overflow-hidden animate-in`}
              style={{
                animationDelay: `${i * 80}ms`,
                backgroundImage: `radial-gradient(ellipse 100% 80% at 50% 0%, ${f.glowColor} 0%, transparent 60%)`,
              }}
            >
              <div className={`w-11 h-11 rounded-xl ${f.iconBg} border ${f.borderColor} flex items-center justify-center mb-4 shadow-inner`}>
                <f.icon className={`w-5 h-5 ${f.iconColor}`} />
              </div>
              <h3 className="font-semibold text-white mb-2 text-[15px]">{f.title}</h3>
              <p className="text-sm text-muted leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Tech stack ────────────────────────────────────────── */}
      <section className="border-t border-border bg-surface/40 py-12">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-center text-xs font-semibold uppercase tracking-[0.15em] text-subtle mb-8">
            Built with
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {techStack.map((t) => (
              <div
                key={t.name}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl border ${t.border} ${t.bg} transition-all duration-200 hover:scale-105`}
              >
                <span className={`text-sm font-semibold ${t.color}`}>{t.name}</span>
                <span className="text-xs text-subtle">{t.sub}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="relative overflow-hidden py-20 px-6">
        <div className="absolute inset-0 hero-mesh pointer-events-none opacity-60" />
        <div className="relative max-w-2xl mx-auto text-center">
          <div className="w-16 h-16 rounded-2xl bg-gold/10 border border-gold/25 flex items-center justify-center mx-auto mb-6 shadow-glow animate-glow-pulse">
            <Scale className="w-7 h-7 text-gold" />
          </div>
          <h2 className="font-serif text-3xl sm:text-4xl font-bold text-white mb-4">
            Ready to analyze your{" "}
            <span className="gradient-accent-text">contracts?</span>
          </h2>
          <p className="text-muted text-sm mb-8 leading-relaxed">
            Upload a PDF contract and get structured analysis, risk scores, and a plain-English
            summary in under a minute.
          </p>
          <Link
            href="/login"
            className="group inline-flex items-center gap-2.5 px-8 py-4 rounded-xl font-semibold text-sm
              bg-gradient-gold text-[#000000] shadow-glow hover:shadow-glow-lg transition-all duration-300
              hover:scale-[1.04]"
          >
            <Brain className="w-4 h-4" />
            Get Started — It&apos;s Free
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────── */}
      <footer className="border-t border-border py-6 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-gradient-gold flex items-center justify-center shadow-glow-sm">
              <Scale className="w-3.5 h-3.5 text-[#06080F]" />
            </div>
            <span className="font-bold text-sm text-white">ContractIQ</span>
          </div>
          <p className="text-xs text-subtle">
            AI-powered legal contract analysis · Built with GPT-4o, Qdrant & FastAPI
          </p>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-xs text-muted hover:text-gold transition-colors">
              Login
            </Link>
            <Link href="/register" className="text-xs text-muted hover:text-gold transition-colors">
              Sign Up
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
