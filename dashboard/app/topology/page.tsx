"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/card";
import { api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

export default function TopologyPage() {
  const [current, setCurrent] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getTopology();
        setCurrent(res.snapshot);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <div className="p-6 text-[var(--muted)]">Loading...</div>;

  const containers = current?.containers ? (typeof current.containers === "string" ? JSON.parse(current.containers) : current.containers) : {};
  const ports = current?.listening_ports ? (typeof current.listening_ports === "string" ? JSON.parse(current.listening_ports) : current.listening_ports) : {};

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Topology</h2>
        {current?.snapshot_ts && (
          <span className="text-xs text-[var(--muted)]">
            Last updated: {formatDate(current.snapshot_ts)}
          </span>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardTitle>Containers ({Object.keys(containers).length})</CardTitle>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {Object.entries(containers).length > 0 ? (
              Object.entries(containers).map(([id, info]: [string, any]) => (
                <div key={id} className="p-3 rounded-lg bg-[var(--surface-2)] text-sm">
                  <div className="font-medium text-[var(--fg)]">{info.name || id}</div>
                  <div className="text-xs text-[var(--muted)] font-mono mt-1">
                    {info.image || "unknown image"}
                  </div>
                  {info.status && (
                    <div className={cn(
                      "text-xs mt-1",
                      info.status === "running" ? "text-green-400" : "text-yellow-400"
                    )}>
                      {info.status}
                    </div>
                  )}
                </div>
              ))
            ) : (
              <p className="text-[var(--muted)] text-sm">No containers yet</p>
            )}
          </div>
        </Card>

        <Card>
          <CardTitle>Listening Ports ({Object.keys(ports).length})</CardTitle>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {Object.entries(ports).length > 0 ? (
              Object.entries(ports).map(([port, info]: [string, any]) => (
                <div key={port} className="flex justify-between text-sm py-1 border-b border-[var(--border)]">
                  <span className="font-mono text-[var(--fg)]">{info.ip || "0.0.0.0"}:{port}</span>
                  <span className="text-[var(--muted)] text-xs truncate ml-2">{info.process || ""}</span>
                </div>
              ))
            ) : (
              <p className="text-[var(--muted)] text-sm">No port data yet</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
