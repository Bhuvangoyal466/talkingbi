import type {
  ChatRequest,
  ChatResponse,
  DBConnectRequest,
  UploadResponse,
  DataPreviewResponse,
  SessionStatus,
  SessionNewResponse,
  SessionSummary,
  SessionMessage,
  SessionChart,
  HealthResponse,
  ProviderInfo,
  InsightResult,
  ChartResult,
  Insight,
  VoiceAnalysisResponse,
  VoiceTranscriptionResponse,
} from "@/types/api";


// Points to FastAPI backend — proxied via Vite in dev, direct in prod
export const BASE_URL = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

async function readErrorDetail(res: Response, fallbackLabel: string): Promise<string> {
  const body = await res.text();
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    if (parsed?.detail) {
      return `${fallbackLabel}: ${parsed.detail}`;
    }
  } catch {
    // fall through to raw text
  }
  return `${fallbackLabel}: ${body}`;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthResponse> {
  return request("/health");
}

// ─── LLM Provider ─────────────────────────────────────────────────────────────

export async function getProvider(): Promise<ProviderInfo> {
  return request("/llm/provider");
}

export async function setProvider(provider: string): Promise<ProviderInfo> {
  return request("/llm/provider", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

// ─── Session ──────────────────────────────────────────────────────────────────

export async function createSession(): Promise<SessionNewResponse> {
  return request("/session/new", { method: "POST" });
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatus> {
  return request(`/session/${sessionId}/status`);
}

export async function deleteSession(sessionId: string): Promise<{ status: string; session_id: string }> {
  return request(`/session/${sessionId}`, { method: "DELETE" });
}

export async function listPastSessions(): Promise<{ sessions: SessionSummary[] }> {
  return request("/sessions/history");
}

export async function deletePastSession(sessionId: string): Promise<{ status: string; session_id: string }> {
  return request(`/sessions/history/${sessionId}`, { method: "DELETE" });
}

export async function getSessionMessages(sessionId: string, limit = 100): Promise<{ messages: SessionMessage[] }> {
  return request(`/session/${sessionId}/history?limit=${limit}`);
}

export async function getSessionCharts(sessionId: string, limit = 50): Promise<{ charts: SessionChart[] }> {
  return request(`/session/${sessionId}/charts?limit=${limit}`);
}

export async function getSessionInsights(sessionId: string, limit = 100): Promise<{ insights: Insight[] }> {
  return request(`/session/${sessionId}/insights?limit=${limit}`);
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function sendVoiceAnalysis(
  audio: Blob,
  sessionId: string,
  dashboardContext = "",
  kpis = ""
): Promise<VoiceAnalysisResponse> {
  const form = new FormData();
  form.append("audio", audio, "voice.webm");
  form.append("session_id", sessionId);
  form.append("dashboard_context", dashboardContext);
  form.append("kpis", kpis);

  const res = await fetch(`${BASE_URL}/voice/analyse`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Voice analysis failed ${res.status}`));
  }

  return res.json() as Promise<VoiceAnalysisResponse>;
}

export async function sendVoiceTranscription(
  audio: Blob
): Promise<VoiceTranscriptionResponse> {
  const form = new FormData();
  form.append("audio", audio, "voice.webm");

  const res = await fetch(`${BASE_URL}/voice/transcribe-only`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Voice transcription failed ${res.status}`));
  }

  return res.json() as Promise<VoiceTranscriptionResponse>;
}

// ─── Data Upload ──────────────────────────────────────────────────────────────

export async function uploadFile(file: File, sessionId: string): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(
    `${BASE_URL}/data/upload?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST", body: form }
    // No Content-Type header — browser sets multipart/form-data boundary
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed ${res.status}: ${body}`);
  }
  return res.json() as Promise<UploadResponse>;
}

// ─── DB Connect ───────────────────────────────────────────────────────────────

export async function connectDatabase(
  payload: DBConnectRequest
): Promise<{ status: string; message?: string }> {
  return request("/data/connect-db", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Data Preview ─────────────────────────────────────────────────────────────

export async function getDataPreview(
  sessionId: string,
  rows = 10
): Promise<DataPreviewResponse> {
  return request(
    `/data/preview?session_id=${encodeURIComponent(sessionId)}&rows=${rows}`
  );
}

// ─── Charts ───────────────────────────────────────────────────────────────────

export async function generateChart(
  sessionId: string,
  query: string,
  chartType?: string
): Promise<ChartResult> {
  return request("/charts/generate", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      message: query,
      // Only include chart_type when user explicitly picked one (not "auto")
      ...(chartType && chartType !== "auto" ? { chart_type: chartType } : {}),
    }),
  });
}

export async function getChartSuggestions(
  sessionId: string
): Promise<{ suggestions: string[]; chart_types: { type: string; label: string; desc: string }[] }> {
  return request(`/session/${sessionId}/chart-suggestions`);
}

// ─── Insights ─────────────────────────────────────────────────────────────────

export async function discoverInsights(
  sessionId: string,
  goal?: string
): Promise<InsightResult> {
  return request("/insights/discover", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message: goal ?? "" }),
  });
}