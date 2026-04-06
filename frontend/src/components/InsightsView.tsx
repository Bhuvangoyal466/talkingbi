import { useState, useEffect } from "react";
import {
  Lightbulb,
  TrendingUp,
  AlertCircle,
  CheckCircle,
  Loader2,
  RefreshCw,
  Info,
  ChevronDown,
  Copy,
} from "lucide-react";
import { discoverInsights, getSessionInsights } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import type { Insight } from "@/types/api";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

// ─── Insight type → style mapping ────────────────────────────────────────────

const TYPE_MAP: Record<
  string,
  { icon: React.ElementType; color: string; label: string }
> = {
  Descriptive:  { icon: Info,         color: "bg-primary/10 text-primary",         label: "Descriptive"  },
  Diagnostic:   { icon: AlertCircle,  color: "bg-amber-500/10 text-amber-400",     label: "Diagnostic"   },
  Predictive:   { icon: TrendingUp,   color: "bg-emerald-500/10 text-emerald-400", label: "Predictive"   },
  Prescriptive: { icon: CheckCircle,  color: "bg-sky-500/10 text-sky-400",         label: "Prescriptive" },
  default:      { icon: Lightbulb,    color: "bg-primary/10 text-primary",         label: "Insight"      },
};

const FILTER_TYPES = ["All", "Descriptive", "Diagnostic", "Predictive", "Prescriptive"];

const STAGGER_DELAY = [
  "",
  "delay-[60ms]",
  "delay-[120ms]",
  "delay-[180ms]",
  "delay-[240ms]",
  "delay-[300ms]",
];

function getStyle(type?: string) {
  if (!type) return TYPE_MAP.default;
  return TYPE_MAP[type] ?? TYPE_MAP.default;
}

// ─── Single insight card ──────────────────────────────────────────────────────

