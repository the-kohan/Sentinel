const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8100";

export interface Event {
  id: number;
  ts: string;
  source: string;
  src_ip?: string;
  src_port?: number;
  dst_ip?: string;
  dst_port?: number;
  proto?: string;
  direction?: string;
  bytes?: number;
  container_id?: string;
  service_name?: string;
  raw_data?: any;
}

export interface Incident {
  id: number;
  opened_ts: string;
  closed_ts?: string;
  severity: number;
  summary: string;
  related_events?: number[];
  llm_assessment?: string;
  operator_acknowledged: boolean;
  operator_note?: string;
  recommended_action?: string;
}

export interface ReputationEntry {
  identifier: string;
  first_seen: string;
  last_seen: string;
  contact_count: number;
  verdict: "benign" | "unknown" | "suspicious";
  note?: string;
  last_updated: string;
}

export interface AllowlistEntry {
  id: number;
  pattern: string;
  source: string;
  reason: string;
  added_ts: string;
  added_by: string;
  expiry?: string;
}

export interface MuteEntry {
  id: number;
  target: string;
  muted_until_ts: string;
  reason: string;
  created_ts: string;
}

export interface Summary {
  period_hours: number;
  events_by_source: Record<string, number>;
  top_talkers: { dst_ip: string; contacts: number; last_seen: string }[];
  open_incidents: number;
  reputation: Record<string, number>;
  active_mutes: number;
  timestamp: string;
}

export interface Status {
  status: string;
  version: string;
  db: string;
  timestamp: string;
}

export interface SetupStatus {
  initialized: boolean;
  event_count: number;
  topology_count: number;
  allowlist_count: number;
  open_incidents: number;
  telegram_configured: boolean;
  issues: string[];
}

export interface DriftResponse {
  drift_detected: boolean;
  message?: string;
  new_containers?: string[];
  removed_containers?: string[];
  current_count?: number;
  previous_count?: number;
}

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  getStatus: () => fetchJSON<Status>("/api/status"),
  getSetupStatus: () => fetchJSON<SetupStatus>("/api/setup/status"),
  getSummary: (hours = 24) => fetchJSON<Summary>(`/api/query/summary?hours=${hours}`),
  getTopology: () => fetchJSON<any>(`/api/topology/current`),
  getEvents: (params?: { source?: string; src_ip?: string; dst_ip?: string; direction?: string; hours?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.source) q.set("source", params.source);
    if (params?.src_ip) q.set("src_ip", params.src_ip);
    if (params?.dst_ip) q.set("dst_ip", params.dst_ip);
    if (params?.direction) q.set("direction", params.direction);
    if (params?.hours) q.set("hours", params.hours.toString());
    if (params?.limit) q.set("limit", params.limit.toString());
    return fetchJSON<{ events: Event[]; total: number }>(`/api/events?${q}`);
  },
  getEvent: (id: number) => fetchJSON<{ event: Event }>(`/api/events/${id}`),
  getAnomalies: (hours = 24) => fetchJSON<{ anomalies: Event[] }>(`/api/anomalies?hours=${hours}`),
  getIncidents: (status?: string, severity?: string) => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    if (severity) q.set("severity", severity);
    return fetchJSON<{ incidents: Incident[] }>(`/api/incidents?${q}`);
  },
  getReputation: (verdict?: string) => {
    const q = new URLSearchParams();
    if (verdict) q.set("verdict", verdict);
    return fetchJSON<{ sources: ReputationEntry[] }>(`/api/reputation?${q}`);
  },
  getAllowlist: (status?: string) => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    return fetchJSON<{ entries: AllowlistEntry[] }>(`/api/allowlist?${q}`);
  },
  getMutes: () => fetchJSON<{ mutes: MuteEntry[] }>("/api/mute"),
  getDrift: () => fetchJSON<DriftResponse>("/api/drift"),
  addAllowlistEntry: async (pattern: string, source: string, reason: string) => {
    const res = await fetch(`${API_BASE}/api/allowlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pattern, source, reason }),
    });
    return res.json();
  },
  deleteAllowlistEntry: async (pattern: string) => {
    const res = await fetch(`${API_BASE}/api/allowlist/${encodeURIComponent(pattern)}`, { method: "DELETE" });
    return res.json();
  },
  promoteAllowlistEntry: async (pattern: string) => {
    const res = await fetch(`${API_BASE}/api/allowlist/${encodeURIComponent(pattern)}/promote`, { method: "POST" });
    return res.json();
  },
  createIncident: async (severity: number, summary: string, related_events?: number[]) => {
    const res = await fetch(`${API_BASE}/api/incidents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ severity, summary, related_events }),
    });
    return res.json();
  },
  updateIncident: async (id: number, data: { closed?: boolean; acknowledged?: boolean; note?: string; recommended_action?: string }) => {
    const res = await fetch(`${API_BASE}/api/incidents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },
  search: (q: string) => fetchJSON<{ events: Event[]; reputation: ReputationEntry[]; allowlist: AllowlistEntry[] }>(`/api/query/search?q=${encodeURIComponent(q)}`),
  getBaselineDeviations: () => fetchJSON<{ deviations: any[]; baseline_source: string }>(`/api/baseline/deviations`),
  getSetupDiscover: () => fetchJSON<any>("/api/setup/discover"),
  setupConfirm: async (patterns: { pattern: string; source: string; reason: string }[]) => {
    const res = await fetch(`${API_BASE}/api/setup/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patterns }),
    });
    return res.json();
  },
  configureTelegram: async (token: string, chat_id: string) => {
    const res = await fetch(`${API_BASE}/api/setup/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, chat_id }),
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
  },
};
