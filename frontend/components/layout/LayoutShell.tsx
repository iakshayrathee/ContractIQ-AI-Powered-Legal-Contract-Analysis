"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import Sidebar from "./Sidebar";
import { useAuth } from "@/lib/auth";

/** Routes that are public (no auth required). */
const PUBLIC_ROUTES = new Set(["/", "/login", "/register"]);

export default function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();

  const isPublic = PUBLIC_ROUTES.has(pathname);

  // Redirect unauthenticated users away from protected routes
  useEffect(() => {
    if (!isLoading && !user && !isPublic) {
      router.replace("/login");
    }
  }, [isLoading, user, isPublic, router]);

  // While restoring session, show nothing (avoids flash of protected content)
  if (isLoading && !isPublic) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0a0e1a]">
        <div className="flex flex-col items-center gap-3">
          <svg className="animate-spin w-8 h-8 text-violet-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-slate-400 text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  // Public pages (landing, login, register) — no sidebar
  if (isPublic) {
    return <div className="flex-1 overflow-auto">{children}</div>;
  }

  // Authenticated app shell
  return (
    <>
      <Sidebar />
      <main className="flex-1 overflow-auto pt-14 md:pt-0">{children}</main>
    </>
  );
}
