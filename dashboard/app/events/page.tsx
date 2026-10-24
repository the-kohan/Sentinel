"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type Event } from "@/lib/api";
import { cn, formatDate, sourceIcon } from "@/lib/utils";

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<string>("");
  const [hours, setHours] = useState(24);

  async function load() {
    try {
      const res = await api.getEvents({ source: source || undefined, hours, limit: 100 });
      setEvents(res.events);
      setTotal(res.total);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [source, hours]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Events</h2>
        <span className="text-xs text-[var(--muted)]">{total} total</span>
      </div>

      <div className="flex gap-3">
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All sources</option>
          <option value="docker">Docker</option>
          <option value="host">Host</option>
          <option value="pcap">PCAP</option>
        </select>
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
        >
          <option value={1}>1h</option>
          <option value={6}>6h</option>
          <option value={24}>24h</option>
          <option value={168}>7d</option>
        </select>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--border)]">
                <th className="pb-2 pr-4">Time</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4">Direction</th>
                <th className="pb-2 pr-4">Destination</th>
                <th className="pb-2">Proto</th>
              </tr>
            </thead>
            <tbody>
              {events.length > 0 ? (
                events.map((e) => (
                  <tr key={e.id} className="border-b border-[var(--border)]/50 hover:bg-[var(--surface-2)]">
                    <td className="py-2 pr-4 text-[var(--muted)] whitespace-nowrap">{formatDate(e.ts)}</td>
                    <td className="py-2 pr-4">{sourceIcon(e.source)} {e.source}</td>
                    <td className="py-2 pr-4">
                      <span className={cn(
                        "px-2 py-0.5 rounded text-xs",
                        e.direction === "inbound" ? "bg-blue-400/10 text-blue-400" : "bg-purple-400/10 text-purple-400"
                      )}>
                        {e.direction || "?"}
                      </span>
                    </td>
                    <td className="py-2 pr-4 font-mono text-[var(--fg)]">
                      {e.dst_ip}{e.dst_port ? `:${e.dst_port}` : ""}
                    </td>
                    <td className="py-2 text-[var(--muted)]">{e.proto || "?"}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={5} className="py-8 text-center text-[var(--muted)]">No events found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
