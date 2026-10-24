'use client'

import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import { api } from '@/lib/api'
import { Card, CardTitle } from '@/components/card'
import { cn, formatDate } from '@/lib/utils'

interface Node {
  id: string
  label: string
  type: 'container' | 'host' | 'service'
  status?: string
  group: number
}

interface Link {
  source: string
  target: string
  value: number
  proto?: string
}

export default function TopologyWidget() {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [data, setData] = useState<{
    containers: Record<string, any>
    ports: Record<string, any>
    arp: any[]
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastTs, setLastTs] = useState<string | null>(null)
  const widthRef = useRef(0)
  const heightRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.getTopology()
        if (cancelled) return
        const snap = res.snapshot
        if (!snap) {
          setData(null)
          setLastTs(null)
          return
        }
        const containers: Record<string, any> =
          typeof snap.containers === 'string'
            ? JSON.parse(snap.containers)
            : snap.containers ?? {}
        const ports: Record<string, any> =
          typeof snap.listening_ports === 'string'
            ? JSON.parse(snap.listening_ports)
            : snap.listening_ports ?? {}
        const arp: any[] = Array.isArray(snap.arp_table)
          ? snap.arp_table
          : []
        if (!cancelled) {
          setData({ containers, ports, arp })
          setLastTs(snap.snapshot_ts || null)
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

  useEffect(() => {
    if (!svgRef.current || !data) return
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const rect = svgRef.current.getBoundingClientRect()
    widthRef.current = rect.width || 400
    heightRef.current = rect.height || 260

    const w = widthRef.current
    const h = heightRef.current
    const g = svg
      .attr('viewBox', `0 0 ${w} ${h}`)
      .append('g')

    const nodes: Node[] = []
    const nodeMap = new Map<string, Node>()

    // Host node
    const host: Node = {
      id: 'host',
      label: 'Host PC',
      type: 'host',
      status: 'active',
      group: 1,
    }
    nodes.push(host)
    nodeMap.set('host', host)

    // Container nodes
    Object.entries(data.containers).forEach(([id, info]) => {
      const n: Node = {
        id,
        label: (info.name || id).substring(0, 18),
        type: 'container',
        status: info.status || undefined,
        group: 2,
      }
      nodes.push(n)
      nodeMap.set(id, n)
    })

    // Service nodes from listening ports
    Object.entries(data.ports).forEach(([port, info]) => {
      const svc = (info.service || `*:${port}`).substring(0, 16)
      let id = `svc:${port}`
      if (!nodeMap.has(id)) {
        const n: Node = {
          id,
          label: svc,
          type: 'service',
          group: 3,
        }
        nodes.push(n)
        nodeMap.set(id, n)
      }
    })

    // Links: host -> containers, containers -> services
    const links: Link[] = []

    Object.entries(data.containers).forEach(([cid]) => {
      links.push({ source: 'host', target: cid, value: 1 })
    })

    Object.entries(data.ports).forEach(([port, info]) => {
      // Heuristic: if a container exposes this port, link it
      let linkedContainer: string | undefined
      for (const [cid, cinfo] of Object.entries(data.containers)) {
        const exposed =
          typeof cinfo.exposed_ports === 'object' && cinfo.exposed_ports
        if (exposed && Object.keys(exposed).some((p) => p.includes(port))) {
          linkedContainer = cid
          break
        }
      }
      if (linkedContainer) {
        links.push({ source: linkedContainer, target: `svc:${port}`, value: 2 })
      } else {
        links.push({ source: 'host', target: `svc:${port}`, value: 1 })
      }
    })

    // ARP links
    if (Array.isArray(data.arp) && data.arp.length) {
      data.arp.slice(0, 12).forEach((entry: any) => {
        const ip = entry.ip_addr || entry.ip || entry
        if (ip && nodeMap.has(ip)) {
          links.push({ source: 'host', target: ip, value: 1 })
        }
      })
    }

    if (nodes.length <= 1) {
      g.append('text')
        .attr('x', w / 2)
        .attr('y', h / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', 'var(--muted)')
        .attr('font-size', 13)
        .text('No topology data yet')
      return
    }

    const simulation = d3
      .forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force(
        'link',
        d3
          .forceLink(links)
          .id((d: any) => (d as Node).id)
          .distance(70),
      )
      .force('charge', d3.forceManyBody().strength(-220))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .force('collision', d3.forceCollide(22))

    const link = g
      .append('g')
      .attr('stroke', 'var(--border)')
      .attr('stroke-opacity', 0.6)
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke-width', (d: any) => Math.max(1, (d.value || 1) * 1.2))

    const node = g
      .append('g')
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 1.5)
      .selectAll<SVGGElement, d3.SimulationNodeDatum>('g')
      .data(nodes as d3.SimulationNodeDatum[])
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3.drag<SVGGElement, d3.SimulationNodeDatum>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )

    node
      .append('circle')
      .attr('r', (d) => {
        const n = d as Node
        return n.type === 'host' ? 12 : n.type === 'service' ? 7 : 9
      })
      .attr('fill', (d) => {
        const n = d as Node
        if (n.type === 'host') return 'var(--accent)'
        if (n.type === 'service') return 'var(--green)'
        return n.status === 'running' ? 'var(--green)' : 'var(--yellow)'
      })
      .attr('stroke', (d) => {
        const n = d as Node
        return n.type === 'host'
          ? 'var(--accent)'
          : n.type === 'service'
            ? 'var(--green)'
            : 'var(--border)'
      })

    node
      .append('text')
      .attr('dy', (d) => {
        const n = d as Node
        return n.type === 'host' ? -16 : -12
      })
      .attr('text-anchor', 'middle')
      .attr('fill', 'var(--fg)')
      .attr('font-size', 10)
      .attr('font-family', 'var(--font-mono)')
      .text((d) => { const n = d as Node; return n.label })

    node
      .append('title')
      .text((d) => {
        const n = d as Node
        return `${n.label} (${n.type})\n` +
          (n.status ? `Status: ${n.status}\n` : '') +
          `ID: ${n.id}`
      })

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => (d.source as any).x)
        .attr('y1', (d: any) => (d.source as any).y)
        .attr('x2', (d: any) => (d.target as any).x)
        .attr('y2', (d: any) => (d.target as any).y)

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
    })

    return () => {
      simulation.stop()
    }
  }, [data])

  return (
    <Card className="h-full">
      <CardTitle>Topology</CardTitle>
      {loading ? (
        <div className="flex items-center justify-center h-[200px] text-[var(--muted)]">
          Loading topology...
        </div>
      ) : !data ? (
        <div className="flex items-center justify-center h-[200px] text-[var(--muted)]">
          No topology snapshot
        </div>
      ) : (
        <>
          <svg
            ref={svgRef}
            className="w-full flex-1 min-h-0"
            style={{ display: 'block' }}
          />
          {lastTs && (
            <p className="text-[10px] text-[var(--muted)] mt-1">
              Updated {formatDate(lastTs)}
            </p>
          )}
        </>
      )}
    </Card>
  )
}
