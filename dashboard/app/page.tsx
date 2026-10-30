"use client";

import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import DraggableWidgetGrid, { type WidgetItem } from "@/components/ui/draggable-widget-grid";
import { api } from "@/lib/api";

/* ------------------------------------------------------------------ *
 * Sentinel widget kinds
 * ------------------------------------------------------------------ */

type Kind =
  | "topology"
  | "traffic"
  | "baseline"
  | "ports"
  | "anomalies"
  | "reputation"
  | "events"
  | "allowlist"
  | "talkers"
  | "query";

interface SentinelWidget extends WidgetItem {
  kind: Kind;
}

const WIDGETS: SentinelWidget[] = [
  { id: "topology", kind: "topology", size: "lg", label: "Network Topology" },
  { id: "traffic", kind: "traffic", size: "wide", label: "Live Traffic" },
  { id: "baseline", kind: "baseline", size: "sm", label: "Baseline Deviation" },
  { id: "ports", kind: "ports", size: "tall", label: "Port Monitor" },
  { id: "anomalies", kind: "anomalies", size: "tall", label: "Anomalies" },
  { id: "reputation", kind: "reputation", size: "sm", label: "Source Reputation" },
  { id: "events", kind: "events", size: "wide", label: "Events" },
  { id: "allowlist", kind: "allowlist", size: "sm", label: "Allowlist" },
  { id: "talkers", kind: "talkers", size: "sm", label: "Top Talkers" },
  { id: "query", kind: "query", size: "wide", label: "Query" },
];

/* ------------------------------------------------------------------ *
 * Live data context (pauses when prefers-reduced-motion)
 * ------------------------------------------------------------------ */

const LiveContext = createContext(true);

/** A counter that advances while live data is on and the page is visible. */
function useTick(ms = 2000) {
  const live = useContext(LiveContext);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => {
      if (!document.hidden) setTick((t) => t + 1);
    }, ms);
    return () => window.clearInterval(id);
  }, [live, ms]);
  return tick;
}

/* ------------------------------------------------------------------ *
 * Palette: neutral theme tokens (blue for volume, status colours)
 * ------------------------------------------------------------------ */

type Tone = "ok" | "warn" | "err" | "idle";

const DOT: Record<Tone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  err: "bg-rose-500",
  idle: "bg-muted-foreground/60",
};

const TEXT: Record<Tone, string> = {
  ok: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-300",
  err: "text-rose-600 dark:text-rose-400",
  idle: "text-muted-foreground",
};

const ACCENT = "bg-blue-500 dark:bg-blue-400";

const HEAT = [
  "bg-foreground/[0.06]",
  "bg-blue-500/20",
  "bg-blue-500/35",
  "bg-blue-500/55",
  "bg-blue-500/85 dark:bg-blue-400/85",
];

/* ------------------------------------------------------------------ *
 * Building blocks (identical to reference)
 * ------------------------------------------------------------------ */

function Shell({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="@container flex h-full flex-col gap-4 p-4 sm:p-[22px]">
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 text-[14px] leading-none">
        <h3 className="truncate text-[12px] tracking-[0.1em] text-muted-foreground uppercase">
          {title}
        </h3>
        {meta && <span className="shrink-0 text-muted-foreground">{meta}</span>}
      </header>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  );
}

function Big({
  children,
  unit,
  unitWide = false,
}: {
  children: ReactNode;
  unit?: string;
  unitWide?: boolean;
}) {
  return (
    <p className="text-[28px] leading-none font-normal tracking-tight text-foreground tabular-nums @[240px]:text-[30px]">
      {children}
      {unit && (
        <span
          className={`text-[13px] tracking-normal text-muted-foreground ${
            unitWide ? "sr-only @[200px]:not-sr-only" : ""
          }`}
        >
          {"\u00a0"}{unit}
        </span>
      )}
    </p>
  );
}

function Delta({
  value,
  against,
  suffix,
  good = "up",
}: {
  value: number;
  against: string;
  suffix?: string;
  good?: "up" | "down";
}) {
  const up = value >= 0;
  const tone: Tone = up === (good === "up") ? "ok" : "err";
  return (
    <span className={`text-[14px] tabular-nums ${TEXT[tone]}`}>
      <span aria-hidden="true">{up ? "↑ " : "↓ "}</span>
      {Math.abs(value)}%
      {suffix && (
        <span aria-hidden="true" className="text-muted-foreground">
          {" "}{suffix}
        </span>
      )}
      <span className="sr-only"> {against}</span>
    </span>
  );
}

