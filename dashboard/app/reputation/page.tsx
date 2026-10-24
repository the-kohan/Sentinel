"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type ReputationEntry } from "@/lib/api";
import { cn, formatDate, verdictColor, verdictBg } from "@/lib/utils";

export default function ReputationPage() {
  const [sources, setSources] = useState<ReputationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [verdictFilter, setVerdictFilter] = useState<string>("");

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getReputation(verdictFilter || undefined);
        setSources(res.sources);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [verdictFilter]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Source Reputation</h2>
        <div className="flex gap-2">
          {["", "benign", "unknown", "suspicious"].map((v) => (
            <button
              key={v}
              onClick={() => setVerdictFilter(v)}
              className={cn(
                "px-3 py-1 rounded-lg text-sm capitalize",
                verdictFilter === v
                  ? "bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--surface-2)]"
              )}
            >
              {v || "All"}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--border)]">
                <th className="pb-2 pr-4">Identifier</th>
                <th className="pb-2 pr-4">Verdict</th>
                <th className="pb-2 pr-4">Contacts</th>
                <th className="pb-2 pr-4">Last Seen</th>
                <th className="pb-2">Note</th>
              </tr>
            </thead>
            <tbody>
              {sources.length > 0 ? (
                sources.map((s) => (
                  <tr key={s.identifier} className="border-b border-[var(--border)]/50 hover:bg-[var(--surface-2)]">
                    <td className="py-2 pr-4 font-mono text-[var(--fg)]">{s.identifier}</td>
                    <td className="py-2 pr-4">
                      <span className={cn(
                        "px-2 py-0.5 rounded text-xs capitalize",
                        verdictBg(s.verdict),
                        verdictColor(s.verdict)
                      )}>
                        {s.verdict}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-[var(--muted)]">{s.contact_count}</td>
                    <td className="py-2 pr-4 text-[var(--muted)]">{formatDate(s.last_seen)}</td>
                    <td className="py-2 text-[var(--muted)] text-xs">{s.note || "—"}</td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={5} className="py-8 text-center text-[var(--muted)]">No reputation entries</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
