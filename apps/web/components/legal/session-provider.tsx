"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ApiError,
  gatewayAuthConfig,
  gatewayLocalLogin,
  gatewayLoginUrl,
  gatewayLogout,
  gatewaySession,
  type AuthenticatedUser,
  type GatewaySession,
} from "../../lib/api";

type SessionContextValue = {
  token: string;
  user: AuthenticatedUser | null;
  ready: boolean;
  error: string | null;
  authMode: "local" | "oidc";
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"local" | "oidc">("local");

  const applySession = useCallback((session: GatewaySession) => {
    setToken(session.csrf_token);
    setUser(session.user);
  }, []);

  const connect = useCallback(async () => {
    setReady(false);
    setError(null);
    try {
      if (authMode === "oidc") {
        window.location.assign(gatewayLoginUrl());
        return;
      }
      applySession(await gatewayLocalLogin());
    } catch (reason) {
      setUser(null);
      setError(reason instanceof Error ? reason.message : "Conectarea nu a reușit.");
      throw reason;
    } finally {
      setReady(true);
    }
  }, [applySession, authMode]);

  const clearSession = useCallback(() => {
    setToken("");
    setUser(null);
    setReady(true);
  }, []);

  const disconnect = useCallback(async () => {
    try {
      if (token) await gatewayLogout(token);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Deconectarea nu a reușit.");
    } finally {
      clearSession();
    }
  }, [clearSession, token]);

  useEffect(() => {
    let active = true;
    const restore = async () => {
      try {
        const config = await gatewayAuthConfig();
        if (active) setAuthMode(config.mode);
        const session = await gatewaySession();
        if (active) applySession(session);
      } catch (reason) {
        if (active && (!(reason instanceof ApiError) || reason.status !== 401)) {
          setError(reason instanceof Error ? reason.message : "Gateway-ul nu este disponibil.");
        }
      } finally {
        if (active) setReady(true);
      }
    };
    const expired = () => {
      clearSession();
      setError("Sesiunea a expirat sau a fost revocată. Autentifică-te din nou.");
    };
    window.addEventListener("govcontrol:session-expired", expired);
    void restore();
    return () => {
      active = false;
      window.removeEventListener("govcontrol:session-expired", expired);
    };
  }, [applySession, clearSession]);

  const value = useMemo(
    () => ({ token, user, ready, error, authMode, connect, disconnect }),
    [token, user, ready, error, authMode, connect, disconnect],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
