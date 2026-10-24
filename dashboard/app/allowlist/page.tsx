"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api, type AllowlistEntry } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import { Plus, Trash2 } from "lucide-react";

export default function AllowlistPage() {
  const [entries, setEntries] = useState<AllowlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("active");
  const [showAdd, setShowAdd] = useState(false);
  const [newPattern, setNewPattern] = useState("");
  const [newReason, setNewReason] = useState("");

  async function load() {
    try {
      const res = await api.getAllowlist(statusFilter || undefined);
      setEntries(res.entries);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [statusFilter]);

  async function addEntry() {
    if (!newPattern) return;
    try {
      await api.addAllowlistEntry(newPattern, "operator", newReason);
      setNewPattern("");
      setNewReason("");
      setShowAdd(false);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  async function deleteEntry(pattern: string) {
    try {
      await api.deleteAllowlistEntry(pattern);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Allowlist</h2>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--accent)]/10 text-[var(--accent)] text-sm hover:bg-[var(--accent)]/20"
        >
          <Plus className="w-4 h-4" /> Add Entry
        </button>
      </div>

      {showAdd && (
        <Card>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Pattern (e.g., 127.0.0.53:53)"
              value={newPattern}
              onChange={(e) => setNewPattern(e.target.value)}
              className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
            />
            <input
              type="text"
              placeholder="Reason"
              value={newReason}
              onChange={(e) => setNewReason(e.target.value)}
              className="flex-1 bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
            />
            <button
              onClick={addEntry}
              className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm"
            >
              Add
            </button>
          </div>
        </Card>
      )}

      <div className="flex gap-2">
        {["active", "pending", "expired", "all"].map((s) => (
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

      <Card>
        <div className="space-y-2">
          {entries.length > 0 ? (
            entries.map((e) => (
              <div key={e.id} className="flex justify-between items-center p-3 rounded-lg bg-[var(--surface-2)]">
                <div>
                  <div className="font-mono text-sm text-[var(--fg)]">{e.pattern}</div>
                  <div className="text-xs text-[var(--muted)]">
                    {e.reason} • Added: {formatDate(e.added_ts)}
                    {e.expiry && ` • Expires: ${formatDate(e.expiry)}`}
                  </div>
                </div>
                <button
                  onClick={() => deleteEntry(e.pattern)}
                  className="text-red-400 hover:text-red-300 p-1"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))
          ) : (
            <p className="text-[var(--muted)] text-sm text-center py-4">No entries</p>
          )}
        </div>
      </Card>
    </div>
  );
}
