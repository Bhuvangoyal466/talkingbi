import {
  Upload,
  Sparkles,
  TrendingUp,
  FileText,
  Wand2,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCw,
  Eye,
  History,
  MessageSquare,
  ChevronRight,
  Trash2,
} from "lucide-react";
import { useRef, useState } from "react";
import { uploadFile, getDataPreview, listPastSessions, deletePastSession } from "@/lib/api";
import { useSession } from "@/hooks/use-session";
import type { DataPreviewResponse, SessionSummary } from "@/types/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface AppSidebarProps {
  onQuickAction: (action: string) => void;
  activeTab: string;
}

type UploadState = "idle" | "uploading" | "success" | "error";
const AppSidebar = ({ onQuickAction }: AppSidebarProps) => {
  const { sessionId, status, refreshStatus, clearSession, switchSession } = useSession();

  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadInfo, setUploadInfo] = useState<string>("");
  const [uploadExt, setUploadExt] = useState<string>("");

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<DataPreviewResponse | null>(null);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [pastSessions, setPastSessions] = useState<SessionSummary[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ─── File Upload ────────────────────────────────────────────────────────────
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    setUploadState("uploading");
    setUploadInfo("");
    setUploadExt(ext);

    try {
      const res = await uploadFile(file, sessionId);
      setUploadState("success");
      setUploadInfo(`${res.rows} rows · ${res.columns.length} cols`);
      await refreshStatus();
    } catch (err) {
      setUploadState("error");
      setUploadInfo((err as Error).message);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // ─── Data Preview ───────────────────────────────────────────────────────────
  const handlePreview = async () => {
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      const data = await getDataPreview(sessionId, 10);
      setPreviewData(data);
    } catch (err) {
      setPreviewData(null);
      console.error("Preview failed:", err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await listPastSessions();
      setPastSessions(res.sessions);
    } catch (err) {
      console.error("Failed to load session history:", err);
    } finally { setHistoryLoading(false); }
  };

  const viewSession = async (s: SessionSummary) => {
    // Switch the active session to this one and navigate to the chat tab
    await switchSession(s.session_id);
    setHistoryOpen(false);
    onQuickAction("__goto_chat__");
  };

  const handleDeleteSession = async (e: React.MouseEvent, s: SessionSummary) => {
    e.stopPropagation();
    try {
      await deletePastSession(s.session_id);
      setPastSessions((prev) => prev.filter((x) => x.session_id !== s.session_id));
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  // ─── Derived status ─────────────────────────────────────────────────────────
  const hasData = status?.has_data ?? uploadState === "success";
  const canPreview = hasData;

  return (
    <aside className="w-72 min-h-screen bg-sidebar flex flex-col border-r border-border/50 p-5 gap-6">
      {/* Branding */}
      <div className="mb-2">
        <h1 className="text-xl font-bold text-foreground tracking-tight">TalkingBI</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Conversational Business Intelligence</p>
      </div>

      {/* Data Sources */}
      <section className="space-y-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Data Sources
        </h2>

        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls,.parquet"
          className="hidden"
          aria-label="Upload data file (CSV, Excel, or Parquet)"
          onChange={handleFileChange}
        />

        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadState === "uploading"}
          className="w-full glass-card glow-hover flex items-center gap-3 px-4 py-3 text-sm text-foreground disabled:opacity-50"
        >
          {uploadState === "uploading" ? (
            <Loader2 size={16} className="text-primary animate-spin" />
          ) : uploadState === "success" ? (
            <CheckCircle2 size={16} className="text-emerald-400" />
          ) : uploadState === "error" ? (
            <XCircle size={16} className="text-red-400" />
          ) : (
            <Upload size={16} className="text-primary" />
          )}
          {uploadState === "uploading"
            ? "Uploading…"
            : uploadState === "success"
            ? "Uploaded ✓"
            : "Upload CSV, Excel or Parquet"}
        </button>

        {uploadState === "success" && uploadExt && (
          <span className="inline-block text-[11px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400">
            {uploadExt}
          </span>
        )}

        {uploadInfo && (
          <p
            className={`text-[11px] px-1 ${
              uploadState === "error" ? "text-red-400" : "text-emerald-400"
            }`}
          >
            {uploadInfo}
          </p>
        )}
      </section>

      {/* Quick Actions */}
      <section className="space-y-3 flex-1">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Quick Actions
        </h2>
        <div className="grid grid-cols-2 gap-2">
          {[
            { icon: Sparkles, label: "Auto Insights", action: "auto-insights" },
            { icon: TrendingUp, label: "Trend Chart", action: "trend-chart" },
            { icon: FileText, label: "Data Summary", action: "data-summary" },
            { icon: Wand2, label: "Clean Data", action: "clean-data" },
          ].map((item) => (
            <button
              key={item.action}
              onClick={() => onQuickAction(item.action)}
              className="glass-card glow-hover flex flex-col items-center gap-2 px-3 py-4 text-xs text-foreground font-medium"
            >
              <item.icon size={18} className="text-primary" />
              {item.label}
            </button>
          ))}
        </div>

        {/* Preview Data button */}
        {canPreview && (
          <button
            onClick={handlePreview}
            className="w-full glass-card glow-hover flex items-center gap-3 px-4 py-3 text-sm text-foreground"
          >
            <Eye size={16} className="text-primary" />
            Preview Data
          </button>
        )}

        {/* Session History button */}
        <button
          onClick={() => { setHistoryOpen(true); loadHistory(); }}
          className="w-full glass-card glow-hover flex items-center gap-3 px-4 py-3 text-sm text-foreground"
        >
          <History size={16} className="text-primary" />
          Session History
        </button>
      </section>

      {/* Session Status */}
      <section className="border-t border-border/50 pt-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-muted-foreground">Session</p>
          {/* New Session button */}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
                title="Start a new session"
              >
                <RefreshCw size={11} />
                New
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Start a new session?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will clear all loaded data, chat history, and the current session.
                  This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={async () => {
                    await clearSession();
                    setUploadState("idle");
                    setUploadInfo("");
                    setUploadExt("");
                    setPreviewData(null);
                  }}
                >
                  New Session
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        <p className="text-[10px] text-muted-foreground/60 font-mono truncate">{sessionId || "—"}</p>

        <div className="flex gap-2 flex-wrap mt-1">
          <div className="flex flex-col gap-0.5">
            <span
              className={`text-[11px] px-2 py-0.5 rounded-full ${
                hasData
                  ? "bg-sky-500/10 text-sky-400"
                  : "bg-secondary text-muted-foreground"
              }`}
            >
              {hasData ? "Data ✓" : "No Data"}
            </span>
            {hasData && status?.data_shape && (
              <span className="text-[10px] text-muted-foreground/70 px-1">
                {status.data_shape[0].toLocaleString()} rows × {status.data_shape[1]} cols
              </span>
            )}
          </div>
        </div>

        {status && (
          <p className="text-[10px] text-muted-foreground/50 mt-1">
            {status.message_count} messages
          </p>
        )}
      </section>

      {/* Session History Dialog — click a session to open it in the chat */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-w-xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History size={16} className="text-primary" />
              Session History
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto min-h-0">
            {historyLoading ? (
              <div className="flex items-center justify-center py-10 gap-2 text-sm text-muted-foreground">
                <Loader2 size={16} className="animate-spin" /> Loading sessions…
              </div>
            ) : pastSessions.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No past sessions found.</p>
            ) : (
              <div className="space-y-2 pr-1">
                {pastSessions.map((s) => (
                  <div key={s.session_id} className="relative group">
                    <button
                      onClick={() => viewSession(s)}
                      className="w-full glass-card glow-hover text-left px-4 py-3 space-y-1"
                    >
                      <div className="flex items-center justify-between pr-6">
                        <span className="font-mono text-xs text-muted-foreground truncate max-w-[200px]">
                          {s.session_id}
                        </span>
                        <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />
                      </div>
                      {s.preview && (
                        <p className="text-xs text-foreground/70 truncate">{s.preview}</p>
                      )}
                      <div className="flex gap-3 text-[10px] text-muted-foreground/60">
                        <span><MessageSquare size={10} className="inline mr-0.5" />{s.messages} msgs</span>
                        <span>{s.insights} insights</span>
                        <span>{s.charts} charts</span>
                        <span className="ml-auto">
                          {new Date(s.modified * 1000).toLocaleDateString()}
                        </span>
                      </div>
                    </button>
                    <button
                      onClick={(e) => handleDeleteSession(e, s)}
                      title="Delete session"
                      className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/20 text-muted-foreground hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
      {/* Data Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Data Preview</DialogTitle>
          </DialogHeader>
          {previewLoading ? (
            <div className="flex items-center justify-center py-8 gap-2 text-sm text-muted-foreground">
              <Loader2 size={16} className="animate-spin" />
              Loading preview…
            </div>
          ) : previewData ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                {previewData.rows.toLocaleString()} rows · {previewData.columns.length} columns
              </p>
              <div className="overflow-auto max-h-72 rounded-xl border border-border/40">
                <table className="w-full text-xs">
                  <thead className="sticky top-0">
                    <tr className="bg-secondary/80">
                      {previewData.columns.map((col) => (
                        <th
                          key={col}
                          className="px-3 py-2 text-left font-medium whitespace-nowrap text-muted-foreground"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.preview.map((row, i) => (
                      <tr key={i} className="border-t border-border/30 hover:bg-secondary/30">
                        {previewData.columns.map((col) => (
                          <td
                            key={col}
                            className="px-3 py-2 text-foreground/80 whitespace-nowrap"
                          >
                            {String(row[col] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-4">
              Could not load preview. Make sure data is loaded in this session.
            </p>
          )}
        </DialogContent>
      </Dialog>
    </aside>
  );
};

export default AppSidebar;
