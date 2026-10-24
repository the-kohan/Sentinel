"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SetupPage() {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tgToken, setTgToken] = useState("");
  const [tgChatId, setTgChatId] = useState("");
  const [tgSaving, setTgSaving] = useState(false);
  const [tgSaved, setTgSaved] = useState(false);

  useEffect(() => {
    api.getSetupStatus().then(setStatus).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function saveTelegram() {
    setTgSaving(true);
    try {
      await api.configureTelegram(tgToken, tgChatId);
      setTgSaved(true);
      setTimeout(() => setTgSaved(false), 3000);
      // Refresh status
      api.getSetupStatus().then(setStatus).catch(console.error);
    } catch (err) {
      console.error(err);
    } finally {
      setTgSaving(false);
    }
  }

  if (loading) return <div className="p-6 text-[var(--muted)]">Loading...</div>;

  const issues = status?.issues || [];
  const ready = status?.initialized;

  return (
    <div className="p-6 space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Setup</h1>
        {ready && (
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            All configured
          </span>
        )}
      </div>

      {/* Status Overview */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="text-xs text-[var(--muted)] uppercase tracking-wide">Events</div>
          <div className="text-lg font-semibold mt-1">{status?.event_count ?? 0}</div>
          {!issues.includes("no_events") && <div className="text-xs text-emerald-400 mt-1">Collecting</div>}
          {issues.includes("no_events") && <div className="text-xs text-rose-400 mt-1">No data yet</div>}
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="text-xs text-[var(--muted)] uppercase tracking-wide">Topology</div>
          <div className="text-lg font-semibold mt-1">{status?.topology_count ?? 0}</div>
          {!issues.includes("no_topology") && <div className="text-xs text-emerald-400 mt-1">Snapshots ready</div>}
          {issues.includes("no_topology") && <div className="text-xs text-rose-400 mt-1">No snapshots</div>}
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="text-xs text-[var(--muted)] uppercase tracking-wide">Allowlist</div>
          <div className="text-lg font-semibold mt-1">{status?.allowlist_count ?? 0}</div>
          {!issues.includes("empty_allowlist") && <div className="text-xs text-emerald-400 mt-1">Entries configured</div>}
          {issues.includes("empty_allowlist") && <div className="text-xs text-rose-400 mt-1">Empty</div>}
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="text-xs text-[var(--muted)] uppercase tracking-wide">Open Incidents</div>
          <div className="text-lg font-semibold mt-1">{status?.open_incidents ?? 0}</div>
        </div>
      </div>

      {/* Telegram Configuration */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="text-lg font-semibold mb-1">Telegram Notifications</h2>
        <p className="text-sm text-[var(--muted)] mb-4">
          Connect a Telegram bot so Sentinel can send alerts directly to your phone.
        </p>

        {status?.telegram_configured ? (
          <div className="flex items-center gap-2 text-sm text-emerald-400">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            Telegram bot is configured and ready
          </div>
        ) : (
          <div className="space-y-3">
            <input
              type="password"
              placeholder="Bot Token (from @BotFather)"
              value={tgToken}
              onChange={(e) => setTgToken(e.target.value)}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="text"
              placeholder="Chat ID (your Telegram user ID)"
              value={tgChatId}
              onChange={(e) => setTgChatId(e.target.value)}
              className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--fg)] placeholder:text-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="flex gap-2">
              <button
                onClick={saveTelegram}
                disabled={tgSaving || !tgToken || !tgChatId}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-ring text-ring-foreground hover:bg-ring/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {tgSaving ? "Saving..." : tgSaved ? "Saved!" : "Save Telegram Config"}
              </button>
              <a
                href="https://t.me/BotFather"
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--muted)] hover:text-[var(--fg)] transition-colors"
              >
                Get Bot Token
              </a>
            </div>
          </div>
        )}
      </div>

      {/* What's Missing */}
      {issues.length > 0 && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
          <h3 className="text-sm font-semibold text-amber-400 mb-2">Setup Checklist</h3>
          <ul className="space-y-1 text-sm text-[var(--muted)]">
            {issues.map((issue: string) => (
              <li key={issue} className="flex items-center gap-2">
                <span className="text-rose-400">●</span>
                {issue === "no_events" && "No network events collected yet — watchers need to run"}
                {issue === "no_topology" && "No topology snapshots — run a watcher cycle first"}
                {issue === "empty_allowlist" && "Allowlist is empty — add known services to reduce noise"}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Quick Info */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
        <p className="mb-2"><span className="text-[var(--fg)] font-medium">Sentinel</span> watches your Docker mesh and host network for unusual activity.</p>
        <p className="text-xs">Current stack: {status?.allowlist_count ?? 0} known services, {status?.event_count ?? 0} events captured.</p>
      </div>
    </div>
  );
}
