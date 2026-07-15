"use client";

import type { ChatMessage } from "@/lib/types";
import { useState, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/Badge";
import { Scale, FileText, Table2, Copy, Check, RotateCcw, ThumbsUp, ThumbsDown, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  message: ChatMessage;
  projectName: string;
  isLatest?: boolean;
  isStreaming?: boolean;
  /** True if this is the most recent message in the list (any role) */
  isMostRecent?: boolean;
  onRegenerate?: () => void;
  onRetry?: () => void;
  /** For user messages: resend edited content */
  onResend?: (text: string) => void;
}

export default function MessageBubble({
  message,
  projectName,
  isLatest = false,
  isStreaming = false,
  isMostRecent = false,
  onRegenerate,
  onRetry,
  onResend,
}: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  
  // Memoize sources to prevent re-renders when message updates but sources stay the same
  const sources = useMemo(() => message.sources ?? [], [message.sources]);
  
  // Limit sources to 3 and memoize to prevent re-renders
  const displaySources = useMemo(() => sources.slice(0, 3), [sources]);
  
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(message.content);
  const [showSources, setShowSources] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Show cursor while this specific bubble is actively streaming
  const showCursor = !isUser && isLatest && isStreaming && message.content.length > 0;

  // Do not render an empty assistant bubble while streaming (avoid double view with typing indicator)
  if (!isUser && isLatest && isStreaming && message.content === "") {
    return null;
  }

  // Detect error messages
  const isError = !isUser && message.content.startsWith("Error:");

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-5 animate-in fade-in slide-in-from-bottom-2`}>
      {!isUser && !(isLatest && isStreaming && !message.content) && (
        <div className="w-8 h-8 rounded-xl bg-gold/10 border border-gold/25 flex items-center justify-center mr-2.5 mt-0.5 shrink-0 shadow-glow-sm">
          <Scale className="w-3.5 h-3.5 text-gold" />
        </div>
      )}

      <div className={`max-w-[78%] ${isUser ? "order-1" : ""} group relative`}>
        {/* Hover actions for assistant message - floating top right */}
        {!isUser && !isStreaming && (
          <div
            className="absolute top-2 right-2 opacity-0 group-hover:opacity-100
            transition-all duration-200 flex items-center gap-0.5 bg-card/90 backdrop-blur border border-border rounded-lg p-1 shadow-lg z-20"
          >
            {isError && onRetry ? (
              <button
                onClick={onRetry}
                title="Retry this question"
                className="p-1.5 rounded hover:bg-amber-500/10 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
              </button>
            ) : (
              <>
                <button
                  onClick={handleCopy}
                  title="Copy message"
                  className="p-1.5 rounded hover:bg-white/[0.06] transition-colors"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Copy className="w-3.5 h-3.5 text-muted hover:text-gold" />
                  )}
                </button>

                {onRegenerate && (
                  <button
                    onClick={onRegenerate}
                    title="Regenerate response"
                    className="p-1.5 rounded hover:bg-white/[0.06] transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-muted hover:text-gold" />
                  </button>
                )}

                <button
                  onClick={() => setFeedback(feedback === "up" ? null : "up")}
                  title="Helpful"
                  className="p-1.5 rounded hover:bg-white/[0.06] transition-colors"
                >
                  <ThumbsUp className={`w-3.5 h-3.5 ${feedback === "up" ? "text-emerald-400" : "text-muted hover:text-gold"}`} />
                </button>

                <button
                  onClick={() => setFeedback(feedback === "down" ? null : "down")}
                  title="Not helpful"
                  className="p-1.5 rounded hover:bg-white/[0.06] transition-colors"
                >
                  <ThumbsDown className={`w-3.5 h-3.5 ${feedback === "down" ? "text-red-400" : "text-muted hover:text-gold"}`} />
                </button>
              </>
            )}
          </div>
        )}

        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? "bg-gold/[0.12] border border-gold/25 text-white rounded-br-sm shadow-glow-sm"
            : isError
            ? "bg-red-500/10 border border-red-500/25 text-red-200 rounded-bl-sm"
            : "bg-card border border-border text-white rounded-bl-sm"
          }`}
        >
          {isUser ? (
            editing ? (
              <div className="space-y-2">
                <textarea
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  rows={3}
                  className="w-full bg-transparent border border-border rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold/20"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      const v = editValue.trim();
                      if (!v || !onResend) { setEditing(false); return; }
                      onResend(v);
                      setEditing(false);
                    }}
                    className="px-2 py-1 rounded-md text-xs font-medium bg-gold/20 text-gold hover:bg-gold/25 transition-colors"
                  >
                    Save & Resend
                  </button>
                  <button
                    onClick={() => { setEditValue(message.content); setEditing(false); }}
                    className="px-2 py-1 rounded-md text-xs font-medium bg-card text-muted hover:text-white hover:bg-card-hover border border-border transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <span className="whitespace-pre-wrap">{message.content}</span>
            )
          ) : (
            <>
              <div className="prose-invert prose-sm max-w-none
                [&_p]:mb-2 [&_p:last-child]:mb-0
                [&_ul]:mb-2 [&_ol]:mb-2 [&_li]:text-white/80
                [&_code]:bg-surface [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-accent-light [&_code]:text-xs
                [&_pre]:bg-surface [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-border
                [&_table]:w-full [&_th]:text-left [&_th]:px-2 [&_th]:py-1 [&_th]:border-b [&_th]:border-border
                [&_td]:px-2 [&_td]:py-1 [&_td]:border-b [&_td]:border-border
                [&_strong]:text-white [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm
                [&_a]:text-accent-light [&_a]:underline
                [&_blockquote]:border-l-2 [&_blockquote]:border-accent/50 [&_blockquote]:pl-3 [&_blockquote]:text-muted">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                {showCursor && <span className="inline-block w-0.5 h-3.5 bg-gold ml-0.5 animate-pulse" />}
              </div>

              {/* Inline images — from any retrieved source chunk */}
              {(() => {
                const allImages = sources.flatMap(s => s.images_base64 ?? []);
                if (allImages.length === 0) return null;
                return (
                  <div className="mt-3 pt-3 border-t border-border/50 space-y-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle">
                      Referenced Images
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {allImages.map((img, j) => (
                        <img
                          key={j}
                          src={`data:image/jpeg;base64,${img}`}
                          alt={`Referenced image ${j + 1}`}
                          className="max-h-56 w-auto rounded-lg border border-border object-contain"
                        />
                      ))}
                    </div>
                  </div>
                );
              })()}
            </>
          )}
        </div>

        {/* Meta row */}
        <div className={`flex items-center gap-2 mt-1.5 flex-wrap ${isUser ? "justify-end" : "justify-start"}`}>
          <span className="text-[11px] text-subtle">
            {message.timestamp.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
          </span>
          {/* User message actions */}
          {isUser && isMostRecent && !isStreaming && (
            <div className="inline-flex items-center gap-1 ml-1">
              <button
                onClick={handleCopy}
                title="Copy message"
                className="p-1 rounded-md hover:bg-white/[0.06] transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-muted hover:text-gold" />}
              </button>
              {onResend && (
                <button
                  onClick={() => setEditing(true)}
                  title="Edit and resend"
                  className="p-1 rounded-md hover:bg-white/[0.06] transition-colors text-muted hover:text-gold"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Top 3 Chunks - Collapsible */}
        {!isUser && displaySources.length > 0 && !isStreaming && (
          <div className="mt-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle">
                Sources Referenced
              </p>
              <button
                onClick={() => setShowSources(!showSources)}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-subtle hover:text-gold transition-colors px-2 py-0.5 rounded bg-surface/50 border border-border/40"
              >
                <span>{showSources ? "Hide Details" : "Show Details"}</span>
                {showSources ? (
                  <ChevronUp className="w-3 h-3 text-muted" />
                ) : (
                  <ChevronDown className="w-3 h-3 text-muted" />
                )}
              </button>
            </div>
            
            {showSources && (
              <div className="space-y-2 mt-2 animate-in fade-in slide-in-from-top-1 duration-200">
                {displaySources.map((source, i) => {
                  const score = source.relevance_score;
                  const p = source.page_numbers?.[0];
                  const pdfUrl = source.source_file
                    ? `${API_BASE}/projects/${encodeURIComponent(projectName)}/documents/${encodeURIComponent(source.source_file)}#page=${p}`
                    : null;

                  const getScoreColor = () => {
                    if (!score) return "text-gray-400";
                    if (score >= 0.85) return "text-emerald-400";
                    if (score >= 0.70) return "text-amber-400";
                    return "text-red-400";
                  };
                  
                  return (
                    <div key={`source-detail-${i}-${source.source_file}-${p || 'nopage'}`} className="bg-card border border-border rounded-xl p-3 space-y-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-xs font-semibold text-gold bg-gold/10 border border-gold/20 rounded-md px-1.5 py-0.5 font-mono">
                          #{i + 1}
                        </span>
                        {score !== undefined && (
                          <span className={`text-[10px] font-medium ${getScoreColor()}`}>
                            {(score * 100).toFixed(0)}% match
                          </span>
                        )}
                        {source.content_types?.map((t, typeIdx) => (
                          <Badge key={`${i}-${typeIdx}-${t}`} type={t as "text" | "table" | "image"} small />
                        ))}
                        
                        {/* PDF Document Source Info (static display, no link) */}
                        {source.source_file && (
                          <div className="inline-flex items-center gap-1 text-[11px] text-muted ml-auto">
                            <FileText className="w-3 h-3 text-gold" />
                            <span className="truncate max-w-[150px] font-medium">{source.source_file}</span>
                            {p && <span className="opacity-70 font-mono">p.{p}</span>}
                          </div>
                        )}
                      </div>

                      <p className="text-xs text-muted leading-relaxed whitespace-pre-wrap">{source.raw_text}</p>

                      {source.tables_html && source.tables_html.length > 0 && (
                        <div className="space-y-2">
                          <div className="flex items-center gap-1 text-[10px] text-subtle">
                            <Table2 className="w-3 h-3" />
                            {source.tables_html.length} table{source.tables_html.length !== 1 ? "s" : ""}
                          </div>
                          {source.tables_html.map((tableHtml, t) => (
                            <div
                              key={t}
                              className="overflow-x-auto rounded-lg border border-border text-[11px]
                                [&_table]:w-full [&_table]:border-collapse
                                [&_th]:bg-surface [&_th]:text-white/80 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:border [&_th]:border-border
                                [&_td]:text-muted [&_td]:px-2 [&_td]:py-1 [&_td]:border [&_td]:border-border"
                              dangerouslySetInnerHTML={{ __html: tableHtml }}
                            />
                          ))}
                        </div>
                      )}

                      {source.images_base64 && source.images_base64.length > 0 && (
                        <div className="flex gap-2 mt-1 overflow-x-auto pb-1">
                          {source.images_base64.map((img, j) => (
                            <img
                              key={j}
                              src={`data:image/jpeg;base64,${img}`}
                              alt={`Source image ${j + 1}`}
                              className="h-20 w-auto rounded-lg border border-border object-cover shrink-0"
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
