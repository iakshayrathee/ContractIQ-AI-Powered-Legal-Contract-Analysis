"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { flushSync } from "react-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi, queryApi } from "@/lib/api";
import { useChatHistory } from "@/lib/hooks/useProjectQueries";
import type { ChatMessage, ChatMessageResponse, Project, SourceChunk } from "@/lib/types";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";
import ChatEmptyState from "./ChatEmptyState";
import { Sparkles, FileText, Trash2, Download, X } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { exportConversation } from "@/lib/export";

let msgIdCounter = 0;
const nextId = () => `msg-${++msgIdCounter}`;

/** Build a dedup key from role + trimmed content to match optimistics against persisted history */
const dedupKey = (role: string, content: string) => `${role}::${content.trim()}`;

/** Convert a backend ChatMessageResponse to the frontend ChatMessage shape */
function fromResponse(r: ChatMessageResponse): ChatMessage {
  return {
    id: r.id,
    role: r.role,
    content: r.content,
    sources: r.sources,
    timestamp: new Date(r.created_at),
  };
}

interface Props {
  project: Project;
}

interface ChatInputProps {
  onSubmit: (message: string) => void;
  loading: boolean;
  disabled?: boolean;
  onCancel?: () => void;
}

export default function ChatPanel({ project }: Props) {
  const qc = useQueryClient();
  const { toast } = useToast();

  // Optimistic messages that haven't been confirmed by the backend yet
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const userScrolledUpRef = useRef(false);

  // ── Fetch persisted history from Postgres ──────────────────────────────
  const { data: rawHistory = [], isLoading: historyLoading } = useChatHistory(project.name);
  const history = rawHistory.map(fromResponse);

  // Derive subtitle from project metadata
  const docSubtitle = (() => {
    if (project.description) return project.description;
    if (project.document_count > 0)
      return `${project.document_count} document${project.document_count !== 1 ? "s" : ""} indexed`;
    return "Ask questions about your documents";
  })();

  // ── Local draft persistence to survive tab switches / backend issues ────
  const storageKey = `chatDrafts:${project.name}`;

  // Load drafts on mount/project change
  useEffect(() => {
    try {
      const raw = typeof window !== "undefined" ? localStorage.getItem(storageKey) : null;
      if (raw) {
        const parsed: any[] = JSON.parse(raw);
        const restored: ChatMessage[] = parsed.map((m) => ({ ...m, timestamp: new Date(m.timestamp) }));
        if (restored.length > 0) setOptimisticMessages(restored);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.name]);

  // Save drafts whenever optimistic messages change
  useEffect(() => {
    try {
      const serializable = optimisticMessages.map((m) => ({ ...m, timestamp: m.timestamp.toISOString() }));
      if (typeof window !== "undefined") {
        if (serializable.length > 0) localStorage.setItem(storageKey, JSON.stringify(serializable));
        else localStorage.removeItem(storageKey);
      }
    } catch {}
  }, [optimisticMessages, storageKey]);

  // Merged view: persisted history + any in-flight optimistic messages.
  // De-duplicate by BOTH id AND content+role:
  //   - ID match: optimistic id already returned by backend (rare — only if backend echoes client id)
  //   - Content match: backend persisted the message with a new UUID, so we compare role+content
  //     to suppress the optimistic copy once history has caught up.
  const historyIds = new Set(history.map((m) => m.id));
  const historyKeys = new Set(history.map((m) => dedupKey(m.role, m.content)));
  const pendingOptimistics = optimisticMessages.filter(
    (m) => !historyIds.has(m.id) && !historyKeys.has(dedupKey(m.role, m.content))
  );
  const messages = [...history, ...pendingOptimistics];

  // Once history has caught up with our optimistic messages, clear the optimistics.
  // Match by BOTH id AND content+role so we handle the common case where the backend
  // returns new UUIDs that don't match the client-side msg-N ids.
  useEffect(() => {
    if (isStreaming || optimisticMessages.length === 0) return;

    const hIds = new Set(history.map((m) => m.id));
    const hKeys = new Set(history.map((m) => dedupKey(m.role, m.content)));

    // A non-empty optimistic message is "persisted" when history has it by id or content+role.
    // Empty-content assistant placeholders (still streaming or just cleared) are always kept.
    // For assistant messages with sources, we also verify sources are present in history.
    const allPersisted = optimisticMessages.every((m) => {
      if (m.content === "") return true;
      const inHistory = hIds.has(m.id) || hKeys.has(dedupKey(m.role, m.content));
      if (!inHistory) return false;
      // If this optimistic message has sources, wait for history to also have sources
      if (m.role === "assistant" && m.sources && m.sources.length > 0) {
        const historyMatch = history.find(
          (h) => h.id === m.id || dedupKey(h.role, h.content) === dedupKey(m.role, m.content)
        );
        // Only clear if history has the same sources (or at least some sources)
        if (historyMatch && (!historyMatch.sources || historyMatch.sources.length === 0)) {
          return false; // history not fully synced yet
        }
      }
      return true;
    });

    if (allPersisted && history.length > 0) {
      setOptimisticMessages([]);
      try { if (typeof window !== "undefined") localStorage.removeItem(storageKey); } catch {}
    }
  }, [history, optimisticMessages, isStreaming, storageKey]);

  // ── Clear chat ─────────────────────────────────────────────────────────
  const clearMutation = useMutation({
    mutationFn: () => projectsApi.clearChatHistory(project.name),
    onSuccess: () => {
      setOptimisticMessages([]);
      try { if (typeof window !== "undefined") localStorage.removeItem(storageKey); } catch {}
      qc.invalidateQueries({ queryKey: ["chat", project.name] });
      toast("Chat history cleared", "success");
    },
    onError: (error) => {
      console.error("[ChatPanel] Clear chat failed:", error);
      toast("Failed to clear chat", "error");
    },
  });

  // ── Send message ───────────────────────────────────────────────────────
  const handleSubmit = useCallback((question: string) => {
    // Add optimistic user + streaming assistant messages immediately
    const userMsg: ChatMessage = {
      id: nextId(),
      role: "user",
      content: question,
      timestamp: new Date(),
    };
    const assistantId = nextId();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setOptimisticMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    // Use adaptive retrieval (k=undefined) — backend will fetch pool and filter by score
    queryApi.stream(project.name, question, undefined, {
      onSources: (data) => {
        setOptimisticMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, chunks_retrieved: data.chunks_retrieved, sources: data.sources as SourceChunk[] }
              : m
          )
        );
      },
      onToken: (token) => {
        flushSync(() => {
          setOptimisticMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + token } : m
            )
          );
        });
      },
      onDone: () => {
        setIsStreaming(false);
        // Don't clear localStorage yet — keep optimistic messages alive until history confirms them.
        // The dedup effect above will clear them once the refetch returns WITH sources.
        // Wait 2s for backend to persist (save_chat_pair is fire-and-forget async).
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["chat", project.name] });
        }, 2000);
      },
      onError: (msg) => {
        setOptimisticMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: `Error: ${msg}` } : m
          )
        );
        setIsStreaming(false);
      },
    }, controller.signal).catch((err: Error) => {
      if (err.name === "AbortError") {
        // Keep the user's message, remove the empty assistant placeholder
        console.debug("[ChatPanel] Stream aborted by user");
        setOptimisticMessages((prev) => prev.filter((m) => m.id !== assistantId));
        setIsStreaming(false);
        return;
      }
      console.error("[ChatPanel] Stream error:", err);
      setOptimisticMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: `Error: ${err.message}` } : m
        )
      );
      setIsStreaming(false);
    });
  }, [project.name, qc]);

  // Debounced scroll - only scroll if user hasn't manually scrolled up
  useEffect(() => {
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => {
      if (!userScrolledUpRef.current) {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }, 100);
    return () => {
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, [messages, isStreaming]);

  // Track if user scrolled up
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const isAtBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 100;
    userScrolledUpRef.current = !isAtBottom;
  };

  const isEmpty = messages.length === 0 && !historyLoading;
  const hasDocuments = project.document_count > 0;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-6 h-16 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
            <Sparkles className="w-3.5 h-3.5 text-accent-light" />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-white truncate">{project.name}</h1>
            <p className="text-xs text-muted leading-none mt-0.5 truncate max-w-[260px]">
              {docSubtitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {project.document_count > 0 && (
            <div className="flex items-center gap-1.5">
              <FileText className="w-3 h-3 text-muted" />
              <span className="text-xs text-muted">{project.document_count} docs</span>
            </div>
          )}

          {/* Export chat button — only shown when there are messages */}
          {messages.length > 0 && (
            <button
              onClick={() => exportConversation(messages, project.name)}
              title="Export conversation"
              aria-label="Export conversation history"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
                text-subtle hover:text-gold hover:bg-gold/10 border border-transparent
                hover:border-gold/20 transition-all"
            >
              <Download className="w-3 h-3" />
              <span className="hidden sm:inline">Export</span>
            </button>
          )}

          {/* Clear chat button — only shown when there are messages */}
          {messages.length > 0 && (
            <button
              id="clear-chat-btn"
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending || isStreaming}
              title="Clear conversation"
              aria-label="Clear conversation history"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium
                text-subtle hover:text-red-400 hover:bg-red-500/10 border border-transparent
                hover:border-red-500/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 className="w-3 h-3" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-5" onScroll={handleScroll}>
        {historyLoading ? (
          <div className="flex items-center justify-center h-full">
            <span className="w-5 h-5 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : isEmpty && !isStreaming ? (
          <ChatEmptyState project={project} onSuggestionClick={handleSubmit} />
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble
                key={`msg-${i}`}
                message={msg}
                projectName={project.name}
                isLatest={i === messages.length - 1 && msg.role === "assistant"}
                isStreaming={isStreaming}
                isMostRecent={i === messages.length - 1}
                onResend={(text) => handleSubmit(text)}
              />
            ))}
            {/* Typing indicator — only shown while waiting for the FIRST token (content is still empty) */}
            {isStreaming && pendingOptimistics[pendingOptimistics.length - 1]?.content === "" && (
              <div className="flex justify-start mb-4">
                <div className="w-8 h-8 rounded-xl bg-gold/10 border border-gold/25 flex items-center justify-center mr-2.5 mt-0.5 shrink-0 shadow-glow-sm">
                  <Sparkles className="w-3.5 h-3.5 text-gold" />
                </div>
                <div className="bg-card border border-border rounded-2xl rounded-bl-sm px-4 py-3">
                  <span className="flex gap-1.5 items-center">
                    <span className="w-1.5 h-1.5 bg-gold/70 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 bg-gold/70 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 bg-gold/70 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <ChatInput
        onSubmit={handleSubmit}
        loading={isStreaming}
        disabled={!hasDocuments}
        onCancel={() => abortRef.current?.abort()}
      />
    </div>
  );
}
