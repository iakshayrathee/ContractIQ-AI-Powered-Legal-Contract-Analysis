"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import type { Project } from "@/lib/types";
import ProjectCard from "./ProjectCard";
import CreateProjectModal from "./CreateProjectModal";
import { Button } from "@/components/ui/Button";
import { ProjectCardSkeleton } from "@/components/ui/Skeleton";
import { Search, Plus, FolderOpen, FileText, CheckCircle } from "lucide-react";

export default function ProjectsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"date" | "name" | "docs">("date");

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description.toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === "name") {
      return a.name.localeCompare(b.name);
    }
    if (sortBy === "docs") {
      return b.document_count - a.document_count;
    }
    // Default: Sort by date (newest first)
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  });

  const totalDocs = projects.reduce((s, p) => s + p.document_count, 0);
  const readyCount = projects.filter(p => p.document_count > 0).length;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 pt-6 sm:pt-10 pb-10">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight font-serif">
            My <span className="gradient-accent-text">Projects</span>
          </h1>
          <p className="text-sm text-muted mt-1.5">
            Upload contracts, run AI analysis, and query your knowledge bases
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} size="sm">
          <Plus className="w-4 h-4" />
          New Project
        </Button>
      </div>

      {/* Stats row */}
      {!isLoading && projects.length > 0 && (
        <div className="flex flex-wrap gap-3 mb-8">
          <div className="flex items-center gap-2.5 px-4 py-2.5 bg-gold/[0.06] border border-gold/20 rounded-xl shadow-glow-sm">
            <div className="w-7 h-7 rounded-lg bg-gold/10 flex items-center justify-center">
              <FolderOpen className="w-3.5 h-3.5 text-gold" />
            </div>
            <div>
              <p className="text-base font-bold text-gold leading-none font-serif">{projects.length}</p>
              <p className="text-[10px] text-subtle mt-0.5">Projects</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 px-4 py-2.5 bg-blue-500/[0.06] border border-blue-500/20 rounded-xl">
            <div className="w-7 h-7 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <FileText className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <div>
              <p className="text-base font-bold text-blue-400 leading-none font-serif">{totalDocs}</p>
              <p className="text-[10px] text-subtle mt-0.5">Documents</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 px-4 py-2.5 bg-emerald-500/[0.06] border border-emerald-500/20 rounded-xl">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            </div>
            <div>
              <p className="text-base font-bold text-emerald-400 leading-none font-serif">{readyCount}</p>
              <p className="text-[10px] text-subtle mt-0.5">Ready</p>
            </div>
          </div>
        </div>
      )}

      {/* Search & Sort controls */}
      {projects.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="relative flex-1">
            <label htmlFor="project-search" className="sr-only">Search projects</label>
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-subtle pointer-events-none" aria-hidden="true" />
            <input
              id="project-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search projects..."
              className="w-full bg-card border border-border rounded-xl pl-10 pr-4 py-2.5 text-sm
                text-white placeholder-subtle focus:outline-none focus:ring-2 focus:ring-gold/50
                focus:border-gold/60 focus:bg-gold/[0.04] shadow-card transition-all"
            />
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "date" | "name" | "docs")}
              className="text-xs bg-card border border-border text-white/80 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-gold/50 cursor-pointer"
            >
              <option value="date">Sort by: Date (Newest)</option>
              <option value="name">Sort by: Name (A-Z)</option>
              <option value="docs">Sort by: Documents (Most)</option>
            </select>
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <ProjectCardSkeleton key={i} />)}
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-20 h-20 mb-6 rounded-2xl bg-gold/[0.08] border border-gold/20 flex items-center justify-center shadow-glow animate-glow-pulse">
            {search ? (
              <Search className="w-8 h-8 text-gold" />
            ) : (
              <FolderOpen className="w-8 h-8 text-gold" />
            )}
          </div>
          <h2 className="text-lg font-semibold text-white mb-2 font-serif">
            {search ? "No matching projects" : "No projects yet"}
          </h2>
          <p className="text-sm text-muted mb-8 max-w-sm leading-relaxed">
            {search
              ? "Try a different search term."
              : "Create a project, upload contract PDFs, and let AI analyze them."
            }
          </p>
          {!search && (
            <Button onClick={() => setCreateOpen(true)} size="sm">
              <Plus className="w-4 h-4" />
              Create your first project
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((p) => <ProjectCard key={p.name} project={p} />)}
        </div>
      )}

      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
