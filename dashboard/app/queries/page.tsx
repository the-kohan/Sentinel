"use client";

import { useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type Event, type ReputationEntry, type AllowlistEntry } from "@/lib/api";
import { cn, formatDate, sourceIcon, verdictColor, verdictBg } from "@/lib/utils";

export default function QueriesPage() {
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState<Event[]>([]);
  const [reputation, setReputation] = useState<ReputationEntry[]>([]);
  const [allowlist, setAllowlist] = useState<AllowlistEntry[]>([]);
  const [loading, setLoading] = useState(false);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.search(query);
      setEvents(res.events);
      setReputation(res.reputation);
      setAllowlist(res.allowlist);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-bold">Search</h2>

      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search IPs, ports, patterns..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
          className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-4 py-2 text-sm"
        />
        <button
          onClick={runSearch}
          disabled={loading}
          className="px-6 py-2 rounded-lg bg-[var(--accent)] text-white text-sm disabled:opacity-50"
        >
          {loading ? "..." : "Search"}
        </button>
      </div>

      {events.length > 0 && (
        <Card>
          <CardTitle>Events ({events.length})</CardTitle>
          <div className="space-y-1">
            {events.slice(0, 20).map((e) => (
              <div key={e.id} className="flex justify-between text-sm py-1 border-b border-[var(--border)]/50">
                <span className="text-[var(--muted)]">{formatDate(e.ts)}</span>
                <span>{sourceIcon(e.source)} {e.source}</span>
                <span className="font-mono text-[var(--fg)]">
                  {e.dst_ip}{e.dst_port ? `:${e.dst_port}` : ""}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {reputation.length > 0 && (
        <Card>
          <CardTitle>Reputation ({reputation.length})</CardTitle>
          <div className="space-y-1">
            {reputation.map((r) => (
              <div key={r.identifier} className="flex justify-between text-sm py-1 border-b border-[var(--border)]/50">
                <span className="font-mono text-[var(--fg)]">{r.identifier}</span>
                <span className={cn(
                  "px-2 py-0.5 rounded text-xs capitalize",
                  verdictBg(r.verdict),
                  verdictColor(r.verdict)
                )}>
                  {r.verdict}
                </span>
                <span className="text-[var(--muted)]">{r.contact_count} contacts</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {allowlist.length > 0 && (
        <Card>
          <CardTitle>Allowlist ({allowlist.length})</CardTitle>
          <div className="space-y-1">
            {allowlist.map((a) => (
              <div key={a.id} className="flex justify-between text-sm py-1 border-b border-[var(--border)]/50">
                <span className="font-mono text-[var(--fg)]">{a.pattern}</span>
                <span className="text-[var(--muted)]">{a.reason}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {events.length === 0 && reputation.length === 0 && allowlist.length === 0 && query && !loading && (
        <Card>
          <p className="text-[var(--muted)] text-sm text-center py-4">No results for "{query}"</p>
        </Card>
      )}
    </div>
  );
}
