"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import type { ChunkItem, ChunksResponse } from "@/lib/types";
import ChunkCard from "./ChunkCard";
import ChunkDetailPanel from "./ChunkDetailPanel";
import { Spinner } from "@/components/ui/Spinner";
import Link from "next/link";

const TYPE_FILTERS = [
  { label: "All", value: undefined },
  { label: "Text", value: "text" },
  { label: "Table", value: "table" },
  { label: "Image", value: "image" },
];

interface Props {
  projectName: string;
}

export default function ChunksPage({ projectName }: Props) {
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState("");
  const [selected, setSelected] = useState<ChunkItem | null>(null);

  const { data, isLoading } = useQuery<ChunksResponse>({
    queryKey: ["chunks", projectName, typeFilter],
    queryFn: () => projectsApi.chunks(projectName, typeFilter),
  });

  const chunks = data?.chunks ?? [];

  // Client-side search filtering
  const filteredChunks = useMemo(() => {
    if (!searchQuery.trim()) return chunks;
    const query = searchQuery.toLowerCase();
    return chunks.filter(
      (c) =>
        c.content.toLowerCase().includes(query) ||
        c.raw_text.toLowerCase().includes(query) ||
        c.source_file?.toLowerCase().includes(query) ||
        c.clause_type?.toLowerCase().includes(query)
    );
  }, [chunks, searchQuery]);

  // Calculate statistics
  const stats = useMemo(() => {
    const textCount = chunks.filter((c) => c.content_types.includes("text")).length;
    const tableCount = chunks.filter((c) => c.content_types.includes("table")).length;
    const imageCount = chunks.filter((c) => c.content_types.includes("image")).length;
    return { textCount, tableCount, imageCount, total: chunks.length };
  }, [chunks]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 px-4 sm:px-6 py-4 border-b border-border shrink-0">
        <Link
          href={`/projects/${encodeURIComponent(projectName)}`}
          aria-label="Back to project"
          className="text-muted hover:text-white transition-colors p-1 -m-1 rounded-lg"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </Link>
        <div>
          <h1 className="text-sm font-semibold text-white">{projectName} — Chunks</h1>
          <p className="text-xs text-muted">{data?.total ?? 0} total</p>
        </div>

        {/* Filter tabs */}
        <div className="ml-auto flex items-center gap-1 bg-card border border-border rounded-lg p-0.5">
          {TYPE_FILTERS.map((f) => (
            <button
              key={f.label}
              onClick={() => { setTypeFilter(f.value); setSelected(null); }}
              aria-pressed={typeFilter === f.value}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                ${typeFilter === f.value
                  ? "bg-accent/20 text-accent"
                  : "text-muted hover:text-white"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Statistics Banner */}
      {!isLoading && chunks.length > 0 && (
        <div className="px-4 sm:px-6 py-3 bg-card/30 border-b border-border flex items-center gap-6 shrink-0">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="text-xs text-muted">Text:</span>
            <span className="text-xs font-semibold text-white">{stats.textCount}</span>
          </div>
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <span className="text-xs text-muted">Tables:</span>
            <span className="text-xs font-semibold text-white">{stats.tableCount}</span>
          </div>
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-xs text-muted">Images:</span>
            <span className="text-xs font-semibold text-white">{stats.imageCount}</span>
          </div>
        </div>
      )}

      {/* Search Bar */}
      <div className="px-4 sm:px-6 py-3 border-b border-border shrink-0">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search chunks by content, clause type, or filename..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-card border border-border rounded-lg text-sm text-white placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-white"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        {searchQuery && (
          <p className="text-xs text-muted mt-2">
            {filteredChunks.length} result{filteredChunks.length !== 1 ? "s" : ""} found
          </p>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 flex min-h-0">
        {/* Chunk list */}
        <div className="w-80 shrink-0 border-r border-border overflow-y-auto">
          {isLoading ? (
            <div className="flex justify-center py-10">
              <Spinner size="sm" />
            </div>
          ) : filteredChunks.length === 0 ? (
            <p className="text-xs text-muted text-center py-10">
              {searchQuery ? "No matching chunks found" : "No chunks found"}
            </p>
          ) : (
            filteredChunks.map((c) => (
              <ChunkCard
                key={c.chunk_id}
                chunk={c}
                selected={selected?.chunk_id === c.chunk_id}
                onClick={() => setSelected(c)}
              />
            ))
          )}
        </div>

        {/* Detail panel */}
        <ChunkDetailPanel chunk={selected} />
      </div>
    </div>
  );
}
