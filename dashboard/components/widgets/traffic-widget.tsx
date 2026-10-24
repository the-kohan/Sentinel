'use client'

import { useEffect, useRef, useState } from 'react'
import { Card, CardTitle } from '@/components/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const BUCKETS = 24 // 24 cells = 1 per hour for last 24h
const COLORS = [
  'bg-foreground/[0.04]',
  'bg-blue-500/15',
  'bg-blue-500/30',
  'bg-blue-500/50',
  'bg-blue-500/80',
]

export default function TrafficWidget() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    let cancelled = false
    let animationId: number

    async function load() {
      try {
        const res = await api.getEvents({ hours: 24, limit: 500 })
        if (cancelled) return
        const events = res.events ?? []
        const now = Date.now()
        const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000

        const buckets: number[] = new Array(BUCKETS).fill(0)
        let totalCount = 0

        for (const e of events) {
          const ts = new Date(e.ts).getTime()
          if (ts >= twentyFourHoursAgo) {
            const elapsed = ts - twentyFourHoursAgo
            const bucketIndex = Math.min(
              BUCKETS - 1,
              Math.floor((elapsed / (twentyFourHoursAgo)) * BUCKETS),
            )
            buckets[bucketIndex]++
            totalCount++
          }
        }

        if (!cancelled) {
          setTotal(totalCount)
          setLastUpdate(new Date().toISOString())
          const canvas = canvasRef.current
          if (!canvas) return
          const ctx = canvas.getContext('2d')
          if (!ctx) return
          const dpr = window.devicePixelRatio || 1
          const displayW = canvas.clientWidth
          const displayH = canvas.clientHeight
          canvas.width = displayW * dpr
          canvas.height = displayH * dpr
          ctx.scale(dpr, dpr)

          const cellW = displayW / BUCKETS
          const max = Math.max(1, ...buckets)

          ctx.clearRect(0, 0, displayW, displayH)

          // Background grid lines
          ctx.strokeStyle = 'rgba(42, 45, 58, 0.4)'
          ctx.lineWidth = 1
          for (let i = 0; i < BUCKETS; i++) {
            const x = i * cellW
            ctx.beginPath()
            ctx.moveTo(x, 0)
            ctx.lineTo(x, displayH)
            ctx.stroke()
          }

          // Bars
          for (let i = 0; i < BUCKETS; i++) {
            const level = Math.min(1, buckets[i] / max)
            const color =
              level === 0
                ? 'rgba(8, 8, 10, 0.3)'
                : `rgba(79, 140, 255, ${0.2 + level * 0.7})`
            ctx.fillStyle = color
            const barH = level * displayH * 0.85
            ctx.fillRect(
              i * cellW + 1,
              displayH - barH,
              cellW - 2,
              barH,
            )
          }

          // Current hour marker
          const nowBucket = Math.min(BUCKETS - 1, Math.floor((Date.now() - twentyFourHoursAgo) / (twentyFourHoursAgo) * BUCKETS))
          ctx.strokeStyle = 'var(--accent)'
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(nowBucket * cellW, 0)
          ctx.lineTo(nowBucket * cellW, displayH)
          ctx.stroke()

          animationId = requestAnimationFrame(() => {})
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
      if (animationId) cancelAnimationFrame(animationId)
    }
  }, [])

  return (
    <Card className="h-full">
      <CardTitle>Live Traffic</CardTitle>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--muted)] tabular-nums">
          Last 24 hours · {total.toLocaleString()} events
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
        <div className="flex items-center justify-center h-[140px] text-[var(--muted)]">
          Loading traffic data...
        </div>
      ) : (
        <div className="relative w-full flex-1 min-h-0" style={{ height: 160 }}>
          <canvas ref={canvasRef} className="w-full h-full" />
          {/* Hour labels */}
          <div className="absolute inset-0 pointer-events-none flex justify-between px-1 text-[9px] text-[var(--muted)]">
            {Array.from({ length: 6 }, (_, i) => {
              const label =
                i === 0
                  ? '00:00'
                  : i === 5
                    ? 'Now'
                    : `${String(i * 4).padStart(2, '0')}:00`
              return (
                <span
                  key={i}
                  className="truncate"
                  style={{ flex: 1, textAlign: 'center' }}
                >
                  {label}
                </span>
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
}
