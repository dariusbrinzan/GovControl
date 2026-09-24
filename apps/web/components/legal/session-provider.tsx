"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiGet, type AuthenticatedUser } from "../../lib/api";

const TOKEN_KEY = "govcontrol.dev-token";

type SessionContextValue = {
  token: string;
  user: AuthenticatedUser | null;
  ready: boolean;
  error: string | null;
  connect: (token: string) => Promise<void>;
  disconnect: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [ready, setReady] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async (nextToken: string) => {
    const normalized = nextToken.trim();
    if (!normalized) {
      setError("Introdu tokenul local de dezvoltare.");
      return;
    }
    setReady(false);
    setError(null);
    try {
      const nextUser = await apiGet<AuthenticatedUser>("/auth/me", normalized);
      window.localStorage.setItem(TOKEN_KEY, normalized);
      setToken(normalized);
      setUser(nextUser);
    } catch (reason) {
      setUser(null);
      setError(reason instanceof Error ? reason.message : "Conectarea nu a reușit.");
      throw reason;
    } finally {
      setReady(true);
    }
  }, []);

  const disconnect = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setError(null);
    setReady(true);
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem(TOKEN_KEY);
    if (saved) void connect(saved).catch(() => undefined);
  }, [connect]);

  const value = useMemo(
    () => ({ token, user, ready, error, connect, disconnect }),
    [token, user, ready, error, connect, disconnect],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
