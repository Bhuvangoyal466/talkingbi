import { useState, useRef, useEffect, Fragment } from "react";
import {
  Send,
  Bot,
  User,
  Loader2,
  Volume2,
  BarChart3,
  ChevronDown,
  Code2,
  Layers,
  TrendingUp,
  PieChart as PieIcon,
  BarChart2,
} from "lucide-react";
import { sendChat, getSessionMessages } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import { useVoiceAgent } from "@/hooks/useVoiceAgent";
import InteractiveChart from "@/components/InteractiveChart";
import KpiCoverageCard from "@/components/KpiCoverageCard";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type {
  ChatResponse,
  SQLResultResponse,
  ChartResultResponse,
  InsightsResponse,
  DataPrepResponse,
  HybridResponse,
  Insight,
  ChartData,
  KpiCoverageInfo,
} from "@/types/api";
import { MicButton } from "@/components/voice/MicButton";
import { VoiceTranscriptBubble } from "@/components/voice/VoiceTranscriptBubble";
import { VoiceAudioPlayer } from "@/components/voice/VoiceAudioPlayer";

// ─── Error mapping ────────────────────────────────────────────────────────────

const ERROR_MESSAGES: [string, string][] = [
  ["LLMError", "The AI model encountered an issue. Please try again."],
  ["SQLGenerationError", "Could not generate a valid SQL query. Try rephrasing your request."],
  ["SchemaExtractionError", "Could not read the database schema. Ensure the database file is accessible."],
  ["ChartGenerationError", "Chart generation failed. Try a different visualization request."],
  ["InsightDiscoveryError", "Could not discover insights. Try a more specific analytical goal."],
  ["FileLoadError", "File could not be loaded. Ensure it is a valid CSV, Excel, or Parquet file."],
];

function mapError(error: string): string {
  for (const [key, msg] of ERROR_MESSAGES) {
    if (error.includes(key)) return msg;
  }
  return error;
}

// ─── Progress steps ───────────────────────────────────────────────────────────

const PROGRESS_STEPS = ["Routing", "Processing", "Generating", "Done"];

// ─── Message Types ────────────────────────────────────────────────────────────

interface BaseMessage { id: number; role: "user" | "ai"; }
interface TextMessage extends BaseMessage { kind: "text"; content: string; kpiCoverage?: KpiCoverageInfo; }
interface SQLMessage extends BaseMessage {
  kind: "sql"; summary: string; columns: string[];
  rows: unknown[][]; rowsReturned: number;
  kpiCoverage?: KpiCoverageInfo;
}
interface ChartMessage extends BaseMessage {
  kind: "chart";
  imageBase64: string;
  chartType: string;
  title: string;
  dataPoints: number;
  code: string;
  chartData?: ChartData;
  kpiCoverage?: KpiCoverageInfo;
}
interface InsightMessage extends BaseMessage {
  kind: "insight"; summary: string; goal: string; insights: Insight[];
  kpiCoverage?: KpiCoverageInfo;
}
interface DataPrepMessage extends BaseMessage {
  kind: "data_prep"; pipeline: string[];
  shape: [number, number]; preview: Record<string, unknown>[];
  kpiCoverage?: KpiCoverageInfo;
}
interface HybridMessage extends BaseMessage {
  kind: "hybrid";
  sqlData?: SQLResultResponse;
  chart?: ChartResultResponse;
  insightTexts?: string[];
  kpiCoverage?: KpiCoverageInfo;
}

type Message =
  | TextMessage | SQLMessage | ChartMessage
  | InsightMessage | DataPrepMessage | HybridMessage;

