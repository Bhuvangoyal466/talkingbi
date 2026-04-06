import { useState, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
  PieChart, Pie, Cell, Sector,
  BarChart, Bar,
  AreaChart, Area,
  ScatterChart, Scatter, ZAxis,
  LabelList,
} from "recharts";
import type { ChartData } from "@/types/api";

// ─── Colour palette ───────────────────────────────────────────────────────────

export const CHART_PALETTE = [
  "#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#f43f5e",
  "#8b5cf6", "#0ea5e9", "#84cc16", "#fb923c", "#ec4899",
];

// ─── Custom dark tooltip ──────────────────────────────────────────────────────

export const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1e1e2e] border border-white/10 rounded-xl px-3 py-2 shadow-2xl text-xs z-50">
      {label && <p className="text-white/50 mb-1.5 font-medium">{label}</p>}
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color || p.fill || CHART_PALETTE[i] }} className="font-semibold">
          {p.name ? `${p.name}: ` : ""}
          {typeof p.value === "number" ? p.value.toLocaleString() : p.value}
        </p>
      ))}
    </div>
  );
};

// ─── Active pie slice ─────────────────────────────────────────────────────────

const ActivePieShape = (props: any) => {
  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill, payload, percent } = props;
  return (
    <g>
      <text x={cx} y={cy - 10} textAnchor="middle" fill="currentColor" fontSize={12} fontWeight="bold">
        {payload.name}
      </text>
      <text x={cx} y={cy + 10} textAnchor="middle" fill="#9ca3af" fontSize={11}>
        {`${(percent * 100).toFixed(1)}%`}
      </text>
      <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius + 7}
        startAngle={startAngle} endAngle={endAngle} fill={fill} />
      <Sector cx={cx} cy={cy} innerRadius={outerRadius + 11} outerRadius={outerRadius + 15}
        startAngle={startAngle} endAngle={endAngle} fill={fill} />
    </g>
  );
};

// ─── InteractiveChart ─────────────────────────────────────────────────────────

interface InteractiveChartProps {
  chartData: ChartData;
  chartType: string;
  /** Height in px — defaults to 300 */
  height?: number;
}