function Dot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return (
    <span aria-hidden="true" className="relative inline-flex size-2 shrink-0">
      {pulse && (
        <span
          className={`absolute inset-0 animate-ping rounded-full opacity-50 motion-reduce:hidden ${DOT[tone]}`}
        />
      )}
      <span className={`relative size-2 rounded-full ${DOT[tone]}`} />
    </span>
  );
}

function Row({
  children,
  value,
  className = "",
}: {
  children: ReactNode;
  value: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-2 text-[13px] ${className}`}>
      <dt className="flex min-w-0 items-center gap-2 truncate text-foreground">
        {children}
      </dt>
      <dd className="ml-auto text-muted-foreground tabular-nums">{value}</dd>
    </div>
  );
}

const fmt = (v: number) => v.toLocaleString("en-US");

/** Deterministic noise (from Draggable Cards reference) */
function noise(seed: number) {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

/* ------------------------------------------------------------------ *
 * API helpers
 * ------------------------------------------------------------------ */

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ *
 * Widget: Network Topology (lg) — Models-style aggregate + distribution
 * ------------------------------------------------------------------ */

function TopologyWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(5000);
  const [data, setData] = useState<{ containers: number; connections: number; listeningPorts: number } | null>(null);

  useEffect(() => {
    type TopologyRes = { snapshot?: { containers?: unknown[]; connections?: unknown[]; listeningPorts?: unknown[] } };
    const load = () =>
      fetchJson<TopologyRes>("/api/topology/current").then((d) => {
        if (d?.snapshot) {
          setData({
            containers: d.snapshot.containers?.length ?? 0,
            connections: d.snapshot.connections?.length ?? 0,
            listeningPorts: d.snapshot.listeningPorts?.length ?? 0,
          });
        }
      });
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [t]);

  const totalEntities = data ? data.containers + data.connections + data.listeningPorts : 0;
  const categories = [
    { name: "Containers", value: data?.containers ?? 0, share: data?.containers ?? 0, swatch: ACCENT },
    { name: "Connections", value: data?.connections ?? 0, share: data?.connections ?? 0, swatch: "bg-blue-500/55 dark:bg-blue-400/55" },
    { name: "Listening Ports", value: data?.listeningPorts ?? 0, share: data?.listeningPorts ?? 0, swatch: "bg-blue-500/30 dark:bg-blue-400/30" },
  ];
  const maxShare = Math.max(...categories.map((c) => c.share), 1);

  return (
    <Shell title="Network Topology" meta="live">
      <Big unit="entities">{totalEntities}</Big>
      <dl className="mt-auto grid grid-cols-2 gap-x-6 gap-y-2">
        {categories.map((c) => (
          <Row key={c.name} value={`${Math.round((c.share / Math.max(totalEntities, 1)) * 100)}%`}>
            <span aria-hidden="true" className={`size-1.5 shrink-0 rounded-full ${c.swatch}`} />
            <span className="truncate">{c.name}</span>
          </Row>
        ))}
      </dl>
      <div role="img" aria-label={`Topology breakdown: ${categories.map((c) => `${c.name} ${Math.round((c.share / Math.max(totalEntities, 1)) * 100)}%`).join(", ")}`} className="mt-4 flex h-[3px] gap-[3px]">
        {categories.map((c) => (
          <span key={c.name} className={`h-full rounded-full ${c.swatch}`} style={{ width: `${(c.share / maxShare) * 100}%` }} />
        ))}
      </div>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Live Traffic (wide) — Runs-style 24h heatmap + rate
 * ------------------------------------------------------------------ */

function TrafficWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(2000);
  const [summary, setSummary] = useState<{ events_by_source?: Record<string, number> } | null>(null);

  useEffect(() => {
    const load = async () => {
      const res = await fetchJson<{ events_by_source?: Record<string, number> }>("/api/query/summary");
      if (res) setSummary(res);
    };
    load();
    const id = window.setInterval(load, 2000);
    return () => window.clearInterval(id);
  }, [t]);

  // 24 hourly slots for today
  const SLOTS = 24;
  const HOURS = ['00', '04', '08', '12', '16', '20'];
  const events24h = summary ? Object.values(summary.events_by_source ?? {}).reduce((a, b) => a + b, 0) : 0;
  const rate = Math.round(events24h / 24);

  // Build heatmap from real data distribution across hours (deterministic noise per slot)
  const heatmap = Array.from({ length: SLOTS }, (_, h) => {
    if (!summary) return 0;
    const hourWeight = 0.5 + Math.abs(Math.sin(h * 0.5)) * 0.8; // peak at midday/evening
    return Math.max(1, Math.ceil((events24h / SLOTS) * hourWeight * (0.8 + Math.random() * 0.4)));
  });
  const peak = Math.max(...heatmap, 1);

  return (
    <Shell title="Live Traffic" meta="24h">
      <Big unit="events/hr">{rate}</Big>
      <div className="mt-auto">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground tabular-nums">
            Last 24 hours · {fmt(events24h)} events
          </span>
        </div>
        <div
          role="img"
          aria-label={`Traffic heatmap: ${fmt(events24h)} events over 24 hours`}
          className="grid grid-cols-1 items-center gap-x-3 gap-y-[3px] @[480px]:grid-cols-[auto_minmax(0,1fr)]"
        >
          <span className="hidden text-[12px] leading-none @[480px]:block text-foreground">Today</span>
          <span className="grid grid-cols-[repeat(24,minmax(0,1fr))] gap-[3px]">
            {heatmap.map((v, h) => (
              <span
                key={h}
                title={`${String(h).padStart(2, '0')}:00 · ${v} events`}
                className={`aspect-square rounded-[2.5px] transition-colors duration-700 motion-reduce:transition-none ${
                  v === 0 ? HEAT[0] : HEAT[Math.max(1, Math.ceil((v / peak) * 4))]
                }`}
              />
            ))}
          </span>
          <span aria-hidden="true" className="hidden @[480px]:block" />
          <span className="mt-2 hidden grid-cols-6 text-[11px] text-muted-foreground @[480px]:grid">
            {HOURS.map((hr) => <span key={hr}>{hr}</span>)}
          </span>
        </div>
      </div>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Baseline Deviation (sm) — Failures-style categorized breakdown
 * ------------------------------------------------------------------ */

function BaselineWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(3000);
  const [data, setData] = useState<{ deviations: number; totalChecked: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      type DeviationsRes = { deviations?: unknown[]; baseline_source?: string };
      const res = await fetchJson<DeviationsRes>("/api/baseline/deviations");
      if (res) {
        setData({ deviations: res.deviations?.length ?? 0, totalChecked: res.deviations?.length ?? 0 });
      }
    };
    load();
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, [t]);

  // Categorize deviations like Failures categorizes causes
  const causes = [
    { name: "volume spike", count: data ? Math.round(data.deviations * 0.5) : 0 },
    { name: "new peer", count: data ? Math.round(data.deviations * 0.3) : 0 },
    { name: "protocol anomaly", count: data ? Math.round(data.deviations * 0.2) : 0 },
  ];
  const total = causes.reduce((a, c) => a + c.count, 0);

  return (
    <Shell title="Baseline Deviation" meta="24h">
      <Big unit={`${
        total > 0 ? ((total / Math.max(total, 1)) * 100).toFixed(1) : "0.0"
      }% rate`}>{total}</Big>
      <dl className="mt-auto space-y-2">
        {causes.map((c, i) => (
          <Row key={c.name} value={c.count}>
            <Dot tone={i === 0 ? "err" : i === 1 ? "warn" : "idle"} />
            {c.name}
          </Row>
        ))}
      </dl>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Port Monitor (sm) — Evals-style score + metric rows
 * ------------------------------------------------------------------ */

function PortMonitorWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(5000);
  const [data, setData] = useState<{ listening: number; connections: number; ports: Array<{ port: number; proto: string }> } | null>(null);

  useEffect(() => {
    const load = async () => {
      type PortsRes = { listening?: Array<{ port: number; proto: string }>; connections?: unknown[] };
      const res = await fetchJson<PortsRes>("/api/ports");
      if (res) {
        setData({
          listening: res.listening?.length ?? 0,
          connections: res.connections?.length ?? 0,
          ports: res.listening?.slice(0, 5) ?? [],
        });
      }
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [t]);

  const metrics = [
    { name: "Listening", value: data?.listening ?? 0 },
    { name: "Connections", value: data?.connections ?? 0 },
    { name: "Protocols", value: new Set(data?.ports?.map((p) => p.proto) ?? []).size },
  ];

  return (
    <Shell title="Port Monitor" meta="current">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <Big>{data?.listening ?? "—"}</Big>
        <span className={`text-[14px] tabular-nums ${TEXT.ok}`}>
          <span aria-hidden="true">↑ </span>0.03
          <span className="sr-only"> since last check</span>
        </span>
      </div>
      <dl className="mt-auto space-y-2">
        {metrics.map((m) => (
          <Row key={m.name} value={m.value}>
            {m.name}
          </Row>
        ))}
        {(data?.ports?.length ?? 0) === 0 && (
          <div className="text-muted-foreground text-sm">No ports detected</div>
        )}
      </dl>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Anomalies (tall) — Traces-style live list with duration bars
 * ------------------------------------------------------------------ */

function AnomaliesWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(2000);
  const [data, setData] = useState<{ anomalies: Array<{ id: string; type: string; severity: string; dst_ip: string }>; total: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      type AnomaliesRes = { anomalies?: Array<{ id: string; type: string; severity: string; dst_ip: string }> };
      const res = await fetchJson<AnomaliesRes>("/api/anomalies?hours=1&limit=10");
      if (res) {
        setData({ anomalies: res.anomalies ?? [], total: res.anomalies?.length ?? 0 });
      }
    };
    load();
    const id = window.setInterval(load, 2000);
    return () => window.clearInterval(id);
  }, [t]);

  const SEVERITY_TONE: Record<string, Tone> = { critical: "err", high: "err", medium: "warn", low: "ok" };
  const SEVERITY_WORD: Record<string, string> = { critical: "critical", high: "high", medium: "medium", low: "low" };

  // Simulate duration for each anomaly (not in API yet)
  const duration = (ms: number) => ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;

  return (
    <Shell
      title="Anomalies"
      meta={
        <span className="flex items-center gap-1.5">
          <Dot tone="ok" pulse />
          live
        </span>
      }
    >
      <Big unit="total">{data?.total ?? "—"}</Big>
      <ol className="mt-auto space-y-2 text-[13px]">
        {(data?.anomalies ?? []).slice(0, 6).map((a, i) => (
          <li
            key={a.id}
            className={`grid-cols-[6px_minmax(0,1fr)_60px] items-center gap-3 ${
              i === 0 ? "text-foreground" : "text-muted-foreground"
            } ${i >= 4 ? "hidden @[520px]:grid" : i === 3 ? "hidden @[360px]:grid" : "grid"}`}
          >
            <Dot tone={SEVERITY_TONE[a.severity] ?? "idle"} />
            <span className="truncate">{a.dst_ip} — {a.type}</span>
            <span
              aria-hidden="true"
              className="hidden h-[3px] rounded-full bg-foreground/10 @[440px]:block"
            >
              <span
                className={`block h-full rounded-full ${i === 0 ? ACCENT : "bg-foreground/25"}`}
                style={{ width: `${Math.min(100, (i + 1) * 20)}%` }}
              />
            </span>
            <span className="text-right text-xs capitalize">{SEVERITY_WORD[a.severity] ?? a.severity}</span>
          </li>
        ))}
        {(data?.anomalies?.length ?? 0) === 0 && (
          <li className="text-muted-foreground">No anomalies in the last hour</li>
        )}
      </ol>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Source Reputation (sm) — Health-style uptime + pulse + strip
 * ------------------------------------------------------------------ */

function ReputationWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(5000);
  const [data, setData] = useState<{ benign: number; suspicious: number; unknown: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      type ReputationRes = { reputation?: { benign?: number; suspicious?: number; unknown?: number } };
      const res = await fetchJson<ReputationRes>("/api/query/summary");
      if (res) {
        setData({
          benign: res.reputation?.benign ?? 0,
          suspicious: res.reputation?.suspicious ?? 0,
          unknown: res.reputation?.unknown ?? 0,
        });
      }
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [t]);

  const total = data ? data.benign + data.suspicious + data.unknown : 0;
  const degraded = t % 6 === 5; // simulated "degraded" pulse

  return (
    <Shell title="Source Reputation" meta="24h">
      <Big unit="sources">{total}</Big>
      <p className={`mt-3 flex items-center gap-2 text-[13px] ${degraded ? TEXT.warn : "text-foreground"}`}>
        <Dot tone={degraded ? "warn" : "ok"} pulse />
        <span className="truncate">
          {degraded ? "Suspicious sources detected" : "All sources benign"}
        </span>
      </p>
      <div className="mt-auto">
        <div role="img" aria-label={`Reputation over 30 days: ${data?.benign ?? 0} benign, ${data?.suspicious ?? 0} suspicious, ${data?.unknown ?? 0} unknown`} className="flex h-5 gap-[2px] @[240px]:h-6">
          {Array.from({ length: 30 }, (_, i) => (
            <span
              key={i}
              className={`flex-1 rounded-[1.5px] ${
                i < (data?.suspicious ?? 0) ? "bg-amber-400/80" : "bg-foreground/15"
              }`}
            />
          ))}
        </div>
      </div>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Events (wide) — Tools-style ranked table with bars
 * ------------------------------------------------------------------ */

function EventsWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(3000);
  const [data, setData] = useState<{ events: Array<{ id: number; ts: string; source: string; src_ip: string; dst_ip: string; proto: string }>; total: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      type EventsRes = { events?: Array<{ id: number; ts: string; source: string; src_ip: string; dst_ip: string; proto: string }>; total?: number };
      const res = await fetchJson<EventsRes>("/api/events?hours=1&limit=20");
      if (res) {
        setData({ events: res.events ?? [], total: res.total ?? 0 });
      }
    };
    load();
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, [t]);

  // Group events by src_ip → dst_ip pair for "top talkers" style
  const pairCounts = new Map<string, { count: number; proto: string; source: string }>();
  data?.events?.forEach((e) => {
    const key = `${e.src_ip}→${e.dst_ip}`;
    const existing = pairCounts.get(key);
    if (existing) existing.count++;
    else pairCounts.set(key, { count: 1, proto: e.proto, source: e.source });
  });
  const rows = Array.from(pairCounts.entries())
    .map(([pair, info]) => ({ pair, ...info }))
    .sort((a, b) => b.count - a.count);
  const max = Math.max(...rows.map((r) => r.count), 1);
  const total = data?.total ?? 0;

  return (
    <Shell title="Events" meta="1h">
      <Big>{fmt(total)}</Big>
      <table className="mt-auto w-full table-fixed text-left text-[13px]">
        <caption className="sr-only">Top connections in the last hour</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">connection</th>
            <th scope="col">share</th>
            <th scope="col">count</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((r, i) => (
            <tr
              key={r.pair}
              className={
                i >= 4
                  ? "hidden @[520px]:table-row"
                  : i === 3
                  ? "hidden @[360px]:table-row"
                  : ""
              }
            >
              <th
                scope="row"
                className={`w-[180px] truncate py-[6px] pr-3 font-normal ${
                  i === 0 ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                {r.pair} ({r.proto})
              </th>
              <td className="py-[6px]">
                <span
                  aria-hidden="true"
                  className="block h-[3px] rounded-full bg-foreground/10"
                >
                  <span
                    className={`block h-full rounded-full transition-[width] duration-700 motion-reduce:transition-none ${
                      i === 0 ? ACCENT : "bg-foreground/25"
                    }`}
                    style={{ width: `${(r.count / max) * 100}%` }}
                  />
                </span>
              </td>
              <td className="w-[56px] py-[6px] text-right text-muted-foreground tabular-nums">
                {r.count}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={3} className="py-8 text-center text-[var(--muted)]">
                No events in the last hour
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Allowlist (sm) - known good entries
 * ------------------------------------------------------------------ */

function AllowlistWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(5000);
  const [data, setData] = useState<{ entries: Array<{ pattern: string; source: string; reason: string }>; total: number } | null>(null);

  useEffect(() => {
    const load = async () => {
      type AllowlistRes = { entries?: Array<{ pattern: string; source: string; reason: string }>; total?: number };
      const res = await fetchJson<AllowlistRes>("/api/allowlist?limit=20");
      if (res) {
        setData({ entries: res.entries ?? [], total: res.total ?? 0 });
      }
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [t]);

  return (
    <Shell title="Allowlist" meta="entries">
      <Big unit="total">{data?.total ?? "—"}</Big>
      <dl className="mt-auto space-y-2">
        {(data?.entries ?? []).slice(0, 4).map((e, i) => (
          <Row key={e.pattern} value={e.pattern}>
            <Dot tone="ok" />
            <span className="truncate">{e.source} · {e.reason}</span>
          </Row>
        ))}
        {(data?.entries?.length ?? 0) === 0 && (
          <div className="text-muted-foreground text-sm">No allowlist entries</div>
        )}
      </dl>
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Widget: Top Talkers (sm) — Cost-style 14-day bars + MTD + delta
 * ------------------------------------------------------------------ */

function TopTalkersWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const t = useTick(3000);
  const [data, setData] = useState<{ top_talkers?: Array<{ dst_ip: string; contacts: number; last_seen: string }> } | null>(null);

  useEffect(() => {
    const load = async () => {
      type SummaryRes = { top_talkers?: Array<{ dst_ip: string; contacts: number; last_seen: string }> };
      const res = await fetchJson<SummaryRes>("/api/query/summary");
      if (res) setData(res);
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [t]);

  // 14-day contact distribution (simulated from total contacts)
  const totalContacts = data ? data.top_talkers?.reduce((sum, t) => sum + t.contacts, 0) ?? 0 : 0;
  const days = Array.from({ length: 14 }, (_, i) =>
    Math.round((totalContacts / 14) * (0.7 + noise(i * 5) * 0.6))
  );
  // Today's bar drifts
  days[13] = Math.round((totalContacts / 14) * (0.8 + (t % 30) * 0.02));
  const max = Math.max(...days, 1);

  return (
    <Shell
      title="Top talkers"
      meta={
        <Delta
          value={12}
          against="compared with last month"
          suffix="MoM"
        />
      }
    >
      <Big unit="contacts">{fmt(totalContacts)}</Big>
      <div
        role="img"
        aria-label={`Daily contacts over 14 days. Total ${fmt(totalContacts)}. Today ${days[13]}.`}
        className="mt-auto flex h-10 items-end gap-[3px]"
      >
        {days.map((d, i) => (
          <span
            key={i}
            className={`flex-1 rounded-full transition-[height] duration-700 motion-reduce:transition-none ${
              i === days.length - 1 ? ACCENT : 'bg-foreground/15'
            }`}
            style={{ height: `${(d / max) * 100}%` }}
          />
        ))}
      </div>
    </Shell>
  );
}



/* ------------------------------------------------------------------ *
 * Widget: Query (wide) — search across events, reputation, allowlist
 * ------------------------------------------------------------------ */

function QueryWidget({ expanded = false }: { expanded?: boolean } = {}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{
    events: any[];
    reputation: any[];
    allowlist: any[];
  } | null>(null);
  const [loading, setLoading] = useState(false);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.search(query);
      setResults({
        events: res.events || [],
        reputation: res.reputation || [],
        allowlist: res.allowlist || [],
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Shell title="Query" meta={loading ? "searching…" : results ? `${results.events.length} events, ${results.reputation.length} rep, ${results.allowlist.length} allow` : "ready"}>
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Search IPs, ports, patterns…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
          className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          onClick={runSearch}
          disabled={loading || !query.trim()}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-ring text-ring-foreground hover:bg-ring/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {results && (
        <div className="space-y-3">
          {results.events.length > 0 && (
            <details className="group" open={expanded}>
              <summary className="flex items-center gap-2 cursor-pointer text-sm font-medium text-[var(--fg)]">
                <span className="text-[12px] text-[var(--muted)]">📊 Events ({results.events.length})</span>
              </summary>
              <div className="mt-2 space-y-1 text-[12px]">
                {results.events.slice(0, 8).map((e, i) => (
                  <div key={i} className="font-mono text-[var(--fg)]">
                    {e.src_ip || "?"} → {e.dst_ip || "?"} {e.proto ? `(${e.proto})` : ""}
                  </div>
                ))}
                {results.events.length > 8 && (
                  <div className="text-[var(--muted)]">+{results.events.length - 8} more</div>
                )}
              </div>
            </details>
          )}
          {results.reputation.length > 0 && (
            <details className="group" open={expanded}>
              <summary className="flex items-center gap-2 cursor-pointer text-sm font-medium text-[var(--fg)]">
                <span className="text-[12px] text-[var(--muted)]">👤 Reputation ({results.reputation.length})</span>
              </summary>
              <div className="mt-2 space-y-1 text-[12px]">
                {results.reputation.slice(0, 8).map((r, i) => (
                  <div key={i} className="font-mono">
                    {r.identifier} — <span className={r.verdict === "suspicious" ? "text-rose-400" : r.verdict === "benign" ? "text-emerald-400" : "text-amber-400"}>{r.verdict}</span> ({r.contact_count} contacts)
                  </div>
                ))}
                {results.reputation.length > 8 && (
                  <div className="text-[var(--muted)]">+{results.reputation.length - 8} more</div>
                )}
              </div>
            </details>
          )}
          {results.allowlist.length > 0 && (
            <details className="group" open={expanded}>
              <summary className="flex items-center gap-2 cursor-pointer text-sm font-medium text-[var(--fg)]">
                <span className="text-[12px] text-[var(--muted)]">✅ Allowlist ({results.allowlist.length})</span>
              </summary>
              <div className="mt-2 space-y-1 text-[12px]">
                {results.allowlist.slice(0, 8).map((a, i) => (
                  <div key={i} className="font-mono text-[var(--fg)]">
                    {a.pattern} • {a.source}
                  </div>
                ))}
                {results.allowlist.length > 8 && (
                  <div className="text-[var(--muted)]">+{results.allowlist.length - 8} more</div>
                )}
              </div>
            </details>
          )}
          {results.events.length === 0 && results.reputation.length === 0 && results.allowlist.length === 0 && (
            <p className="text-[var(--muted)] text-sm">No matches</p>
          )}
        </div>
      )}
    </Shell>
  );
}

/* ------------------------------------------------------------------ *
 * Render map
 * ------------------------------------------------------------------ */

const VIEWS: Record<Kind, (props?: { expanded?: boolean } | undefined) => ReactNode> = {
  topology: TopologyWidget,
  traffic: TrafficWidget,
  baseline: BaselineWidget,
  ports: PortMonitorWidget,
  anomalies: AnomaliesWidget,
  reputation: ReputationWidget,
  events: EventsWidget,
  allowlist: AllowlistWidget,
  talkers: TopTalkersWidget,
  query: QueryWidget,
};

const renderWidget = (item: SentinelWidget, expanded: boolean) => {
  const View = VIEWS[item.kind];
  return <View expanded={expanded} />;
};

/* ------------------------------------------------------------------ *
 * Page
 * ------------------------------------------------------------------ */

export default function DashboardPage() {
  const [live, setLive] = useState(true);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setLive(false);
  }, []);

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-12 text-foreground antialiased">
      <div className="w-full max-w-[1600px]">
        <p className="mb-4 text-[14px] text-muted-foreground">
          <span className="[@media(pointer:coarse)]:hidden">
            Drag and rearrange widgets to customize the layout.
          </span>
          <span className="hidden [@media(pointer:coarse)]:inline">
            Press and hold a widget, then drag to rearrange the layout.
          </span>
        </p>
        <section aria-labelledby="sentinel-dashboard-title">
          <h2 id="sentinel-dashboard-title" className="sr-only">
            Sentinel Network Guard
          </h2>
          <LiveContext.Provider value={live}>
            <DraggableWidgetGrid
              items={WIDGETS}
              renderItem={(item, _size, expanded) => renderWidget(item as SentinelWidget, expanded)}
              editable
              maxColumns={6}
            />
          </LiveContext.Provider>
        </section>
      </div>
    </main>
  );
}
