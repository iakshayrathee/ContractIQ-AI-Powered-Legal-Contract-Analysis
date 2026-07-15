"use client";

import React, { createContext, useCallback, useContext, useState } from "react";
import { CheckCircle, XCircle, Info, X } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let toastId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            toast={t}
            onDismiss={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const typeConfig: Record<ToastType, { border: string; icon: React.ReactNode; bg: string }> = {
  success: {
    border: "border-l-gold",
    bg: "bg-gold/[0.05]",
    icon: <CheckCircle className="w-4 h-4 text-gold shrink-0" />,
  },
  error: {
    border: "border-l-red-500",
    bg: "bg-red-500/[0.05]",
    icon: <XCircle className="w-4 h-4 text-red-400 shrink-0" />,
  },
  info: {
    border: "border-l-blue-500",
    bg: "bg-blue-500/[0.05]",
    icon: <Info className="w-4 h-4 text-blue-400 shrink-0" />,
  },
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const cfg = typeConfig[toast.type];
  return (
    <div
      className={`pointer-events-auto flex items-center gap-3 pl-3 pr-4 py-3 rounded-xl border border-l-4 border-border/60 ${cfg.border} ${cfg.bg} backdrop-blur-xl shadow-glow-sm text-white slide-in-from-right-5 animate-in max-w-sm`}
    >
      {cfg.icon}
      <p className="text-sm font-medium flex-1 leading-snug">{toast.message}</p>
      <button
        onClick={onDismiss}
        className="text-subtle hover:text-white transition-colors shrink-0 ml-1"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
