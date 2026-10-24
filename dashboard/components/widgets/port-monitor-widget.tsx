'use client'

import { useEffect, useState } from 'react'
import { Card, CardTitle } from '@/components/card'
import { api } from '@/lib/api'
import { cn, formatDate } from '@/lib/utils'

interface PortEntry {
  port: string
  process?: string
  ip?: string
  protocol?: string
}

interface ConnectionEntry {
  src_ip: string
  dst_ip: string
  dst_port: number
  proto: string
  direction: string
  ts: string
  id: number
}

export default function PortMonitorWidget() {
  const [ports, setPorts] = useState<PortEntry[]>([])
  const [connections, setConnections] = useState<ConnectionEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        // Topology for listening ports
        const topoRes = await api.getTopology()
        const snap = topoRes.snapshot
        if (!snap) {
          if (!cancelled) {
            setPorts([])
            setConnections([])
          }
          return
        }

        const rawPorts: Record<string, any> =
          typeof snap.listening_ports === 'string'
            ? JSON.parse(snap.listening_ports)
            : snap.listening_ports ?? {}
        const portList: PortEntry[] = Object.entries(rawPorts)
          .map(([port, info]) => ({
            port,
            process: info?.process,
            ip: typeof info?.ip === 'string' ? info.ip : undefined,
            protocol: info?.proto,
          }))
          .sort((a, b) => parseInt(a.port) - parseInt(b.port))

        // Recent connections from events (last 2 min)
        const eventsRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8100'}/api/events?hours=0.033&limit=30`,
        )
        if (eventsRes.ok) {
          const evJson = await eventsRes.json()
          const evList: ConnectionEntry[] = (
            (evJson.events || []) as any[]
          )
            .slice(0, 15)
            .map((e: any) => ({
              src_ip: e.src_ip || '—',
              dst_ip: e.dst_ip || '—',
              dst_port: e.dst_port || 0,
              proto: e.proto || 'tcp',
              direction: e.direction || '—',
              ts: e.ts,
              id: e.id,
            }))
          if (!cancelled) setConnections(evList)
        }

        if (!cancelled) {
          setPorts(portList)
          setLastUpdate(new Date().toISOString())
        }
      } catch (err) {
        console.error(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, 2000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <Card className="h-full">
      <CardTitle>Port Monitor</CardTitle>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--muted)]">
          {loading ? 'Loading...' : `${ports.length} listening · ${connections.length} active`}
        </span>
        {lastUpdate && (
          <span className="text-[10px] text-[var(--muted)]">
            {new Date(lastUpdate).toLocaleTimeString('en-GB', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
              timeZone: 'Africa/Nairobi',
            })}
          </span>
        )}
      </div>
      {loading ? (
        <div className="flex items-center justify-center h-[160px] text-[var(--muted)]">
          Loading ports...
        </div>
      ) : ports.length === 0 && connections.length === 0 ? (
        <div className="flex items-center justify-center h-[160px]">
          <p className="text-[var(--muted)] text-sm">No port data</p>
        </div>
      ) : (
        <div className="h-full flex flex-col gap-2 overflow-hidden">
          {/* Listening ports */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            <p className="text-[10px] text-[var(--muted)] uppercase tracking-wide mb-1.5">
              Listening Ports
            </p>
            <div className="space-y-0.5 max-h-[80px] overflow-y-auto">
              {ports.slice(0, 12).map((p) => (
                <div
                  key={p.port}
                  className="flex items-center justify-between text-xs py-0.5 border-b border-[var(--border)]/50 last:border-0"
                >
                  <span className="font-mono text-[var(--fg)]">
                    {p.ip && p.ip !== '0.0.0.0' ? `${p.ip}:` : 'localhost:'}
                    {p.port}
                  </span>
                  <span className="text-[var(--muted)] truncate ml-2 min-w-0 flex-1">
                    {p.process || p.protocol || '—'}
                  </span>
                </div>
              ))}
              {ports.length === 0 && (
                <p className="text-[var(--muted)] text-xs pl-1">None</p>
              )}
            </div>
          </div>
          {/* Active connections */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            <p className="text-[10px] text-[var(--muted)] uppercase tracking-wide mb-1.5">
              Active Connections
            </p>
            <div className="space-y-0.5 max-h-[80px] overflow-y-auto">
              {connections.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between text-xs py-0.5 border-b border-[var(--border)]/50 last:border-0"
                >
                  <span className="font-mono text-[var(--fg)] truncate">
                    {c.src_ip}
                  </span>
                  <span className="text-[var(--muted)]">
                    → {c.dst_ip}:{c.dst_port}
                    {' '}
                    <span className="text-[10px]">({c.proto})</span>
                  </span>
                </div>
              ))}
              {connections.length === 0 && (
                <p className="text-[var(--muted)] text-xs pl-1">None active</p>
              )}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
