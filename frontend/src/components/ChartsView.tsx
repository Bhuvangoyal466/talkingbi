import { useState, useEffect } from "react";
import {
  Loader2, BarChart3, AlertCircle, ChevronDown, Code2,
  History, Sparkles, TrendingUp, Lightbulb,
  BarChart2, ChevronRight, PieChart, Activity, ScatterChart,
} from "lucide-react";
import { generateChart, getSessionCharts, getChartSuggestions } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import type { ChartResult, ChartData } from "@/types/api";
import InteractiveChart, { MiniChart } from "@/components/InteractiveChart";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// ─── Chart type icon ──────────────────────────────────────────────────────────

const CHART_TYPE_ICONS: Record<string, React.ReactNode> = {
  bar: <BarChart2 size={13} />,
  horizontal_bar: <BarChart2 size={13} className="rotate-90" />,
  line: <TrendingUp size={13} />,
  area: <Activity size={13} />,
  pie: <PieChart size={13} />,
  scatter: <ScatterChart size={13} />,
  histogram: <BarChart3 size={13} />,
  grouped_bar: <BarChart2 size={13} />,
  stacked_bar: <BarChart2 size={13} />,
};

function ChartTypeIcon({ type }: { type: string }) {
  if (["line", "area"].includes(type)) return <TrendingUp size={12} />;
  return <BarChart2 size={12} />;
}

// ─── History item ─────────────────────────────────────────────────────────────

interface HistoryItem {
  chartData: ChartData;
  chartType: string;
  title: string;
  dataPoints: number;
  code?: string;
}

// ─── Empty state ──────────────────────────────────────────────────────────────

interface EmptyStateProps { suggestions: string[]; onSuggestionClick: (s: string) => void; loading: boolean; }