function InsightCard({ insight, index }: { insight: Insight; index: number }) {
  const style = getStyle(insight.type);
  const Icon = style.icon;
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const delayClass = STAGGER_DELAY[index] ?? "";

  return (
    <div
      className={`glass-card glow-hover p-5 flex items-start gap-4 animate-fade-in ${delayClass}`}
    >
      <div
        className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${style.color}`}
      >
        <Icon size={20} />
      </div>
      <div className="flex-1 min-w-0">
        {insight.question && (
          <h3 className="text-sm font-semibold text-foreground leading-snug">
            {insight.question}
          </h3>
        )}
        {insight.answer && (
          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
            {insight.answer}
          </p>
        )}
        {insight.evidence && (
          <Collapsible open={evidenceOpen} onOpenChange={setEvidenceOpen} className="mt-2">
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <span>Show evidence</span>
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${evidenceOpen ? "rotate-180" : ""}`}
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <p className="text-xs text-muted-foreground/70 mt-1 italic pl-1">
                {insight.evidence}
              </p>
            </CollapsibleContent>
          </Collapsible>
        )}
        <div className="flex items-center gap-3 mt-2">
          <span className={`text-[11px] px-2 py-0.5 rounded-full ${style.color}`}>
            {style.label}
          </span>
          {insight.confidence !== undefined && (
            <span className="text-[11px] text-muted-foreground">
              {Math.round(insight.confidence * 100)}% confidence
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Placeholder cards shown before first discovery ──────────────────────────

const PLACEHOLDER_INSIGHTS: Insight[] = [
  {
    question: "Revenue Trend",
    answer: "Upload a file or connect a database and click Discover to generate real insights.",
    type: "Descriptive",
    confidence: undefined,
  },
  {
    question: "Data Quality",
    answer: "TalkingBI will analyse your data and surface actionable findings automatically.",
    type: "Diagnostic",
    confidence: undefined,
  },
  {
    question: "Growth Opportunities",
    answer: "Insights are scored by confidence and novelty so the most valuable ones surface first.",
    type: "Predictive",
    confidence: undefined,
  },
];

// ─── Main Component ───────────────────────────────────────────────────────────

const InsightsView = () => {
  const { sessionId, status } = useSession();

  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [summary, setSummary] = useState<string>("");
  const [refinedGoal, setRefinedGoal] = useState<string>("");
  const [discovered, setDiscovered] = useState(false);
  const [activeFilter, setActiveFilter] = useState("All");
  const [copied, setCopied] = useState(false);

  const INSIGHTS_KEY = sessionId ? `talkingbi_insights_${sessionId}` : null;

  // Restore insights from sessionStorage when sessionId loads
  useEffect(() => {
    if (!sessionId) return;
    try {
      const stored = sessionStorage.getItem(`talkingbi_insights_${sessionId}`);
      if (stored) {
        const data = JSON.parse(stored);
        if (data.insights?.length) {
          setInsights(data.insights);
          setSummary(data.summary ?? "");
          setRefinedGoal(data.refinedGoal ?? "");
          setDiscovered(true);
          return;
        }
      }
    } catch { /* ignore */ }
    // No local cache — load from backend
    getSessionInsights(sessionId).then((res) => {
      if (res.insights.length > 0) {
        setInsights(res.insights);
        setSummary((res.insights[0] as { summary?: string }).summary ?? "");
        setDiscovered(true);
      }
    }).catch(() => {});
  }, [sessionId]);

  // Persist insights to sessionStorage when they change
  useEffect(() => {
    if (!INSIGHTS_KEY || !discovered) return;
    try {
      sessionStorage.setItem(INSIGHTS_KEY, JSON.stringify({ insights, summary, refinedGoal }));
    } catch { /* ignore */ }
  }, [insights, summary, refinedGoal, discovered, INSIGHTS_KEY]);

  const hasData = status?.has_data || status?.has_db;

  const handleDiscover = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await discoverInsights(sessionId, goal);
      setInsights(result.insights);
      setSummary(result.summary);
      setRefinedGoal(result.goal ?? "");
      setDiscovered(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopySummary = async () => {
    if (!summary) return;
    try {
      await navigator.clipboard.writeText(summary);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  const filteredInsights =
    activeFilter === "All"
      ? insights
      : insights.filter((i) => i.type === activeFilter);

  const displayedInsights = discovered ? filteredInsights : PLACEHOLDER_INSIGHTS;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-foreground">Auto Insights</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            AI-generated insights from your connected data source.
          </p>
          {discovered && refinedGoal && (
            <p className="text-xs text-primary mt-1 italic">{refinedGoal}</p>
          )}
        </div>
        <button
          onClick={handleDiscover}
          disabled={loading || !hasData}
          title={!hasData ? "Upload data or connect a database first" : "Discover insights"}
          className="glass-card glow-hover flex items-center gap-2 px-4 py-2.5 text-sm text-primary font-medium disabled:opacity-40 whitespace-nowrap"
        >
          {loading ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          {loading ? "Discovering…" : "Discover"}
        </button>
      </div>

      {/* Goal input */}
      <div className="flex gap-2">
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Optional: specify an analytical goal, e.g. 'find revenue drivers'"
          className="flex-1 pill-input text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50 rounded-xl px-4 py-2.5 bg-secondary/80 border border-border/50"
        />
      </div>

      {/* No data warning */}
      {!hasData && (
        <div className="glass-card p-4 flex items-center gap-3 border-amber-500/30">
          <AlertCircle size={16} className="text-amber-400 flex-shrink-0" />
          <p className="text-sm text-muted-foreground">
            Upload a CSV/Excel file or connect a database from the sidebar to enable insight discovery.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="glass-card p-4 flex items-center gap-3 border-red-500/30">
          <AlertCircle size={16} className="text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      {/* Executive summary */}
      {summary && (
        <div className="glass-card p-5 border-primary/20">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              Executive Summary
            </p>
            <button
              onClick={handleCopySummary}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Copy summary"
            >
              <Copy size={12} />
              {copied ? "Copied!" : "Copy Summary"}
            </button>
          </div>
          <p className="text-sm text-foreground/80 leading-relaxed">{summary}</p>
        </div>
      )}

      {/* Filter bar + count */}
      {discovered && insights.length > 0 && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            {FILTER_TYPES.map((f) => (
              <button
                key={f}
                onClick={() => setActiveFilter(f)}
                className={`text-[11px] px-3 py-1 rounded-full transition-all ${
                  activeFilter === f
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-muted-foreground hover:text-foreground"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <span className="text-[11px] px-3 py-1 rounded-full bg-secondary/60 text-muted-foreground whitespace-nowrap">
            Showing {filteredInsights.length} of {insights.length} insights
          </span>
        </div>
      )}

      {/* Insight cards */}
      <div className="grid gap-4">
        {displayedInsights.map((insight, i) => (
          <InsightCard key={i} insight={insight} index={i} />
        ))}
        {discovered && filteredInsights.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground text-center py-8">
            No insights match the selected filter. Try "All" or a different type.
          </p>
        )}
      </div>
    </div>
  );
};

export default InsightsView;
