import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { KpiCoverageInfo } from "@/types/api";

interface KpiCoverageCardProps {
  coverage: KpiCoverageInfo;
}

function formatPercent(value: number) {
  return `${Math.round(value)}%`;
}

function CoverageList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.length > 0 ? (
          items.map((item) => (
            <Badge key={item} variant="outline" className={`border ${tone} text-[11px] font-medium`}>
              {item}
            </Badge>
          ))
        ) : (
          <span className="text-xs text-muted-foreground">None</span>
        )}
      </div>
    </div>
  );
}

export default function KpiCoverageCard({ coverage }: KpiCoverageCardProps) {
  const percent = coverage.coverage_percent || 0;
  const statusClass =
    coverage.status === "complete"
      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
      : coverage.status === "partial"
        ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
        : "bg-secondary text-muted-foreground border-border/40";

  return (
    <Card className="border-border/40 bg-secondary/20 shadow-none">
      <CardHeader className="p-4 pb-3 space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-sm font-semibold">KPI Coverage</CardTitle>
          <Badge variant="outline" className={statusClass}>
            {coverage.status.replace(/_/g, " ")}
          </Badge>
        </div>
        <CardDescription className="text-xs leading-relaxed">
          {coverage.summary || `Coverage of ${coverage.coverage_total} KPI${coverage.coverage_total === 1 ? "" : "s"}.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-4 pt-0 space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="rounded-xl bg-background/60 border border-border/30 p-3">
            <p className="text-[11px] text-muted-foreground">Covered</p>
            <p className="text-lg font-semibold text-foreground">{coverage.coverage_count}</p>
          </div>
          <div className="rounded-xl bg-background/60 border border-border/30 p-3">
            <p className="text-[11px] text-muted-foreground">Total</p>
            <p className="text-lg font-semibold text-foreground">{coverage.coverage_total}</p>
          </div>
          <div className="rounded-xl bg-background/60 border border-border/30 p-3">
            <p className="text-[11px] text-muted-foreground">Coverage</p>
            <p className="text-lg font-semibold text-foreground">{formatPercent(percent)}</p>
          </div>
          <div className="rounded-xl bg-background/60 border border-border/30 p-3">
            <p className="text-[11px] text-muted-foreground">Basis</p>
            <p className="text-lg font-semibold text-foreground capitalize">{coverage.coverage_basis}</p>
          </div>
        </div>

        <div className="space-y-3">
          <CoverageList
            title="Requested KPIs"
            items={coverage.requested_kpis}
            tone="border-primary/30 bg-primary/5 text-primary"
          />
          <CoverageList
            title="Available KPIs"
            items={coverage.available_kpis}
            tone="border-border/40 bg-secondary/30 text-foreground"
          />
          <CoverageList
            title="Covered KPIs"
            items={coverage.covered_kpis}
            tone="border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
          />
          <CoverageList
            title="Missing KPIs"
            items={coverage.missing_kpis}
            tone="border-amber-500/30 bg-amber-500/5 text-amber-300"
          />
        </div>
      </CardContent>
    </Card>
  );
}