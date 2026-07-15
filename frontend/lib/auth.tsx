"use client";

/**
 * lib/auth.ts
 * ===========
 * Auth context + API calls for ContractIQ frontend.
 *
 * Strategy:
 *  - Access token stored in React context (memory only — never localStorage)
 *  - Refresh token stored in httpOnly SameSite=Strict cookie (managed by the backend)
 *  - On app load, calls /auth/refresh to restore session from cookie silently
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from "react";
import { setApiToken } from "./api";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  /** User ID extracted from the access token sub claim */
  userId: string;
  /** User email extracted from the access token email claim */
  email: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Attach Bearer header to fetch options */
  withAuth: (options?: RequestInit) => RequestInit;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Helper: decode JWT payload without verifying (client-side only for UX)
// ---------------------------------------------------------------------------

function _decodePayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    return JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

function _userFromToken(token: string): AuthUser | null {
  const payload = _decodePayload(token);
  if (!payload?.sub || !payload?.email) return null;
  return { 
    userId: payload.sub as string,
    email: payload.email as string
  };
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const user = useMemo(
    () => (accessToken ? _userFromToken(accessToken) : null),
    [accessToken]
  );

  // Synchronize access token with API client
  useEffect(() => {
    setApiToken(accessToken);
  }, [accessToken]);

  /** Silent refresh on mount — reads the httpOnly cookie automatically */
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include", // send httpOnly cookie
        });
        if (res.ok) {
          const { access_token } = await res.json();
          setAccessToken(access_token);
        }
      } catch {
        // No valid session — user must log in
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include", // receive httpOnly refresh cookie
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(body.detail ?? "Login failed");
    }
    const { access_token } = await res.json();
    setAccessToken(access_token);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: "Registration failed" }));
      throw new Error(body.detail ?? "Registration failed");
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${BASE_URL}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } finally {
      setAccessToken(null);
    }
  }, []);

  const withAuth = useCallback(
    (options: RequestInit = {}): RequestInit => ({
      ...options,
      credentials: "include",
      headers: {
        ...options.headers,
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        "Content-Type": "application/json",
      },
    }),
    [accessToken]
  );

  const value: AuthContextValue = useMemo(
    () => ({ user, accessToken, isLoading, login, register, logout, withAuth }),
    [user, accessToken, isLoading, login, register, logout, withAuth]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