export default function InteractiveChart({ chartData, chartType, height = 300 }: InteractiveChartProps) {
  const [activePieIndex, setActivePieIndex] = useState(0);
  const { values, x_axis_label, y_axis_label } = chartData;

  const hasCategory = values.some((v) => v.category != null);

  const rechartsData = useMemo(() => {
    if (!hasCategory) return values.map((v) => ({ name: String(v.x), value: v.y }));
    const map: Record<string, Record<string, number>> = {};
    for (const v of values) {
      const key = String(v.x);
      if (!map[key]) map[key] = {};
      const cat = v.category ?? "value";
      map[key][cat] = (map[key][cat] || 0) + v.y;
    }
    return Object.entries(map).map(([name, vals]) => ({ name, ...vals }));
  }, [values, hasCategory]);

  const categories = useMemo(() => {
    if (!hasCategory) return [];
    return [...new Set(values.map((v) => v.category ?? "value"))];
  }, [values, hasCategory]);

  const ax = { fontSize: 11, fill: "#6b7280" };
  const grid = "rgba(99,102,241,0.07)";
  const base = { data: rechartsData, margin: { top: 12, right: 20, left: 0, bottom: 12 } };

  // ── Bar / Grouped Bar / Stacked Bar ──────────────────────────────────────
  if (["bar", "grouped_bar", "stacked_bar"].includes(chartType)) {
    const stacked = chartType === "stacked_bar";
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart {...base} barCategoryGap="32%">
          <defs>
            {CHART_PALETTE.map((c, i) => (
              <linearGradient key={i} id={`bg${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c} stopOpacity={0.95} />
                <stop offset="100%" stopColor={c} stopOpacity={0.45} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
          <YAxis tick={ax} axisLine={false} tickLine={false}
            label={{ value: y_axis_label, angle: -90, position: "insideLeft", fontSize: 10, fill: "#6b7280" }} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          {hasCategory
            ? categories.map((cat, i) => (
                <Bar key={cat} dataKey={cat} stackId={stacked ? "a" : undefined}
                  fill={`url(#bg${i % CHART_PALETTE.length})`}
                  radius={stacked ? [0, 0, 0, 0] : [4, 4, 0, 0]} />
              ))
            : (
              <Bar dataKey="value" radius={[5, 5, 0, 0]}>
                {rechartsData.map((_, i) => (
                  <Cell key={i} fill={`url(#bg${i % CHART_PALETTE.length})`} />
                ))}
              </Bar>
            )
          }
          {hasCategory && <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── Horizontal Bar ────────────────────────────────────────────────────────
  if (chartType === "horizontal_bar") {
    const sorted = [...rechartsData].sort((a, b) => (b.value as number) - (a.value as number));
    return (
      <ResponsiveContainer width="100%" height={Math.max(height, sorted.length * 36)}>
        <BarChart data={sorted} layout="vertical"
          margin={{ top: 10, right: 44, left: 10, bottom: 10 }} barCategoryGap="28%">
          <defs>
            <linearGradient id="hbg" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={CHART_PALETTE[0]} stopOpacity={0.9} />
              <stop offset="100%" stopColor={CHART_PALETTE[1]} stopOpacity={0.6} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} horizontal={false} />
          <XAxis type="number" tick={ax} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="name" tick={ax} axisLine={false} tickLine={false} width={110} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Bar dataKey="value" fill="url(#hbg)" radius={[0, 5, 5, 0]}>
            <LabelList dataKey="value" position="right"
              style={{ fontSize: 10, fill: "#9ca3af" }}
              formatter={(v: number) => v.toLocaleString()} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── Line ──────────────────────────────────────────────────────────────────
  if (chartType === "line") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart {...base}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
          <YAxis tick={ax} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          {hasCategory
            ? categories.map((cat, i) => (
                <Line key={cat} type="monotone" dataKey={cat}
                  stroke={CHART_PALETTE[i % CHART_PALETTE.length]} strokeWidth={2.5}
                  dot={{ r: 3, fill: CHART_PALETTE[i % CHART_PALETTE.length], strokeWidth: 0 }}
                  activeDot={{ r: 5, strokeWidth: 0 }} />
              ))
            : <Line type="monotone" dataKey="value" stroke={CHART_PALETTE[0]} strokeWidth={2.5}
                dot={{ r: 3, fill: CHART_PALETTE[0], strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 0 }} />
          }
          {hasCategory && <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  // ── Area ──────────────────────────────────────────────────────────────────
  if (chartType === "area") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart {...base}>
          <defs>
            {CHART_PALETTE.map((c, i) => (
              <linearGradient key={i} id={`ag${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={c} stopOpacity={0.22} />
                <stop offset="95%" stopColor={c} stopOpacity={0.01} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
          <YAxis tick={ax} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} />
          {hasCategory
            ? categories.map((cat, i) => (
                <Area key={cat} type="monotone" dataKey={cat}
                  stroke={CHART_PALETTE[i % CHART_PALETTE.length]} strokeWidth={2.5}
                  fill={`url(#ag${i % CHART_PALETTE.length})`} />
              ))
            : <Area type="monotone" dataKey="value" stroke={CHART_PALETTE[0]} strokeWidth={2.5}
                fill="url(#ag0)" />
          }
          {hasCategory && <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />}
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  // ── Pie / Donut ───────────────────────────────────────────────────────────
  if (chartType === "pie") {
    const agg: Record<string, number> = {};
    for (const v of values) agg[String(v.x)] = (agg[String(v.x)] || 0) + Math.abs(v.y);
    const sorted = Object.entries(agg).sort((a, b) => b[1] - a[1]);
    const MAX = 12;
    const pieData = sorted.length > MAX
      ? [...sorted.slice(0, MAX).map(([name, value]) => ({ name, value })),
         { name: "Other", value: sorted.slice(MAX).reduce((s, [, v]) => s + v, 0) }]
      : sorted.map(([name, value]) => ({ name, value }));

    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={pieData} cx="50%" cy="50%"
            innerRadius={Math.round(height * 0.22)} outerRadius={Math.round(height * 0.35)}
            dataKey="value"
            activeIndex={activePieIndex}
            activeShape={ActivePieShape}
            onMouseEnter={(_, i) => setActivePieIndex(i)}
            paddingAngle={2}
          >
            {pieData.map((_, i) => (
              <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} stroke="transparent" />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }}
            formatter={(v) => <span style={{ color: "#9ca3af" }}>{v}</span>} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // ── Scatter ───────────────────────────────────────────────────────────────
  if (chartType === "scatter") {
    const pts = values.map((v) => ({
      x: typeof v.x === "number" ? v.x : parseFloat(String(v.x)) || 0,
      y: v.y,
    }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 12, right: 20, left: 0, bottom: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis type="number" dataKey="x" tick={ax} axisLine={false} tickLine={false}
            label={{ value: x_axis_label, position: "insideBottom", offset: -6, fontSize: 10, fill: "#6b7280" }} />
          <YAxis type="number" dataKey="y" tick={ax} axisLine={false} tickLine={false}
            label={{ value: y_axis_label, angle: -90, position: "insideLeft", fontSize: 10, fill: "#6b7280" }} />
          <ZAxis range={[45, 45]} />
          <Tooltip content={<ChartTooltip />} cursor={{ strokeDasharray: "3 3", stroke: CHART_PALETTE[0] }} />
          <Scatter data={pts} fill={CHART_PALETTE[0]} fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // ── Histogram ─────────────────────────────────────────────────────────────
  if (chartType === "histogram") {
    const numVals = values.map((v) => v.y).filter((v) => !isNaN(v));
    const bins = Math.min(20, Math.ceil(Math.sqrt(numVals.length)));
    const min = Math.min(...numVals), max = Math.max(...numVals);
    const step = (max - min) / bins || 1;
    const histData = Array.from({ length: bins }, (_, i) => {
      const lo = min + i * step, hi = lo + step;
      return {
        name: lo.toFixed(1),
        count: numVals.filter((v) => v >= lo && (i === bins - 1 ? v <= hi : v < hi)).length,
      };
    });
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={histData} margin={{ top: 12, right: 20, left: 0, bottom: 12 }} barCategoryGap="4%">
          <defs>
            <linearGradient id="hg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_PALETTE[0]} stopOpacity={0.9} />
              <stop offset="100%" stopColor={CHART_PALETTE[0]} stopOpacity={0.4} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
          <YAxis tick={ax} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Bar dataKey="count" fill="url(#hg)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ── Auto fallback ─────────────────────────────────────────────────────────
  const uniqueX = new Set(values.map((v) => v.x)).size;
  if (uniqueX <= 20) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart {...base} barCategoryGap="32%">
          <defs>
            {CHART_PALETTE.map((c, i) => (
              <linearGradient key={i} id={`abg${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c} stopOpacity={0.95} />
                <stop offset="100%" stopColor={c} stopOpacity={0.45} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
          <YAxis tick={ax} axisLine={false} tickLine={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <Bar dataKey="value" radius={[5, 5, 0, 0]}>
            {rechartsData.map((_, i) => (
              <Cell key={i} fill={`url(#abg${i % CHART_PALETTE.length})`} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart {...base}>
        <defs>
          <linearGradient id="afg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={CHART_PALETTE[0]} stopOpacity={0.2} />
            <stop offset="95%" stopColor={CHART_PALETTE[0]} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} />
        <XAxis dataKey="name" tick={ax} axisLine={false} tickLine={false} />
        <YAxis tick={ax} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey="value" stroke={CHART_PALETTE[0]} strokeWidth={2.5}
          fill="url(#afg)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ─── Mini chart thumbnail ─────────────────────────────────────────────────────

export function MiniChart({ chartData, chartType }: { chartData: ChartData; chartType: string }) {
  const { values } = chartData;
  const data = values.slice(0, 20).map((v) => ({ name: String(v.x), value: v.y }));

  if (chartType === "pie") {
    const agg: Record<string, number> = {};
    for (const v of values.slice(0, 8)) agg[String(v.x)] = (agg[String(v.x)] || 0) + Math.abs(v.y);
    const pieData = Object.entries(agg).map(([name, value]) => ({ name, value }));
    return (
      <PieChart width={72} height={52}>
        <Pie data={pieData} cx="50%" cy="50%" outerRadius={22} dataKey="value" paddingAngle={1}>
          {pieData.map((_, i) => <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />)}
        </Pie>
      </PieChart>
    );
  }
  if (["line", "area"].includes(chartType)) {
    return (
      <LineChart width={72} height={52} data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
        <Line type="monotone" dataKey="value" stroke={CHART_PALETTE[0]} strokeWidth={1.5} dot={false} />
      </LineChart>
    );
  }
  return (
    <BarChart width={72} height={52} data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }} barCategoryGap="20%">
      <Bar dataKey="value">
        {data.map((_, i) => <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />)}
      </Bar>
    </BarChart>
  );
}
