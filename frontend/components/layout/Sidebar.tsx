"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjects } from "@/lib/hooks/useProjectQueries";
import type { Project } from "@/lib/types";
import { useEffect, useState } from "react";
import CreateProjectModal from "@/components/projects/CreateProjectModal";
import RAGFlowDiagram from "./RAGFlowDiagram";
import { Scale, Folder, Plus, LayoutDashboard, Menu, X, Home, LogOut, User } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, user } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const { data: projects = [] } = useProjects();

  const isDashboard = pathname === "/dashboard";
  const isProjects = pathname === "/projects";

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await logout();
      router.push("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      setLoggingOut(false);
    }
  };

  const navLinkClass = (active: boolean) =>
    `w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
      active
        ? "bg-gold/[0.08] text-gold border border-gold/20 shadow-glow-sm"
        : "text-muted hover:text-white hover:bg-white/[0.04]"
    }`;

  const sidebarContent = (onLinkClick?: () => void) => (
    <div className="flex flex-col h-full">
      {/* ── Brand ── */}
      <div className="flex items-center gap-3 px-5 h-16 border-b border-border shrink-0">
        <Link href="/" onClick={onLinkClick} className="flex items-center gap-3 min-w-0 group flex-1">
          <div className="w-8 h-8 rounded-xl bg-gradient-gold flex items-center justify-center shadow-glow-sm transition-all duration-300 group-hover:shadow-glow">
            <Scale className="w-4 h-4 text-[#06080F]" />
          </div>
          <div>
            <span className="font-bold text-[15px] text-white tracking-tight font-serif">ContractIQ</span>
            <p className="text-xs text-subtle leading-none mt-0.5">AI Legal Intelligence</p>
          </div>
        </Link>
        {onLinkClick && (
          <button
            onClick={onLinkClick}
            aria-label="Close navigation"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-muted hover:text-white hover:bg-white/[0.06] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── Navigation ── */}
      <div className="px-3 pt-4 pb-2 space-y-1">
        <Link
          href="/dashboard"
          onClick={onLinkClick}
          className={navLinkClass(isDashboard)}
        >
          <LayoutDashboard className={`w-4 h-4 ${isDashboard ? "text-gold" : ""}`} />
          Dashboard
        </Link>
        <Link
          href="/projects"
          onClick={onLinkClick}
          className={navLinkClass(isProjects)}
        >
          <Folder className={`w-4 h-4 ${isProjects ? "text-gold" : ""}`} />
          Projects
        </Link>
        <button
          onClick={() => { setCreateOpen(true); onLinkClick?.(); }}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium
            border border-gold/20 text-gold/80 hover:text-gold hover:bg-gold/[0.06] hover:border-gold/35
            transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          New Project
        </button>
      </div>

      {/* ── Divider ── */}
      <div className="mx-4 my-1 gold-line" />

      {/* ── Project list ── */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 min-h-0">
        <p className="text-[10px] uppercase tracking-[0.14em] text-subtle font-semibold px-3 mb-2.5">
          Projects
        </p>
        {projects.length === 0 ? (
          <div className="px-3 py-4 text-center">
            <p className="text-xs text-subtle">No projects yet</p>
            <p className="text-xs text-subtle/60 mt-1">Create one to get started</p>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {projects.map((p) => {
              const href = `/projects/${encodeURIComponent(p.name)}`;
              const active = pathname.startsWith(href);
              return (
                <li key={p.name}>
                  <Link
                    href={href}
                    onClick={onLinkClick}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-[13px] transition-all duration-200
                      ${active
                        ? "bg-gold/[0.08] text-gold font-medium border border-gold/20 shadow-glow-sm"
                        : "text-muted hover:text-white hover:bg-white/[0.04]"
                      }`}
                  >
                    <Folder className={`w-3.5 h-3.5 shrink-0 ${active ? "text-gold" : ""}`} />
                    <span className="truncate flex-1">{p.name}</span>
                    {p.document_count > 0 && (
                      <span className={`text-[10px] font-semibold rounded-md px-1.5 py-0.5 shrink-0 ${
                        active
                          ? "bg-gold/15 text-gold"
                          : "bg-white/[0.06] text-subtle"
                      }`}>
                        {p.document_count}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* ── RAG Pipeline ── */}
      <div className="shrink-0">
        <RAGFlowDiagram />
      </div>

      {/* ── Bottom strip ── */}
      <div className="px-4 py-3 border-t border-border shrink-0 space-y-2">
        {user && (
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-surface/50 border border-border/50 mb-2">
            <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
              <User className="w-4 h-4 text-gold" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-white truncate">{user.email}</p>
              <p className="text-[10px] text-subtle">Signed in</p>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          disabled={loggingOut}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-xs text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loggingOut ? (
            <>
              <svg className="animate-spin w-3 h-3" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Logging out…
            </>
          ) : (
            <>
              <LogOut className="w-3 h-3" />
              Logout
            </>
          )}
        </button>
        <Link
          href="/"
          onClick={onLinkClick}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-subtle hover:text-gold transition-colors"
        >
          <Home className="w-3 h-3" />
          Back to Home
        </Link>
      </div>
    </div>
  );

  return (
    <>
      {/* ── Desktop sidebar ── */}
      <aside className="hidden md:flex w-64 h-screen flex-col bg-surface/80 backdrop-blur-xl border-r border-border shrink-0">
        {sidebarContent()}
      </aside>

      {/* ── Mobile top bar ── */}
      <header className="md:hidden fixed top-0 inset-x-0 z-40 h-14 flex items-center gap-3 px-4 bg-surface/95 backdrop-blur-xl border-b border-border">
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={mobileOpen}
          className="w-10 h-10 flex items-center justify-center rounded-xl text-muted hover:text-gold hover:bg-gold/[0.06] transition-colors focus-ring"
        >
          <Menu className="w-5 h-5" />
        </button>
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-7 h-7 rounded-lg bg-gradient-gold flex items-center justify-center shadow-glow-sm">
            <Scale className="w-3.5 h-3.5 text-[#06080F]" />
          </div>
          <span className="font-bold text-sm text-white tracking-tight font-serif">ContractIQ</span>
        </Link>
      </header>

      {/* ── Mobile drawer ── */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-50 flex"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          <div
            className="absolute inset-0 bg-primary/80 backdrop-blur-sm fade-in"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative z-10 w-72 max-w-[85vw] h-full flex flex-col bg-surface/98 backdrop-blur-xl border-r border-border slide-in-from-right-5">
            {sidebarContent(() => setMobileOpen(false))}
          </aside>
        </div>
      )}

      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
