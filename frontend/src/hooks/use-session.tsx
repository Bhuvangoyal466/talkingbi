import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { createSession, getSessionStatus, deleteSession } from "@/lib/api";
import type { SessionStatus } from "@/types/api";

const SESSION_KEY = "talkingbi_session_id";

interface SessionContextValue {
  sessionId: string;
  status: SessionStatus | null;
  refreshStatus: () => Promise<void>;
  clearSession: () => Promise<void>;
  switchSession: (newSessionId: string) => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [sessionId, setSessionId] = useState<string>("");
  const [status, setStatus] = useState<SessionStatus | null>(null);

  const refreshStatus = async () => {
    if (!sessionId) return;
    try {
      const s = await getSessionStatus(sessionId);
      setStatus(s);
    } catch {
      // session may not exist yet — ignore
    }
  };

  const initSession = async () => {
    const stored = sessionStorage.getItem(SESSION_KEY);
    if (stored) {
      try {
        // Validate the stored session is still alive on the backend
        await getSessionStatus(stored);
        setSessionId(stored);
        return;
      } catch {
        // Session not found — fall through to create a new one
        sessionStorage.removeItem(SESSION_KEY);
      }
    }
    try {
      const { session_id } = await createSession();
      sessionStorage.setItem(SESSION_KEY, session_id);
      setSessionId(session_id);
    } catch {
      // Fallback local ID so the UI still works without a backend
      const fallback = "local-" + Date.now();
      setSessionId(fallback);
    }
  };

  const clearSession = async () => {
    if (sessionId && !sessionId.startsWith("local-")) {
      try { await deleteSession(sessionId); } catch { /* ignore */ }
    }
    sessionStorage.removeItem(SESSION_KEY);
    setStatus(null);
    try {
      const { session_id } = await createSession();
      sessionStorage.setItem(SESSION_KEY, session_id);
      setSessionId(session_id);
    } catch {
      setSessionId("local-" + Date.now());
    }
  };

  const switchSession = async (newSessionId: string) => {
    if (newSessionId === sessionId) return;
    setStatus(null);
    sessionStorage.setItem(SESSION_KEY, newSessionId);
    setSessionId(newSessionId);
  };

  useEffect(() => {
    initSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (sessionId) refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return (
    <SessionContext.Provider value={{ sessionId, status, refreshStatus, clearSession, switchSession }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
