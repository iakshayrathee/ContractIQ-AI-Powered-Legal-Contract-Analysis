import type {
  AnalysisResponse,
  ChatMessageResponse,
  ChunksResponse,
  DashboardStats,
  HealthResponse,
  IngestJobResponse,
  Job,
  Project,
  QueryResponse,
  RiskResponse,
  SummaryResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let activeAccessToken: string | null = null;

export function setApiToken(token: string | null) {
  activeAccessToken = token;
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (activeAccessToken) {
    headers.set("Authorization", `Bearer ${activeAccessToken}`);
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export const projectsApi = {
  list: (): Promise<Project[]> => request("/projects"),

  create: (name: string, description = ""): Promise<Project> =>
    request("/projects", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  get: (projectName: string): Promise<Project> =>
    request(`/projects/${encodeURIComponent(projectName)}`),

  delete: (projectName: string): Promise<void> =>
    request(`/projects/${encodeURIComponent(projectName)}`, { method: "DELETE" }),

  chunks: (projectName: string, type?: string): Promise<ChunksResponse> => {
    const params = type ? `?type=${type}` : "";
    return request(`/projects/${encodeURIComponent(projectName)}/chunks${params}`);
  },

  chunkStats: (projectName: string): Promise<{ project_name: string; total: number; by_type: { text: number; table: number; image: number } }> =>
    request(`/projects/${encodeURIComponent(projectName)}/chunks/stats`),

  getChatHistory: (projectName: string): Promise<ChatMessageResponse[]> =>
    request(`/projects/${encodeURIComponent(projectName)}/chat`),

  clearChatHistory: (projectName: string): Promise<void> =>
    request(`/projects/${encodeURIComponent(projectName)}/chat`, { method: "DELETE" }),

  listDocuments: (projectName: string): Promise<{ project_name: string; total: number; documents: Array<{ filename: string; size_bytes: number; uploaded_at: number }> }> =>
    request(`/projects/${encodeURIComponent(projectName)}/documents`),

  deleteDocument: (projectName: string, filename: string): Promise<void> =>
    request(`/projects/${encodeURIComponent(projectName)}/documents/${encodeURIComponent(filename)}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Ingestion
// ---------------------------------------------------------------------------

export const ingestApi = {
  ingest: (
    projectName: string,
    file: File,
    overwrite = true,
    onProgress?: (progress: number) => void
  ): Promise<IngestJobResponse> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", file);

      if (onProgress) {
        xhr.upload.addEventListener("progress", (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            onProgress(percent);
          }
        });
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch {
            reject(new Error("Failed to parse response"));
          }
        } else {
          try {
            const body = JSON.parse(xhr.responseText);
            reject(new Error(body.detail ?? `HTTP ${xhr.status}`));
          } catch {
            reject(new Error(`HTTP ${xhr.status}`));
          }
        }
      };

      xhr.onerror = () => reject(new Error("Network error"));

      xhr.open(
        "POST",
        `${BASE_URL}/ingest?project_name=${encodeURIComponent(projectName)}&overwrite=${overwrite}`
      );
      if (activeAccessToken) {
        xhr.setRequestHeader("Authorization", `Bearer ${activeAccessToken}`);
      }
      xhr.send(form);
    });
  },
};

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export const jobsApi = {
  get: (jobId: string): Promise<Job> => request(`/jobs/${jobId}`),
};

// ---------------------------------------------------------------------------
// Query  (SSE streaming)
// ---------------------------------------------------------------------------

export interface SSECallbacks {
  onSources: (data: {
    question: string;
    project_name: string;
    chunks_retrieved: number;
    sources: QueryResponse["sources"];
  }) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
}

export const queryApi = {
  /** Legacy non-streaming fallback (kept for tests / simple callers). */
  ask: (
    projectName: string,
    question: string,
    k?: number
  ): Promise<QueryResponse> =>
    request("/query", {
      method: "POST",
      body: JSON.stringify({ project_name: projectName, question, k }),
    }),

  /** Streaming SSE query — preferred path. */
  stream: async (
    projectName: string,
    question: string,
    k: number | undefined,
    callbacks: SSECallbacks,
    signal?: AbortSignal
  ): Promise<void> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (activeAccessToken) {
      headers["Authorization"] = `Bearer ${activeAccessToken}`;
    }
    const body: { project_name: string; question: string; k?: number } = {
      project_name: projectName,
      question,
    };
    // Only include k if it's explicitly provided
    if (k !== undefined) {
      body.k = k;
    }
    const res = await fetch(`${BASE_URL}/query`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail ?? `HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6);
        try {
          const evt = JSON.parse(payload);
          switch (evt.type) {
            case "sources":
              callbacks.onSources(evt);
              break;
            case "token":
              callbacks.onToken(evt.token);
              break;
            case "done":
              callbacks.onDone();
              break;
            case "error":
              callbacks.onError(evt.detail ?? "Unknown error");
              break;
          }
        } catch {
          // ignore non-JSON lines
        }
      }
    }
  },
};

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export const healthApi = {
  check: (): Promise<HealthResponse> => request("/health"),
};

// ---------------------------------------------------------------------------
// Contract Analysis
// ---------------------------------------------------------------------------

export const contractsApi = {
  analyze: (projectName: string): Promise<AnalysisResponse> =>
    request(`/projects/${encodeURIComponent(projectName)}/analyze`, { method: "POST" }),

  getAnalysis: (projectName: string): Promise<AnalysisResponse> =>
    request(`/projects/${encodeURIComponent(projectName)}/analysis`),

  getClauses: (projectName: string, type?: string): Promise<{ project_name: string; total: number; clauses: any[] }> => {
    const params = type ? `?type=${type}` : "";
    return request(`/projects/${encodeURIComponent(projectName)}/analysis/clauses${params}`);
  },

  getRisks: (projectName: string): Promise<RiskResponse> =>
    request(`/projects/${encodeURIComponent(projectName)}/risks`),

  getSummary: (projectName: string): Promise<SummaryResponse> =>
    request(`/projects/${encodeURIComponent(projectName)}/summary`),
};

// ---------------------------------------------------------------------------
// Analysis Stream (Task 4)
// ---------------------------------------------------------------------------

/**
 * Stream clause analysis for a project question via /analysis/stream SSE.
 * Requires a valid Bearer access token (pass via `authHeaders`).
 */
export const analysisApi = {
  stream: async (
    projectName: string,
    question: string,
    k: number | undefined,
    callbacks: SSECallbacks,
    accessToken: string | null,
    signal?: AbortSignal
  ): Promise<void> => {
    const tokenToUse = accessToken || activeAccessToken;
    const res = await fetch(`${BASE_URL}/analysis/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(tokenToUse ? { Authorization: `Bearer ${tokenToUse}` } : {}),
      },
      credentials: "include",
      body: JSON.stringify({ project_name: projectName, question, k }),
      signal,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail ?? `HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6);
        try {
          const evt = JSON.parse(payload);
          switch (evt.type) {
            case "sources":
              callbacks.onSources(evt);
              break;
            case "token":
              callbacks.onToken(evt.token);
              break;
            case "done":
              callbacks.onDone();
              break;
            case "error":
              callbacks.onError(evt.detail ?? "Unknown error");
              break;
          }
        } catch {
          // ignore non-JSON lines
        }
      }
    }
  },
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const dashboardApi = {
  getStats: (): Promise<DashboardStats> => request("/dashboard/stats"),
};
