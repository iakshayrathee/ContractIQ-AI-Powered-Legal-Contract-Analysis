"use client";

import { useRef, useState } from "react";
import { SendHorizonal, AlertTriangle, X } from "lucide-react";

interface Props {
  onSubmit: (message: string) => void;
  loading: boolean;
  disabled?: boolean;
  onCancel?: () => void;
}

export default function ChatInput({ onSubmit, loading, disabled, onCancel }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading || disabled) return;
    onSubmit(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onInput = (e: React.FormEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div className="border-t border-border px-4 py-3 bg-primary/50">
      {disabled && (
        <div className="flex items-center justify-center gap-1.5 mb-2.5 text-amber-400">
          <AlertTriangle className="w-3.5 h-3.5" />
          <p className="text-xs">Upload a document first to start asking questions.</p>
        </div>
      )}
      <div className={`flex items-center gap-2 bg-card border rounded-xl px-3.5 py-2.5 transition-all
        ${
          disabled
            ? "border-border opacity-50"
            : "border-border hover:border-gold/25 focus-within:border-gold/35 focus-within:ring-2 focus-within:ring-gold/10"
        }`}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onInput={onInput}
          disabled={disabled || loading}
          placeholder="Ask a question about your documents…"
          className="flex-1 bg-transparent text-sm text-white placeholder-muted
            resize-none focus:outline-none min-h-[22px] max-h-40 leading-relaxed"
        />
        {loading && onCancel ? (
          <button
            onClick={onCancel}
            title="Cancel streaming"
            aria-label="Cancel streaming response"
            className="shrink-0 w-8 h-8 rounded-lg bg-red-500/20 border border-red-500/30
              hover:bg-red-500/30 flex items-center justify-center transition-all"
          >
            <X className="w-3.5 h-3.5 text-red-400" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!value.trim() || loading || disabled}
            className="shrink-0 w-8 h-8 rounded-lg bg-gradient-gold
              disabled:opacity-40 disabled:cursor-not-allowed
              flex items-center justify-center transition-all shadow-glow-sm hover:shadow-glow"
          >
            {loading ? (
              <span className="w-3 h-3 border border-[#06080F]/50 border-t-[#06080F] rounded-full animate-spin" />
            ) : (
              <SendHorizonal className="w-3.5 h-3.5 text-[#06080F]" />
            )}
          </button>
        )}
      </div>
      <p className="text-[10px] text-subtle text-center mt-1.5">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