function formatSqlSummary(response: SQLResultResponse): string {
  if (response.answer?.trim()) {
    return response.answer.trim();
  }

  const cols = response.data?.columns ?? [];
  const rows = response.data?.rows ?? [];
  if (rows.length === 0) {
    return "I ran the analysis, but no matching rows were found.";
  }

  if (rows.length === 1 && cols.length > 0 && cols.length <= 4) {
    const firstRow = rows[0] as unknown[];
    const parts = cols.map((c, i) => `${c}: ${String(firstRow[i] ?? "")}`);
    return `Here is what I found: ${parts.join(", ")}.`;
  }

  return `I found ${response.rows_returned.toLocaleString()} rows. Here are the top results.`;
}

function extractKpiCoverage(response: ChatResponse): KpiCoverageInfo | undefined {
  const direct = (response as { kpi_coverage?: KpiCoverageInfo }).kpi_coverage;
  if (direct) return direct;

  const hybrid = response as HybridResponse;
  if (hybrid.data?.kpi_coverage) return hybrid.data.kpi_coverage;
  if (hybrid.chart?.kpi_coverage) return hybrid.chart.kpi_coverage;

  return undefined;
}

// ─── Response → Message builder ───────────────────────────────────────────────

function buildAIMessage(response: ChatResponse): Message {
  const base = { id: Date.now() + 1, role: "ai" as const };
  const kpiCoverage = extractKpiCoverage(response);
  switch (response.type) {
    case "sql_result":
    case "sql": {
      const r = response as SQLResultResponse;
      return {
        ...base, kind: "sql", summary: formatSqlSummary(r),
        columns: r.data?.columns ?? [], rows: r.data?.rows ?? [],
        rowsReturned: r.rows_returned,
        kpiCoverage,
      };
    }
    case "chart": {
      const r = response as ChartResultResponse;
      return {
        ...base, kind: "chart",
        imageBase64: r.image_base64,
        chartType: r.chart_type,
        title: r.title,
        dataPoints: r.data_points,
        code: r.code ?? "",
        chartData: r.chart_data,
        kpiCoverage,
      };
    }
    case "insights": {
      const r = response as InsightsResponse;
      return { ...base, kind: "insight", summary: r.summary, goal: r.goal, insights: r.insights, kpiCoverage };
    }
    case "data_prep": {
      const r = response as DataPrepResponse;
      return {
        ...base, kind: "data_prep",
        pipeline: r.pipeline ?? [],
        shape: r.shape as [number, number],
        preview: r.preview ?? [],
        kpiCoverage,
      };
    }
    case "hybrid": {
      const r = response as HybridResponse;
      return { ...base, kind: "hybrid", sqlData: r.data, chart: r.chart, insightTexts: r.insights, kpiCoverage };
    }
    case "error":
      return { ...base, kind: "text", content: `⚠️ ${mapError(response.error ?? "Unknown error")}` };
    default: {
      const resp = (response as { response?: string; answer?: string; summary?: string }).response
        ?? (response as { answer?: string }).answer
        ?? (response as { summary?: string }).summary;
      return { ...base, kind: "text", content: resp ?? "Done.", kpiCoverage };
    }
  }
}

const STAGGER_DELAY = ["", "delay-[40ms]", "delay-[80ms]", "delay-[120ms]", "delay-[160ms]"];

// ─── Chart type icon ──────────────────────────────────────────────────────────

function ChartTypeIcon({ type }: { type: string }) {
  if (type === "pie") return <PieIcon size={11} />;
  if (["line", "area"].includes(type)) return <TrendingUp size={11} />;
  return <BarChart2 size={11} />;
}

// ─── Sub-renderers ────────────────────────────────────────────────────────────

