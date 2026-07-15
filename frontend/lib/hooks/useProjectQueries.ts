import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { projectsApi, contractsApi } from "@/lib/api";
import type { 
  Project, 
  AnalysisResponse, 
  ChatMessageResponse 
} from "@/lib/types";

/**
 * Shared React Query hooks for project-related data.
 * These hooks enforce consistent query configuration and prevent duplicate fetches.
 */

// ---------------------------------------------------------------------------
// Project Metadata
// ---------------------------------------------------------------------------

export function useProject(name: string, refetchInterval: number | false = false): UseQueryResult<Project> {
  return useQuery({
    queryKey: ["project", name],
    queryFn: () => projectsApi.get(name),
    staleTime: 60_000, // 60s - project metadata changes infrequently
    refetchOnWindowFocus: false,
    refetchInterval,
  });
}

// ---------------------------------------------------------------------------
// Chunk Statistics (Lightweight)
// ---------------------------------------------------------------------------

export interface ChunkStats {
  project_name: string;
  total: number;
  by_type: {
    text: number;
    table: number;
    image: number;
  };
}

export function useChunkStats(name: string): UseQueryResult<ChunkStats> {
  return useQuery({
    queryKey: ["chunkStats", name],
    queryFn: () => projectsApi.chunkStats(name),
    staleTime: 120_000, // 2min - chunk stats only change on re-ingest
    refetchOnWindowFocus: false,
  });
}

// ---------------------------------------------------------------------------
// Documents List
// ---------------------------------------------------------------------------

export interface DocumentsResponse {
  project_name: string;
  total: number;
  documents: Array<{
    filename: string;
    size_bytes: number;
    uploaded_at: number;
  }>;
}

export function useDocuments(name: string, refetchInterval: number | false = false): UseQueryResult<DocumentsResponse> {
  return useQuery({
    queryKey: ["documents", name],
    queryFn: () => projectsApi.listDocuments(name),
    staleTime: 30_000, // 30s
    refetchOnWindowFocus: false,
    refetchInterval,
  });
}

// ---------------------------------------------------------------------------
// Chat History
// ---------------------------------------------------------------------------

export function useChatHistory(name: string): UseQueryResult<ChatMessageResponse[]> {
  return useQuery({
    queryKey: ["chat", name],
    queryFn: () => projectsApi.getChatHistory(name),
    staleTime: 30_000, // 30s - changes after each message
    refetchOnWindowFocus: false,
  });
}

// ---------------------------------------------------------------------------
// Analysis (with Smart Polling)
// ---------------------------------------------------------------------------

export function useAnalysis(name: string, enabled: boolean = true): UseQueryResult<AnalysisResponse> {
  return useQuery({
    queryKey: ["analysis", name],
    queryFn: () => contractsApi.getAnalysis(name),
    staleTime: 30_000, // 30s
    refetchOnWindowFocus: false,
    enabled,
    // Smart polling: only poll when analysis is actually running
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      // Poll at 3s intervals only during active analysis
      if (data.status === "running" || data.status === "pending") {
        return 3000;
      }
      // Stop polling when complete or failed
      return false;
    },
  });
}

// ---------------------------------------------------------------------------
// Projects List
// ---------------------------------------------------------------------------

export function useProjects(): UseQueryResult<Project[]> {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list(),
    staleTime: 30_000, // 30s - changes on create/delete
    refetchOnWindowFocus: false,
  });
}
