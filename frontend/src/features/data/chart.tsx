"use client";

import { BarChart3, Table2 } from "lucide-react";
import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartSpec } from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";

/** Categorical order validated with the dataviz palette checker (light surface). Fixed order, never cycled. */
export const SERIES = ["#2563eb", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const MAX_SERIES = 8;

type Row = Record<string, unknown>;

function toRows(spec: ChartSpec): Row[] {
  if (spec.data) return spec.data;
  const cols = spec.columns ?? [];
  return (spec.rows ?? []).map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
}

function shortLabel(v: unknown): string {
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v)) {
    const d = new Date(v);
    return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
  }
  return typeof v === "number" ? formatNumber(v) : String(v ?? "");
}

/** Pivot long (x, series, value) rows into wide rows; extra series beyond the palette fold into "Other". */
function pivot(rows: Row[], x: string, series: string, y: string): { data: Row[]; keys: string[] } {
  const totals = new Map<string, number>();
  for (const r of rows) totals.set(String(r[series]), (totals.get(String(r[series])) ?? 0) + Number(r[y] ?? 0));
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
  const keep = new Set(ranked.length > MAX_SERIES ? ranked.slice(0, MAX_SERIES - 1) : ranked);
  // Keys stay in first-seen order so an entity keeps its color across filters.
  const keys: string[] = [];
  const byX = new Map<string, Row>();
  for (const r of rows) {
    const k = keep.has(String(r[series])) ? String(r[series]) : "Other";
    if (!keys.includes(k)) keys.push(k);
    const xv = String(r[x]);
    const row = byX.get(xv) ?? { [x]: r[x] };
    row[k] = Number(row[k] ?? 0) + Number(r[y] ?? 0);
    byX.set(xv, row);
  }
  return { data: [...byX.values()], keys };
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: unknown }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[12px] shadow-pop">
      <div className="mb-1 font-medium text-ink">{shortLabel(label)}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 text-ink-2">
          <span className="size-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums text-ink">{formatNumber(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

const axis = { tick: { fill: "#64748b", fontSize: 11 }, axisLine: false, tickLine: false } as const;

export function ChartView({ spec, height = 260, className }: { spec: ChartSpec; height?: number; className?: string }) {
  const [view, setView] = React.useState<"chart" | "table">("chart");
  const rows = React.useMemo(() => toRows(spec), [spec]);
  const yKey = spec.y[0];
  const { data, keys } = React.useMemo(
    () => (spec.series ? pivot(rows, spec.x, spec.series, yKey) : { data: rows, keys: spec.y }),
    [rows, spec, yKey],
  );
  const multi = keys.length > 1;

  const chart = (() => {
    if (spec.type === "scatter") {
      return (
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#eef2f7" />
          <XAxis dataKey={spec.x} name={spec.x} type="number" {...axis} tickFormatter={formatNumber} />
          <YAxis dataKey={yKey} name={yKey} type="number" {...axis} tickFormatter={formatNumber} width={48} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v) => formatNumber(v)} />
          <Scatter data={rows} fill={SERIES[0]} fillOpacity={0.7} stroke="#fff" strokeWidth={1} />
        </ScatterChart>
      );
    }
    if (spec.type === "line" || spec.type === "area") {
      const C = spec.type === "area" ? AreaChart : LineChart;
      return (
        <C data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#eef2f7" vertical={false} />
          <XAxis dataKey={spec.x} {...axis} tickFormatter={shortLabel} minTickGap={24} />
          <YAxis {...axis} tickFormatter={formatNumber} width={52} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#cbd5e1" }} />
          {multi && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#334155" }} />}
          {keys.map((k, i) =>
            spec.type === "area" ? (
              <Area key={k} dataKey={k} type="monotone" stroke={SERIES[i]} fill={SERIES[i]} fillOpacity={0.12} strokeWidth={2} />
            ) : (
              <Line
                key={k}
                dataKey={k}
                type="monotone"
                stroke={SERIES[i]}
                strokeWidth={2}
                dot={spec.highlight ? (p: { cx?: number; cy?: number; payload?: Row; index?: number }) =>
                  p.payload?.[spec.highlight!] ? (
                    <circle key={p.index} cx={p.cx} cy={p.cy} r={5} fill="#ef4444" stroke="#fff" strokeWidth={2} />
                  ) : <g key={p.index} />
                  : false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }}
              />
            ),
          )}
        </C>
      );
    }
    const horizontal = !!spec.horizontal;
    return (
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, bottom: 4, left: horizontal ? 8 : 0 }} barCategoryGap="22%">
        <CartesianGrid stroke="#eef2f7" vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...axis} tickFormatter={formatNumber} />
            <YAxis type="category" dataKey={spec.x} {...axis} width={110} tickFormatter={(v) => String(v).slice(0, 16)} />
          </>
        ) : (
          <>
            <XAxis dataKey={spec.x} {...axis} tickFormatter={shortLabel} minTickGap={8} />
            <YAxis {...axis} tickFormatter={formatNumber} width={52} />
          </>
        )}
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgb(37 99 235 / 0.05)" }} />
        {multi && <Legend iconType="square" wrapperStyle={{ fontSize: 12, color: "#334155" }} />}
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={SERIES[i]} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} stackId={spec.series ? "s" : undefined} stroke="#fff" strokeWidth={spec.series ? 1 : 0} maxBarSize={44}>
            {!multi && spec.type === "pie" && data.map((_, j) => <Cell key={j} fill={SERIES[j % SERIES.length]} />)}
          </Bar>
        ))}
      </BarChart>
    );
  })();

  return (
    <div className={cn("rounded-xl border border-line bg-surface", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-line px-3.5 py-2">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-medium text-ink">
            {spec.label && <span className="mr-1.5 rounded bg-[#f5f3ff] px-1 font-mono text-[10.5px] text-violet">{spec.label}</span>}
            {spec.title}
          </div>
          {spec.note && <div className="text-[11.5px] text-muted">{spec.note}</div>}
        </div>
        <div className="flex shrink-0 rounded-lg border border-line p-0.5" role="group" aria-label="Chart view">
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              aria-label={v === "chart" ? "Show chart" : "Show table"}
              className={cn("rounded-md p-1 text-muted transition", view === v && "bg-primary-soft text-primary")}
            >
              {v === "chart" ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
            </button>
          ))}
        </div>
      </div>
      {view === "chart" ? (
        <div className="p-2" style={{ height }} data-testid="chart">
          <ResponsiveContainer width="100%" height="100%">
            {chart}
          </ResponsiveContainer>
        </div>
      ) : (
        <DataTable columns={spec.columns ?? Object.keys(rows[0] ?? {})} rows={spec.rows ?? rows.map((r) => Object.values(r))} maxHeight={height} />
      )}
    </div>
  );
}

export function DataTable({ columns, rows, maxHeight = 320, className }: { columns: string[]; rows: unknown[][]; maxHeight?: number; className?: string }) {
  return (
    <div className={cn("nx-scroll overflow-auto", className)} style={{ maxHeight }}>
      <table className="w-full border-separate border-spacing-0 text-[12.5px]">
        <thead className="sticky top-0 z-10">
          <tr>
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap border-b border-line bg-surface-2 px-3 py-2 text-left font-medium text-ink">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-bg-subtle/60">
              {r.map((v, j) => (
                <td key={j} className={cn("whitespace-nowrap border-b border-line/70 px-3 py-1.5 text-ink-2", typeof v === "number" && "text-right tabular-nums")}>
                  {v === null ? <span className="text-faint">null</span> : typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="py-8 text-center text-[12.5px] text-muted">No rows</div>}
    </div>
  );
}
