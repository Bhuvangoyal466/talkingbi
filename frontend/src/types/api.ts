// ─── Requests ─────────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  session_id: string;
}

export interface VoiceAnalyseRequest {
  audio: File | Blob;
  session_id: string;
  dashboard_context?: string;
  kpis?: string;
}

export interface DBConnectRequest {
  db_path: string;
  session_id: string;
}

// ─── Session ──────────────────────────────────────────────────────────────────

export interface SessionNewResponse {
  session_id: string;
}

export interface SessionStatus {
  session_id: string;
  has_db: boolean;
  has_data: boolean;
  message_count: number;
  db_name: string | null;
  data_shape: [number, number] | null;
}

export interface ProviderInfo {
  provider: string;
  available: string[];
}

export interface SessionSummary {
  session_id: string;
  db_path: string;
  messages: number;
  insights: number;
  charts: number;
  uploads: number;
  preview: string;
  modified: number;
}

export interface SessionMessage {
  id: number;
  ts: number;
  role: string;
  content: string;
  intent: string | null;
  sql: string | null;
  rows_ret: number | null;
}

export interface SessionChart {
  id: number;
  ts: number;
  title: string;
  chart_type: string;
  query: string | null;
  data_points: number;
  chart_data: ChartData | null;
  justification: string | null;
}

export interface HealthResponse {
  status: string;
  active_sessions: number;
}

// ─── Upload / Preview ─────────────────────────────────────────────────────────

export interface UploadResponse {
  status: string;
  rows: number;
  columns: string[];
  dtypes: Record<string, string>;
  preview: Record<string, unknown>[];
}

export interface DataPreviewResponse {
  rows: number;
  columns: string[];
  dtypes: Record<string, string>;
  preview: Record<string, unknown>[];
}

// ─── Insight ──────────────────────────────────────────────────────────────────

export interface Insight {
  question: string;
  answer: string;
  evidence?: string;
  type: string;
  confidence?: number;
  code?: string;
  stats?: Record<string, unknown>;
  insight?: string;
}

// ─── Chat response union ──────────────────────────────────────────────────────

export interface SQLResultResponse {
  type: "sql_result";
  sql: string;
  data: { columns: string[]; rows: unknown[][] };
  rows_returned: number;
  iterations?: number;
}

// ─── Chart data structure ─────────────────────────────────────────────────────

export interface ChartDataPoint {
  x: string | number;
  y: number;
  category?: string;
}

export interface ChartData {
  values: ChartDataPoint[];
  x_axis_label: string;
  y_axis_label: string;
  title: string;
}

export interface ChartResultResponse {
  type: "chart";
  image_base64: string;
  chart_type: string;
  title: string;
  data_points: number;
  code: string;
  justification?: string;
  chart_data?: ChartData;
}

export interface InsightsResponse {
  type: "insights";
  goal: string;
  insights: Insight[];
  summary: string;
  total_insights: number;
}

export interface DataPrepResponse {
  type: "data_prep";
  success: boolean;
  pipeline: string[];
  shape: [number, number];
  columns: string[];
  preview: Record<string, unknown>[];
  turns?: number;
  error?: string;
}

export interface HybridResponse {
  type: "hybrid";
  data?: SQLResultResponse;
  chart?: ChartResultResponse;
  insights?: string[];
}

export interface ConversationResponse {
  type: "conversation";
  response: string;
}

export interface VoiceAnalysisResponse {
  success?: boolean;
  transcript: string;
  answer: string;
  relevant_kpis: string[];
  confidence: number;
  session_id: string;
  result_type: string;
  result?: ChatResponse;
}

export interface VoiceTranscriptionResponse {
  success?: boolean;
  transcript: string;
}

export interface ErrorResponse {
  type: "error";
  error: string;
}

export type ChatResponse =
  | SQLResultResponse
  | ChartResultResponse
  | InsightsResponse
  | DataPrepResponse
  | HybridResponse
  | ConversationResponse
  | ErrorResponse;

// ─── Direct endpoint result aliases ───────────────────────────────────────────

/** Returned by POST /charts/generate */
export type ChartResult = ChartResultResponse;

/** Returned by POST /insights/discover */
export type InsightResult = InsightsResponse;

// ─── Legacy aliases kept for compatibility ─────────────────────────────────────

export type SQLResult = SQLResultResponse;
export type DataPrepResult = DataPrepResponse;
export type ConversationResult = ConversationResponse;
export type HybridResult = HybridResponse;
