// ─── Request Types ────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  session_id: string;
}

export interface DBConnectRequest {
  db_path: string;
  session_id: string;
}

// ─── Response Types ───────────────────────────────────────────────────────────

export interface UploadResponse {
  status: string;
  rows: number;
  columns: string[];
  dtypes: Record<string, string>;
  preview: Record<string, unknown>[];
}

export interface ChatResponse {
  type: "SQL_QUERY" | "DATA_PREP" | "CHART" | "INSIGHT" | "HYBRID" | "CONVERSATION";
  session_id: string;
  result: SQLResult | ChartResult | InsightResult | DataPrepResult | ConversationResult;
}

export interface SessionStatus {
  session_id: string;
  has_db: boolean;
  has_data: boolean;
  message_count: number;
  db_name: string | null;
  data_shape: [number, number] | null;
}

// ─── Result Payloads (mirrors response.py) ────────────────────────────────────

export interface BaseResult {
  success: boolean;
  error?: string;
}

export interface SQLResult extends BaseResult {
  sql: string;
  columns: string[];
  rows: unknown[][];
  rows_returned: number;
}

export interface ChartResult extends BaseResult {
  image_base64: string;
  chart_type: string;
  title: string;
  data_points: number;
  code: string;
}

export interface InsightResult extends BaseResult {
  goal: string;
  insights: Insight[];
  summary: string;
  total_insights: number;
}

export interface Insight {
  question?: string;
  answer?: string;
  type?: string;
  evidence?: string;
  confidence?: number;
}

export interface DataPrepResult extends BaseResult {
  pipeline: string[];
  shape: [number, number];
  columns: string[];
  preview: Record<string, unknown>[];
}

export interface ConversationResult extends BaseResult {
  response: string;
}
