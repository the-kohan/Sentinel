'use client'

import { useEffect, useState } from 'react'
import { Card, CardTitle } from '@/components/card'
import { api, type Event } from '@/lib/api'
import { cn, formatDate, sourceIcon } from '@/lib/utils'

interface AnomalyEvent {
  id: number
  ts: string
  source: string
  src_ip?: string
  dst_ip?: string
  dst_port?: number
  proto?: string
  severity?: number
  anomaly_type?: string
}

const SEVERITY_COLORS: Record<number, string> = {
  1: 'border-l-green-400',
  2: 'border-l-green-400',
  3: 'border-l-yellow-400',
  4: 'border-l-orange-400',
  5: 'border-l-red-400',
}

const TYPE_LABELS: Record<string, string> = {
  unrecognized_destination: 'New destination',
  anomalous_pattern: 'Anomalous pattern',
  volume_spike: 'Volume spike',
  port_scan: 'Port scan',
  dns_anomaly: 'DNS anomaly',
  baseline_deviation: 'Baseline deviation',
}

export default function AnomalyFeedWidget() {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.getAnomalies(24)
        if (cancelled) return
        const list = (res.anomalies ?? []).slice(0, 12)
        if (!cancelled) {
          setAnomalies(list)
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
      <CardTitle>Anomalies</CardTitle>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--muted)]">
          Last 24h · {anomalies.length} anomalies
        </span>
        {lastUpdate && (
          <span className="text-[10px] text-[var(--muted)]">
            {new Date(lastUpdate).toLocaleTimeString('en-GB', {
              hour: '2-digit',
              minute: '2-digit',
              timeZone: 'Africa/Nairobi',
            })}
          </span>
        )}
      </div>
      {loading ? (
        <div className="flex items-center justify-center h-[160px] text-[var(--muted)]">
          Loading...
        </div>
      ) : anomalies.length === 0 ? (
        <div className="flex items-center justify-center h-[160px]">
          <p className="text-[var(--muted)] text-sm">No anomalies</p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-[160px] overflow-y-auto">
          {anomalies.map((a) => (
            <div
              key={a.id}
              className={cn(
                'p-2 rounded-lg border-l-2 bg-[var(--surface-2)] text-xs',
                SEVERITY_COLORS[a.severity ?? 3] ?? 'border-l-yellow-400',
              )}>
              <div className="flex justify-between items-start gap-2">
                <div className="min-w-0">
                  <p className="font-mono text-[var(--fg)] truncate">
                    {a.dst_ip}
                    {a.dst_port ? `:${a.dst_port}` : ''}
                  </p>
                  <p className="text-[var(--muted)] mt-0.5 flex items-center gap-1">
                    {sourceIcon(a.source)}
                    {TYPE_LABELS[a.anomaly_type || 'anomalous_pattern'] ||
                      'Anomaly'}
                    {a.proto && ` · ${a.proto}`}
                  </p>
                </div>
                <span className="text-[var(--muted)] shrink-0">
                  {formatDate(a.ts)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
