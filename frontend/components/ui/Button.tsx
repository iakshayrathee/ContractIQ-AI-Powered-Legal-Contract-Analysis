"use client";

import React from "react";
import { clsx } from "clsx";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost" | "destructive" | "secondary";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  children: React.ReactNode;
}

const variants = {
  default:     "bg-gradient-gold text-[#06080F] shadow-glow-sm hover:shadow-glow font-semibold",
  secondary:   "bg-surface hover:bg-card text-white/90 border border-border hover:border-border-hover",
  outline:     "bg-transparent hover:bg-gold/[0.06] text-gold/80 hover:text-gold border border-gold/25 hover:border-gold/40",
  ghost:       "bg-transparent hover:bg-white/[0.04] text-muted hover:text-white border border-transparent",
  destructive: "bg-red-950/60 hover:bg-red-900/60 text-red-400 border border-red-900/50 hover:border-red-800/60",
  primary:     "bg-gradient-gold text-[#06080F] shadow-glow-sm hover:shadow-glow font-semibold",
  danger:      "bg-red-950/60 hover:bg-red-900/60 text-red-400 border border-red-900/50",
};

const sizes = {
  sm: "px-3 py-1.5 text-xs rounded-md gap-1.5",
  md: "px-4 py-2 text-sm rounded-lg gap-2",
  lg: "px-5 py-2.5 text-sm rounded-lg gap-2",
};

export function Button({
  variant = "default",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center font-medium",
        "transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 focus-visible:ring-offset-2 focus-visible:ring-offset-primary",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variants[variant as keyof typeof variants] ?? variants.default,
        sizes[size],
        className,
      )}
    >
      {loading && (
        <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
      )}
      {children}
    </button>
  );
}