function EmptyState({ suggestions, onSuggestionClick, loading }: EmptyStateProps) {
  return (
    <div className="glass-card-light flex flex-col items-center justify-center py-20 text-center space-y-5">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center">
        <BarChart3 size={30} className="text-primary" />
      </div>
      <div>
        <p className="text-base font-semibold text-foreground">No charts yet</p>
        <p className="text-sm text-muted-foreground mt-1 max-w-xs">
          Upload a dataset from the sidebar, then describe the chart you want above.
        </p>
      </div>
      {suggestions.length > 0 && (
        <div className="space-y-3 w-full">
          <p className="text-xs font-medium text-muted-foreground">Try one of these:</p>
          <div className="flex flex-wrap gap-2 justify-center">
            {suggestions.map((s, i) => (
              <button key={i} onClick={() => { onSuggestionClick(s); }}
                disabled={loading}
                className="text-xs px-3 py-1.5 rounded-full border border-primary/30 bg-primary/5 text-primary hover:bg-primary/10 hover:border-primary/50 disabled:opacity-50 transition">
                "{s}"
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Chart types sidebar ──────────────────────────────────────────────────────

interface ChartTypesSidebarProps { chartTypes: ChartTypeMeta[]; }

function ChartTypesSidebar({ chartTypes }: ChartTypesSidebarProps) {
  return (
    <div className="glass-card-light p-4 h-fit sticky top-5 space-y-3">
      <div className="flex items-center gap-2">
        <Activity size={14} className="text-primary" />
        <h3 className="text-xs font-semibold text-foreground">Available Chart Types</h3>
      </div>
      <p className="text-[11px] text-muted-foreground">Based on your data, you can create:</p>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {chartTypes.map((ct) => (
          <div key={ct.type} className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-primary/5 transition">
            <div className="flex-shrink-0 w-6 h-6 rounded flex items-center justify-center bg-secondary/50 text-primary">
              {CHART_TYPE_ICONS[ct.type] || <BarChart3 size={12} />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground leading-tight">{ct.label}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{ct.desc}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-muted-foreground/60 border-t border-border/30 pt-2">
        Describe what you want: "Show {'{...}'} as a {'{chart_type}'}"
      </p>
    </div>
  );
}

// ─── Live chart generation panel ─────────────────────────────────────────────

interface ChartTypeMeta { type: string; label: string; desc: string; }

function LiveChartPanel() {
  const { sessionId, status } = useSession();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<ChartResult | null>(null);
  const [codeOpen, setCodeOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyItem, setHistoryItem] = useState<HistoryItem | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [chartTypes, setChartTypes] = useState<ChartTypeMeta[]>([]);

  const CHARTS_KEY = sessionId ? `talkingbi_charts_${sessionId}` : null;
  const CURRENT_KEY = sessionId ? `talkingbi_chart_current_${sessionId}` : null;

  // Restore history and current chart from sessionStorage when sessionId loads
  useEffect(() => {
    if (!sessionId) return;
    let restoredFromStorage = false;
    try {
      const storedHistory = sessionStorage.getItem(`talkingbi_charts_${sessionId}`);
      if (storedHistory) {
        const h = JSON.parse(storedHistory);
        if (Array.isArray(h) && h.length > 0) {
          setHistory(h);
          restoredFromStorage = true;
        }
      }
    } catch { /* ignore */ }
    try {
      const storedCurrent = sessionStorage.getItem(`talkingbi_chart_current_${sessionId}`);
      if (storedCurrent) setCurrent(JSON.parse(storedCurrent));
    } catch { /* ignore */ }

    if (restoredFromStorage) return;

    // No local cache — load from backend (session switch / server restart)
    getSessionCharts(sessionId).then((res) => {
      const items: HistoryItem[] = res.charts
        .filter((c) => c.chart_data?.values?.length)
        .map((c) => ({
          chartData: c.chart_data!,
          chartType: c.chart_type,
          title: c.title || c.chart_type,
          dataPoints: c.data_points,
          code: undefined,
        }));
      if (items.length > 0) {
        setHistory(items);
        const first = items[0];
        setCurrent({
          type: "chart",
          image_base64: "",
          chart_type: first.chartType,
          title: first.title,
          data_points: first.dataPoints,
          code: "",
          chart_data: first.chartData,
        } as ChartResult);
      }
    }).catch(() => {});
  }, [sessionId]);

  // Persist chart history to sessionStorage on change
  useEffect(() => {
    if (!CHARTS_KEY || history.length === 0) return;
    try {
      sessionStorage.setItem(CHARTS_KEY, JSON.stringify(history));
    } catch { /* ignore */ }
  }, [history, CHARTS_KEY]);

  // Persist current chart (strip image_base64 to save space)
  useEffect(() => {
    if (!CURRENT_KEY) return;
    if (!current) { sessionStorage.removeItem(CURRENT_KEY); return; }
    try {
      sessionStorage.setItem(CURRENT_KEY, JSON.stringify({ ...current, image_base64: "" }));
    } catch { /* ignore */ }
  }, [current, CURRENT_KEY]);

  const hasData = status?.has_data || status?.has_db;

  // Fetch data-aware suggestions when data becomes available
  useEffect(() => {
    if (!sessionId || !hasData) return;
    const key = `talkingbi_chart_suggestions_${sessionId}`;
    const cached = sessionStorage.getItem(key);
    if (cached) {
      try {
        const { suggestions: s, chart_types: c } = JSON.parse(cached);
        setSuggestions(s);
        setChartTypes(c);
        return;
      } catch { /* ignore */ }
    }
    getChartSuggestions(sessionId).then((res) => {
      setSuggestions(res.suggestions);
      setChartTypes(res.chart_types);
      try { sessionStorage.setItem(key, JSON.stringify(res)); } catch { /* ignore */ }
    }).catch(() => {});
  }, [sessionId, hasData]);

  const handleGenerate = async () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setCodeOpen(false);
    try {
      const res = await generateChart(sessionId, query, undefined);
      setCurrent(res);
      if (res.chart_data?.values?.length) {
        setHistory((prev) => [
          {
            chartData: res.chart_data!,
            chartType: res.chart_type,
            title: res.title,
            dataPoints: res.data_points,
            code: res.code,
          },
          ...prev.slice(0, 7),
        ]);
      }
      setQuery("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setQuery(suggestion);
  };

  return (
    <div className="space-y-5">
      {/* ── Query bar ── */}
      <div className="glass-card-light p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-primary" />
          <h3 className="text-sm font-semibold text-foreground">Generate Chart from Your Data</h3>
        </div>

        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
            placeholder={hasData ? 'e.g. "Show revenue by month as a pie chart" or "Plot sales by region as a bar chart"' : "Upload data first…"}
            disabled={!hasData || loading}
            className="flex-1 text-sm bg-transparent border border-border/50 rounded-xl px-4 py-2.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50 transition"
          />

          <button
            onClick={handleGenerate}
            disabled={!hasData || loading || !query.trim()}
            className="glass-card glow-hover flex items-center gap-2 px-5 py-2.5 text-sm text-primary font-medium disabled:opacity-40 transition rounded-xl"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <BarChart3 size={14} />}
            {loading ? "Generating…" : "Generate"}
          </button>
        </div>

        {!hasData && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <AlertCircle size={13} className="text-amber-400" />
            Upload a file or connect a database from the sidebar to generate live charts.
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
            <AlertCircle size={13} />
            {error}
          </div>
        )}
      </div>

      {/* ── Current chart or empty state ── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        <div className="lg:col-span-3">
          {current?.chart_data?.values?.length ? (
            <div className="glass-card-light p-5 space-y-4">
              <div className="flex items-start justify-between flex-wrap gap-2">
            <div className="space-y-1.5">
              {current.title && (
                <h3 className="text-lg font-bold text-foreground leading-tight">{current.title}</h3>
              )}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="flex items-center gap-1 text-[11px] px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-medium">
                  <ChartTypeIcon type={current.chart_type} />
                  {current.chart_type}
                </span>
                {current.data_points > 0 && (
                  <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-secondary text-muted-foreground">
                    {current.data_points.toLocaleString()} data points
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  X: <span className="text-foreground/70">{current.chart_data.x_axis_label}</span>
                  {" · "}
                  Y: <span className="text-foreground/70">{current.chart_data.y_axis_label}</span>
                </span>
              </div>
            </div>
            {current.justification && (
              <p className="text-xs text-muted-foreground italic max-w-xs text-right">{current.justification}</p>
            )}
          </div>

          <InteractiveChart chartData={current.chart_data} chartType={current.chart_type} height={340} />

          {current.code && (
            <Collapsible open={codeOpen} onOpenChange={setCodeOpen}>
              <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors mt-1">
                <Code2 size={12} />
                <span>{codeOpen ? "Hide Python Code" : "View equivalent Python Code"}</span>
                <ChevronDown size={12} className={`transition-transform duration-200 ${codeOpen ? "rotate-180" : ""}`} />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-2 bg-secondary/50 border border-border/30 p-3.5 rounded-xl text-[11px] overflow-x-auto whitespace-pre font-mono leading-relaxed">
                  {current.code}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          )}
            </div>
          ) : current?.image_base64 ? (
            <div className="glass-card-light p-5 space-y-3">
              <div className="flex items-center gap-2">
                {current.title && <h3 className="text-base font-bold text-foreground">{current.title}</h3>}
                <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-primary/10 text-primary">
                  {current.chart_type}
                </span>
              </div>
              <img src={`data:image/png;base64,${current.image_base64}`} alt={current.title}
                className="rounded-xl max-w-full border border-border/30" />
            </div>
          ) : (
            <EmptyState suggestions={suggestions} onSuggestionClick={handleSuggestionClick} loading={loading} />
          )}
        </div>
        <div className="lg:col-span-1">
          {hasData && chartTypes.length > 0 && (
            <ChartTypesSidebar chartTypes={chartTypes} />
          )}
        </div>
      </div>
      {/* ── Chart history ── */}
      {history.length > 0 && (
        <div className="glass-card-light p-5 space-y-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <History size={13} />
            <span className="font-medium">Recent charts</span>
            <span className="ml-auto">{history.length} / 8</span>
          </div>
          <div className="flex gap-2.5 overflow-x-auto pb-1">
            {history.map((item, i) => (
              <button key={i} onClick={() => setHistoryItem(item)}
                className="flex-shrink-0 flex flex-col items-center gap-1.5 p-2 rounded-xl border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-all group cursor-pointer"
                title={item.title || item.chartType}
              >
                <div className="overflow-hidden rounded-lg bg-secondary/30">
                  <MiniChart chartData={item.chartData} chartType={item.chartType} />
                </div>
                <span className="text-[10px] text-muted-foreground group-hover:text-foreground/70 transition-colors max-w-[72px] truncate">
                  {item.title || item.chartType}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── History dialog ── */}
      <Dialog open={!!historyItem} onOpenChange={(o) => !o && setHistoryItem(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              {historyItem?.title || historyItem?.chartType}
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-primary/10 text-primary font-normal">
                {historyItem?.chartType}
              </span>
            </DialogTitle>
          </DialogHeader>
          {historyItem && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                {historyItem.dataPoints > 0 && (
                  <span className="px-2.5 py-0.5 rounded-full bg-secondary">
                    {historyItem.dataPoints.toLocaleString()} pts
                  </span>
                )}
                <span>X: <span className="text-foreground/70">{historyItem.chartData.x_axis_label}</span></span>
                <span>Y: <span className="text-foreground/70">{historyItem.chartData.y_axis_label}</span></span>
              </div>
              <InteractiveChart chartData={historyItem.chartData} chartType={historyItem.chartType} height={360} />
              {historyItem.code && (
                <Collapsible>
                  <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    <Code2 size={12} /><span>View Python Code</span><ChevronRight size={12} />
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <pre className="mt-2 bg-secondary/50 border border-border/30 p-3 rounded-xl text-[11px] overflow-x-auto whitespace-pre font-mono">
                      {historyItem.code}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Main ChartsView ──────────────────────────────────────────────────────────

const ChartsView = () => (
  <div className="h-full overflow-y-auto bg-background">
    <div className="p-6 space-y-6 animate-fade-in max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Charts</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Ask a question about your data to generate an interactive chart
          </p>
        </div>
      </div>
      <LiveChartPanel />
    </div>
  </div>
);

export default ChartsView;
