'use client'

import { useEffect, useRef, useState } from 'react'
import { Card, CardTitle } from '@/components/card'
import { cn } from '@/lib/utils'

interface DeviationEntry {
  entity: string
  metric: string
  current: number
  baseline: number
  deviation: number // percentage above baseline
  severity: 'normal' | 'elevated' | 'high'
}

const DEV_COLOR: Record<string, string> = {
  normal: 'text-[var(--green)]',
  elevated: 'text-[var(--yellow)]',
  high: 'text-[var(--red)]',
}

export default function BaselineWidget() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [deviations, setDeviations] = useState<DeviationEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [totalDeviations, setTotalDeviations] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function compute() {
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8100'}/api/baseline/deviations`,
        )
        if (!res.ok) throw new Error(`API ${res.status}`)
        const json = await res.json()
        const deviations: DeviationEntry[] = (json.deviations || []).map((d: any) => ({
          entity: d.entity,
          metric: d.metric,
          current: d.current,
          baseline: d.baseline,
          deviation: d.deviation,
          severity: d.severity as DeviationEntry['severity'],
        }))
        if (!cancelled) {
          setDeviations(
            deviations.sort((a, b) => Math.abs(b.deviation) - Math.abs(a.deviation)),
          )
          setTotalDeviations(deviations.length)
          setLastUpdate(new Date().toISOString())
        }
      } catch (err) {
        console.error('Baseline computation error:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    compute()
    const interval = setInterval(compute, 2000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <Card className="h-full">
      <CardTitle>Baseline Deviations</CardTitle>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--muted)]">
          {loading ? 'Computing...' : `${totalDeviations} entities tracked`}
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
          Analyzing baselines...
        </div>
      ) : deviations.length === 0 ? (
        <div className="flex items-center justify-center h-[160px]">
          <p className="text-[var(--muted)] text-sm">No data yet</p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-[160px] overflow-y-auto">
          {deviations.map((d, i) => (
            <div
              key={`${d.entity}-${d.metric}-${i}`}
              className={cn(
                'flex items-center justify-between p-2 rounded-lg bg-[var(--surface-2)] text-xs',
                i < 3 ? 'border-l-2' : '',
                d.severity === 'high'
                  ? 'border-l-red-400'
                  : d.severity === 'elevated'
                    ? 'border-l-yellow-400'
                    : 'border-l-transparent',
              )}>
              <div className="min-w-0">
                <p className="font-mono text-[var(--fg)] truncate">{d.entity}</p>
                <p className="text-[var(--muted)]">{d.metric}</p>
              </div>
              <div className="text-right shrink-0">
                <p className={cn('font-mono tabular-nums', DEV_COLOR[d.severity])}>
                  {d.current}
                  <span className="text-[var(--muted)] text-[10px]">
                    {' '}
                    / {d.baseline}
                  </span>
                </p>
                <p className={cn('text-[10px]', DEV_COLOR[d.severity])}>
                  {d.deviation > 0 ? '+' : ''}
                  {d.deviation}%
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