function SQLCard({ summary, columns, rows, rowsReturned }: {
  summary: string; columns: string[]; rows: unknown[][]; rowsReturned: number;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed">{summary}</p>

      {columns.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border/40">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-secondary/60">
                {columns.map((c) => (
                  <th key={c} className="px-3 py-2 text-left text-muted-foreground font-medium whitespace-nowrap">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(rows as unknown[][]).slice(0, 10).map((row, i) => (
                <tr key={i} className="border-t border-border/30 hover:bg-secondary/30 transition-colors">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-2 text-foreground/80 whitespace-nowrap">{String(cell ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{rowsReturned.toLocaleString()} rows returned</p>
    </div>
  );
}

function ChartCard({ imageBase64, chartType, title, dataPoints, code, chartData }: {
  imageBase64: string; chartType: string; title: string;
  dataPoints: number; code: string; chartData?: ChartData;
}) {
  const [codeOpen, setCodeOpen] = useState(false);
  const hasInteractive = !!chartData?.values?.length;

  return (
    <div className="space-y-2.5 w-full">
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <BarChart3 size={13} className="text-muted-foreground" />
        <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
          <ChartTypeIcon type={chartType} />
          {chartType}
        </span>
        {dataPoints > 0 && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-secondary text-muted-foreground">
            {dataPoints.toLocaleString()} pts
          </span>
        )}
      </div>

      {title && <p className="text-sm font-semibold text-foreground">{title}</p>}

      {/* Chart — interactive if chart_data is available, else static PNG */}
      {hasInteractive ? (
        <div className="w-full rounded-xl overflow-hidden bg-secondary/20 border border-border/20 py-2">
          <InteractiveChart chartData={chartData!} chartType={chartType} height={260} />
        </div>
      ) : imageBase64 ? (
        <img
          src={`data:image/png;base64,${imageBase64}`}
          alt={title}
          className="rounded-xl max-w-full border border-border/30"
        />
      ) : null}

      {/* Code toggle */}
      {code && (
        <Collapsible open={codeOpen} onOpenChange={setCodeOpen}>
          <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <Code2 size={12} />
            <span>{codeOpen ? "Hide Code" : "View Python Code"}</span>
            <ChevronDown size={12} className={`transition-transform duration-200 ${codeOpen ? "rotate-180" : ""}`} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <pre className="mt-1 bg-secondary/60 border border-border/30 p-3 rounded-xl text-[11px] overflow-x-auto whitespace-pre font-mono">
              {code}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

function DataPrepCard({ pipeline, shape, preview }: {
  pipeline: string[]; shape: [number, number]; preview: Record<string, unknown>[];
}) {
  const cols = preview.length > 0 ? Object.keys(preview[0]) : [];
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 flex-wrap">
        <Layers size={13} className="text-primary mr-1" />
        {pipeline.map((step, i) => (
          <Fragment key={i}>
            <span className="text-[11px] px-2 py-1 rounded-lg bg-primary/10 text-primary font-medium">{step}</span>
            {i < pipeline.length - 1 && <span className="text-xs text-muted-foreground">→</span>}
          </Fragment>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        ✅ Shape: {shape[0].toLocaleString()} rows × {shape[1]} cols
      </p>
      {cols.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border/40">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-secondary/60">
                {cols.map((c) => (
                  <th key={c} className="px-3 py-2 text-left text-muted-foreground font-medium whitespace-nowrap">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.slice(0, 5).map((row, i) => (
                <tr key={i} className="border-t border-border/30 hover:bg-secondary/30">
                  {cols.map((c) => (
                    <td key={c} className="px-3 py-2 text-foreground/80 whitespace-nowrap">{String(row[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InsightCardInline({ insight, index }: { insight: Insight; index: number }) {
  return (
    <div className={`glass-card p-3 space-y-1 animate-fade-in ${STAGGER_DELAY[index] ?? ""}`}>
      {insight.question && <p className="text-xs font-medium text-primary">{insight.question}</p>}
      {insight.answer && <p className="text-xs text-foreground/80 leading-relaxed">{insight.answer}</p>}
      <div className="flex items-center gap-2">
        {insight.type && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">{insight.type}</span>
        )}
        {insight.confidence !== undefined && (
          <span className="text-[10px] text-muted-foreground">{Math.round(insight.confidence * 100)}% confidence</span>
        )}
      </div>
    </div>
  );
}

function HybridCard({ msg }: { msg: HybridMessage }) {
  return (
    <div className="space-y-4">
      {msg.sqlData && (
        <SQLCard sql={msg.sqlData.sql}
          columns={msg.sqlData.data?.columns ?? []}
          rows={msg.sqlData.data?.rows ?? []}
          rowsReturned={msg.sqlData.rows_returned} />
      )}
      {msg.chart && (
        <ChartCard
          imageBase64={msg.chart.image_base64}
          chartType={msg.chart.chart_type}
          title={msg.chart.title}
          dataPoints={msg.chart.data_points}
          code={msg.chart.code ?? ""}
          chartData={msg.chart.chart_data}
        />
      )}
      {msg.insightTexts && msg.insightTexts.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Top Insights</p>
          {msg.insightTexts.map((t, i) => (
            <p key={i} className="text-xs text-foreground/80">• {t}</p>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Message Bubble ───────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  let content: React.ReactNode;
  if (msg.kind === "sql") {
    content = <SQLCard summary={msg.summary} columns={msg.columns} rows={msg.rows} rowsReturned={msg.rowsReturned} />;
  } else if (msg.kind === "chart") {
    content = (
      <ChartCard
        imageBase64={msg.imageBase64}
        chartType={msg.chartType}
        title={msg.title}
        dataPoints={msg.dataPoints}
        code={msg.code}
        chartData={msg.chartData}
      />
    );
  } else if (msg.kind === "insight") {
    content = (
      <div className="space-y-3">
        {msg.goal && <p className="text-xs text-muted-foreground italic">{msg.goal}</p>}
        {msg.summary && <p className="text-sm leading-relaxed">{msg.summary}</p>}
        {msg.insights.slice(0, 5).map((ins, i) => (
          <InsightCardInline key={i} insight={ins} index={i} />
        ))}
      </div>
    );
  } else if (msg.kind === "data_prep") {
    content = <DataPrepCard pipeline={msg.pipeline} shape={msg.shape} preview={msg.preview} />;
  } else if (msg.kind === "hybrid") {
    content = <HybridCard msg={msg} />;
  } else {
    content = <span className="whitespace-pre-wrap">{(msg as TextMessage).content}</span>;
  }

  const kpiCoverage = msg.kpiCoverage;

  // Chart messages get a wider bubble so the chart looks good
  const isChartMsg = msg.kind === "chart" || msg.kind === "hybrid";

  return (
    <div className={`flex gap-3 animate-fade-in ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-xl bg-primary/20 flex items-center justify-center flex-shrink-0 mt-1">
          <Bot size={16} className="text-primary" />
        </div>
      )}
      <div
        className={`px-5 py-3.5 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? "max-w-[78%] bg-primary text-primary-foreground rounded-br-md"
            : isChartMsg
            ? "w-full max-w-[92%] glass-card text-foreground rounded-bl-md"
            : "max-w-[78%] glass-card text-foreground rounded-bl-md"
        }`}
      >
        {content}
        {kpiCoverage && (
          <div className="mt-4">
            <KpiCoverageCard coverage={kpiCoverage} />
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-xl bg-secondary flex items-center justify-center flex-shrink-0 mt-1">
          <User size={16} className="text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

const INITIAL: Message[] = [
  {
    id: 1,
    role: "ai",
    kind: "text",
    content:
      "Hello! I'm your TalkingBI assistant. Upload a file or connect a database from the sidebar, then ask me anything about your data.",
  },
];

interface ChatViewProps {
  quickMessage?: string;
  onQuickMessageConsumed?: () => void;
}

const MSGS_KEY = (sid: string) => `talkingbi_msgs_${sid}`;

const ChatView = ({ quickMessage, onQuickMessageConsumed }: ChatViewProps) => {
  const { sessionId, status, refreshStatus } = useSession();
  const [messages, setMessages] = useState<Message[]>(INITIAL);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [progressStep, setProgressStep] = useState(-1);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const stepTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const {
    voiceState,
    error: voiceError,
    partialTranscript,
    spokenAudio,
    clearSpokenAudio,
    toggleListening,
  } = useVoiceAgent({
    sessionId,
    onResponse: (response) => {
      setMessages((prev) => [...prev, buildAIMessage(response)]);
      void refreshStatus();
    },
  });
  const isVoiceActive = ["listening", "transcribing", "processing", "speaking"].includes(voiceState);

  // Restore messages from sessionStorage when sessionId becomes available
  useEffect(() => {
    if (!sessionId) return;
    const stored = sessionStorage.getItem(MSGS_KEY(sessionId));
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Message[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
          return;
        }
      } catch { /* bad JSON */ }
    }
    // No local cache – fetch from backend (handles session-switch and page refresh
    // for sessions that were never stored in this browser)
    getSessionMessages(sessionId).then((res) => {
      if (res.messages.length === 0) {
        setMessages(INITIAL);
        return;
      }
      const restored: Message[] = [];
      let counter = 1;
      for (const m of res.messages) {
        if (m.role === "user") {
          restored.push({ id: counter++, role: "user", kind: "text", content: m.content });
          continue;
        }
        // AI message — reconstruct based on stored intent
        if (m.intent === "sql" || m.intent === "sql_result") {
          restored.push({
            id: counter++, role: "ai", kind: "sql",
            summary: m.content || `I found ${(m.rows_ret ?? 0).toLocaleString()} rows.`,
            columns: [], rows: [],
            rowsReturned: m.rows_ret ?? 0,
            kpiCoverage: (m as { kpi_coverage?: KpiCoverageInfo }).kpi_coverage,
          });
        } else if (m.intent === "chart") {
          // Chart full data isn't in messages table; show a text summary
          restored.push({
            id: counter++, role: "ai", kind: "text",
            content: m.content || "📊 Chart generated (view in Charts tab)",
            kpiCoverage: (m as { kpi_coverage?: KpiCoverageInfo }).kpi_coverage,
          });
        } else if (m.intent === "insights") {
          restored.push({
            id: counter++, role: "ai", kind: "text",
            content: m.content || "💡 Insights discovered (view in Insights tab)",
            kpiCoverage: (m as { kpi_coverage?: KpiCoverageInfo }).kpi_coverage,
          });
        } else {
          restored.push({
            id: counter++,
            role: "ai",
            kind: "text",
            content: m.content,
            kpiCoverage: (m as { kpi_coverage?: KpiCoverageInfo }).kpi_coverage,
          });
        }
      }
      setMessages(restored);
      try {
        sessionStorage.setItem(MSGS_KEY(sessionId), JSON.stringify(restored));
      } catch { /* ignore */ }
    }).catch(() => setMessages(INITIAL));
  }, [sessionId]);

  // Persist messages to sessionStorage on every change (strip large base64 to save space)
  useEffect(() => {
    if (!sessionId || messages.length === 0) return;
    const slim = messages.map((m) =>
      m.kind === "chart" ? { ...m, imageBase64: "" } : m
    );
    try {
      sessionStorage.setItem(MSGS_KEY(sessionId), JSON.stringify(slim));
    } catch { /* QuotaExceededError — ignore */ }
  }, [messages, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (quickMessage && !loading) {
      handleSend(quickMessage);
      onQuickMessageConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quickMessage]);

  const startProgress = () => {
    setProgressStep(0);
    stepTimers.current = [
      setTimeout(() => setProgressStep(1), 2000),
      setTimeout(() => setProgressStep(2), 3500),
      setTimeout(() => setProgressStep(3), 5000),
    ];
  };

  const stopProgress = () => {
    stepTimers.current.forEach(clearTimeout);
    stepTimers.current = [];
    setProgressStep(-1);
  };

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    const userMsg: Message = { id: Date.now(), role: "user", kind: "text", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    startProgress();

    try {
      const response = await sendChat({ message: text, session_id: sessionId });
      const aiMsg = buildAIMessage(response);
      setMessages((prev) => [...prev, aiMsg]);
      await refreshStatus();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 2,
          role: "ai",
          kind: "text",
          content: `⚠️ Could not reach the backend. Make sure the FastAPI server is running on port 8000.\n\n${(err as Error).message}`,
        },
      ]);
    } finally {
      stopProgress();
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <VoiceAudioPlayer audio={spokenAudio} onConsumed={clearSpokenAudio} />

      {/* Context counter */}
      {status && status.message_count > 0 && (
        <div className="flex justify-center pt-3">
          <span className="text-[11px] px-3 py-1 rounded-full bg-secondary/60 text-muted-foreground">
            {status.message_count} message{status.message_count !== 1 ? "s" : ""} in context
          </span>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {loading && (
          <div className="flex gap-3 justify-start animate-fade-in">
            <div className="w-8 h-8 rounded-xl bg-primary/20 flex items-center justify-center flex-shrink-0 mt-1">
              <Bot size={16} className="text-primary" />
            </div>
            <div className="glass-card rounded-bl-md px-5 py-3.5 flex items-center gap-3 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              {progressStep >= 0 ? (
                <div className="flex items-center gap-1.5 text-xs">
                  {PROGRESS_STEPS.map((step, i) => (
                    <Fragment key={step}>
                      <span className={i <= progressStep ? "text-primary font-medium" : "text-muted-foreground/40"}>
                        {step}
                      </span>
                      {i < PROGRESS_STEPS.length - 1 && (
                        <span className="text-muted-foreground/30">→</span>
                      )}
                    </Fragment>
                  ))}
                </div>
              ) : (
                <span>Thinking…</span>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="px-6 pb-6">
        <VoiceTranscriptBubble transcript={partialTranscript} visible={Boolean(partialTranscript) && isVoiceActive} />
        <div
          className={`pill-input flex items-center gap-3 shadow-lg shadow-black/10 transition-all duration-200 ${
            voiceState === "listening" ? "ring-2 ring-primary/60 shadow-primary/10" : ""
          }`}
        >
          <MicButton state={voiceState} onToggle={toggleListening} disabled={loading && !isVoiceActive} />

          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="Ask anything about your data…"
            disabled={loading || isVoiceActive}
            className="flex-1 bg-transparent text-foreground text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={loading || !input.trim() || isVoiceActive}
            className="w-9 h-9 rounded-full bg-primary flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-40"
          >
            {loading ? (
              <Loader2 size={15} className="text-primary-foreground animate-spin" />
            ) : (
              <Send size={15} className="text-primary-foreground" />
            )}
          </button>
        </div>

        <div className="mt-2 flex items-center justify-between gap-3 px-1 text-[11px] min-h-[18px]">
          <div className="flex items-center gap-2">
            {voiceState === "listening" && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-red-300 border border-red-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                Listening
              </span>
            )}
            {voiceState === "transcribing" && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-primary border border-primary/20">
                <Loader2 size={10} className="animate-spin" />
                Transcribing
              </span>
            )}
            {voiceState === "processing" && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-300 border border-amber-500/20">
                <Loader2 size={10} className="animate-spin" />
                Processing
              </span>
            )}
            {voiceState === "speaking" && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-300 border border-emerald-500/20">
                <Volume2 size={10} />
                Speaking
              </span>
            )}
          </div>

          {voiceError ? (
            <span className="text-red-400 truncate max-w-[70%] text-right">
              {voiceError}
            </span>
          ) : (
            <span className="text-muted-foreground/70 text-right">
              {voiceState === "idle"
                ? "Tap the mic to ask a question with your voice."
                : "Voice input is active. The response will appear automatically."}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatView;
