"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type Event } from "@/lib/api";
import { cn, formatDate, sourceIcon } from "@/lib/utils";

export default function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getAnomalies(hours);
        setAnomalies(res.anomalies);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [hours]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Anomalies</h2>
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
        <div className="space-y-2">
          {anomalies.length > 0 ? (
            anomalies.map((a: any) => (
              <div key={a.id} className="p-3 rounded-lg bg-[var(--surface-2)] border-l-2 border-yellow-400">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="text-sm font-medium text-[var(--fg)]">
                      {sourceIcon(a.source)} {a.anomaly_type?.replace("_", " ") || "anomaly"}
                    </div>
                    <div className="text-xs text-[var(--muted)] font-mono mt-1">
                      {a.dst_ip}{a.dst_port ? `:${a.dst_port}` : ""}
                    </div>
                  </div>
                  <span className="text-xs text-[var(--muted)]">{formatDate(a.ts)}</span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-[var(--muted)] text-sm py-4 text-center">No anomalies detected</p>
          )}
        </div>
      </Card>
    </div>
  );
}
