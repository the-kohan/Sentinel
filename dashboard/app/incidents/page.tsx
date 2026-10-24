"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type Incident } from "@/lib/api";
import { cn, formatDate, severityColor } from "@/lib/utils";
import { Check, X, MessageSquare } from "lucide-react";

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("open");

  async function load() {
    try {
      const res = await api.getIncidents(statusFilter || undefined);
      setIncidents(res.incidents);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [statusFilter]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Incidents</h2>
        <div className="flex gap-2">
          {["open", "closed", "all"].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "px-3 py-1 rounded-lg text-sm capitalize",
                statusFilter === s
                  ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--surface-2)]"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {incidents.length > 0 ? (
          incidents.map((inc) => (
            <Card key={inc.id}>
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className={cn("text-sm font-bold", severityColor(inc.severity))}>
                      P{inc.severity}
                    </span>
                    <span className="text-sm text-[var(--fg)]">{inc.summary}</span>
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">
                    Opened: {formatDate(inc.opened_ts)}
                    {inc.closed_ts && ` • Closed: ${formatDate(inc.closed_ts)}`}
                  </div>
                  {inc.recommended_action && (
                    <div className="text-xs text-[var(--accent)] mt-1">
                      💡 {inc.recommended_action}
                    </div>
                  )}
                  {inc.operator_note && (
                    <div className="text-xs text-[var(--muted)] mt-1">
                      📝 {inc.operator_note}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {inc.operator_acknowledged ? (
                    <span className="text-green-400 text-xs flex items-center gap-1">
                      <Check className="w-3 h-3" /> Acked
                    </span>
                  ) : (
                    <span className="text-yellow-400 text-xs">Pending</span>
                  )}
                </div>
              </div>
            </Card>
          ))
        ) : (
          <Card>
            <p className="text-[var(--muted)] text-sm text-center py-4">No incidents</p>
          </Card>
        )}
      </div>
    </div>
  );
}
