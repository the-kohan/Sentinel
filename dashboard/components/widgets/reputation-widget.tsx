'use client'

import { useEffect, useState } from 'react'
import { Card, CardTitle } from '@/components/card'
import { api, type ReputationEntry } from '@/lib/api'
import { cn, verdictBg, verdictColor, formatDate } from '@/lib/utils'

const VERDICT_LABELS: Record<string, string> = {
  benign: 'Trusted',
  unknown: 'Unknown',
  suspicious: 'Suspicious',
}

export default function ReputationWidget() {
  const [sources, setSources] = useState<ReputationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.getReputation()
        if (cancelled) return
        const list = (res.sources ?? []).slice(0, 10)
        const countMap: Record<string, number> = {}
        for (const s of list) {
          countMap[s.verdict] = (countMap[s.verdict] || 0) + 1
        }
        if (!cancelled) {
          setSources(list)
          setCounts(countMap)
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

  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <Card className="h-full">
      <CardTitle>Source Reputation</CardTitle>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--muted)]">
          {loading ? 'Loading...' : `${total} sources tracked`}
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
          Loading reputation...
        </div>
      ) : total === 0 ? (
        <div className="flex items-center justify-center h-[160px]">
          <p className="text-[var(--muted)] text-sm">No reputation data</p>
        </div>
      ) : (
        <div className="h-full flex flex-col gap-2">
          {/* Summary badges */}
          <div className="flex gap-2 mb-2">
            {(['benign', 'unknown', 'suspicious'] as const).map((v) => (
              <div
                key={v}
                className={cn(
                  'flex-1 rounded-lg p-2 text-center text-xs',
                  verdictBg(v),
                )}
              >
                <p className={cn('font-bold text-sm', verdictColor(v))}>
                  {counts[v] || 0}
                </p>
                <p className="text-[10px] text-[var(--muted)] capitalize">
                  {VERDICT_LABELS[v]}
                </p>
              </div>
            ))}
          </div>
          {/* Source list */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="space-y-1 max-h-[120px] overflow-y-auto">
              {sources.map((s) => (
                <div
                  key={s.identifier}
                  className="flex items-center justify-between p-1.5 rounded bg-[var(--surface-2)] text-xs"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-[var(--fg)] truncate">
                      {s.identifier}
                    </p>
                    <p className="text-[var(--muted)]">
                      {s.contact_count} contacts · last {formatDate(s.last_seen)}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium capitalize',
                      verdictColor(s.verdict),
                      verdictBg(s.verdict),
                    )}
                  >
                    {VERDICT_LABELS[s.verdict]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
