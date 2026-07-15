"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { Scale, AlertCircle } from "lucide-react";

export default function RegisterPage() {
  const { register, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      await register(email, password);
      // Auto-login after successful registration
      await login(email, password);
      router.replace("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-primary hero-mesh px-4 relative overflow-hidden">
      {/* Subtle grid overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.015]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(201,168,76,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(201,168,76,0.4) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      <div className="w-full max-w-md relative z-10 animate-in">
        {/* Logo / Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-gold/10 border border-gold/30 flex items-center justify-center shadow-glow-sm">
              <Scale className="w-5 h-5 text-gold" />
            </div>
            <span className="text-2xl font-bold text-white tracking-tight font-serif">
              Contract<span className="gradient-accent-text">IQ</span>
            </span>
          </div>
          <h1 className="text-2xl font-semibold text-white mb-1">Create your account</h1>
          <p className="text-muted text-xs">Start analyzing contracts with AI today</p>
        </div>

        {/* Card */}
        <div className="bg-card/70 border border-border rounded-2xl p-8 shadow-glow-sm backdrop-blur-md card-mesh relative">
          {/* Accent Line */}
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-gold" />

          <form onSubmit={handleSubmit} className="space-y-5" id="register-form">
            {/* Error */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
                <span className="text-red-300 text-xs leading-relaxed">{error}</span>
              </div>
            )}

            {/* Email */}
            <div className="space-y-1.5">
              <label htmlFor="register-email" className="block text-xs font-semibold uppercase tracking-wider text-muted">
                Email address
              </label>
              <input
                id="register-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-surface/50 border border-border rounded-xl px-4 py-3 text-white placeholder:text-subtle text-sm focus:outline-none focus:ring-2 focus:ring-gold/50 focus:border-gold/60 focus:bg-gold/[0.04] transition-all"
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label htmlFor="register-password" className="block text-xs font-semibold uppercase tracking-wider text-muted">
                Password <span className="text-subtle font-normal lowercase">(min. 8 characters)</span>
              </label>
              <input
                id="register-password"
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-surface/50 border border-border rounded-xl px-4 py-3 text-white placeholder:text-subtle text-sm focus:outline-none focus:ring-2 focus:ring-gold/50 focus:border-gold/60 focus:bg-gold/[0.04] transition-all"
              />
            </div>

            {/* Confirm Password */}
            <div className="space-y-1.5">
              <label htmlFor="register-confirm" className="block text-xs font-semibold uppercase tracking-wider text-muted">
                Confirm password
              </label>
              <input
                id="register-confirm"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-surface/50 border border-border rounded-xl px-4 py-3 text-white placeholder:text-subtle text-sm focus:outline-none focus:ring-2 focus:ring-gold/50 focus:border-gold/60 focus:bg-gold/[0.04] transition-all"
              />
            </div>

            {/* Submit */}
            <button
              id="register-submit-btn"
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-gold text-[#000000] font-bold py-3 rounded-xl transition-all duration-300 shadow-glow hover:shadow-glow-lg disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02] flex items-center justify-center gap-2 text-xs uppercase tracking-wider"
            >
              {loading ? (
                <>
                  <svg className="animate-spin w-4 h-4 text-[#000000]" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating account…
                </>
              ) : (
                "Create account"
              )}
            </button>
          </form>

          {/* Footer link */}
          <p className="text-center text-muted text-xs mt-6">
            Already have an account?{" "}
            <Link href="/login" className="text-gold hover:text-gold-light font-semibold transition-colors">
              Sign in
            </Link>
          </p>
        </div>

        {/* Trust note */}
        <p className="text-center text-subtle text-[10px] mt-6">
          By creating an account you agree to our Terms of Service.
        </p>
      </div>
    </div>
  );
}
