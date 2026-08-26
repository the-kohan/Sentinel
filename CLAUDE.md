# Project Map: Sentinel

## Conceptual Foundation
God-mode network guard for Kohan's local infrastructure — passive surveillance + active alerting for Docker service mesh and host PC network. Answers continuously: *What is touching my stuff, and is it supposed to?*
- [[Network Topology Mapping]] -> Real-time container-to-container traffic, exposed ports, host NIC activity
- [[Anomaly Detection]] -> Rule-based + statistical + LLM-assisted baseline deviation detection
- [[Operator-In-The-Loop]] -> Sentinel recommends, never applies. Kohan decides every action.

## Execution Flow
[[01_Collection]] -> [[02_Correlation_Analysis]] -> [[03_Alert_Generation]] -> [[04_Interface]] -> [[05_Operator_Action]]

## Project Directory
- **[[01_Collection]]**: Docker Watcher (socket API), Host Network Watcher (ss, conntrack, arp), optional pcap (v2)
- **[[02_Correlation_Analysis]]**: LangChain agent + Ollama (local LLM) — baseline modeling, anomaly detection, query interpretation
- **[[03_Alert_Generation]]**: Context-rich alerts with source reputation memory, mute lists
- **[[04_Interface]]**: WhatsApp / TUI / Web UI / API — operator queries, answers, alerts, recommendations
- **[[05_Operator_Action]]**: Recommendation logs, operator acknowledgments, allowlist updates
- **[[06_System]]**: FastAPI backend, TimescaleDB/Postgres, pgvector, Redis, docker-compose
- **[[07_Skills]]**: Detection rules, query parsers, reputation heuristics
- **[[08_Iteration_Logs]]**: Incident history, rule tuning, baseline evolution
- **[[Attachments]]**: Schema SQL, docker-compose, service files, logs
- **src/**: Python source (FastAPI, collectors, agent)
- **sentinel/**: Package root
- **venv/**: Virtual environment

## Critical Docs
- [[CLAUDE]] — Prime Directive
- [[COMMANDS]] — CLI and API reference
- [[SENTINEL.md]] — Living spec (417 lines, full architecture, tech stack, data models)
- [[init_schema.sql]] — TimescaleDB schema
- [[known-good.md]] — Baseline topology snapshots
- [[seed_allowlist.sql]] — Initial allowlist

## Prime Directive
If a session is drifting without improving detection accuracy or reducing false positives, nudge back toward refining baselines and rules — not adding collection sources.

## Core Questions (Definition of Done)
Sentinel must answer all six cleanly:
1. *What is currently pinging `[service/container/IP]`?*
2. *What has `[container X]` talked to in the last N minutes?*
3. *Did anything new appear in the last hour that wasn't here yesterday?*
4. *Is `[host/service]` behaving normally vs. its baseline?*
5. *Show me everything from `[source IP/MAC]`.*
6. *Anomaly digest — what's weird right now?*

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│ INTERFACE LAYER                                     │
│ WhatsApp / TUI / Web UI / API — queries, answers,  │
│ alerts + recommendations                            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│ CORRELATION & ANALYSIS LAYER                        │
│ LangChain agent + Ollama (local LLM)                │
│ - Baseline modeling (what "normal" looks like)      │
│ - Anomaly detection (rule + statistical + LLM)      │
│ - Natural-language query interpretation             │
│ - Alert generation with context                     │
│ - Source reputation memory (operator acks)          │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│ COLLECTION LAYER                                    │
│ ┌────────────┬──────────────┬──────────────────┐   │
│ │ Docker     │ Host Network │ Optional Pcap    │   │
│ │ Watcher    │ Watcher      │ (off by default) │   │
│ │ (socket)   │ (ss,conntrack,│ (v2 opt-in)      │   │
│ │            │ arp,ip neigh) │                  │   │
│ └────────────┴──────────────┴──────────────────┘   │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│ STORAGE LAYER                                       │
│ TimescaleDB/Postgres — events, flows, baselines,   │
│ incidents, topology_snapshots, allowlist           │
│ pgvector (same DB) — similarity search, reputation  │
│ Redis — hot ring buffer, session state, mute list   │
└─────────────────────────────────────────────────────┘
```

## Tech Stack (Locked)
| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python | Primary |
| Backend | FastAPI | Async, plays nice with collectors |
| LLM | Ollama (local) | Local-first, no cloud leak |
| Agent | LangChain | Already in stack |
| Time-series DB | TimescaleDB/Postgres | Native hypertables, SQL |
| Vector | pgvector | Same DB, no extra infra |
| Hot buffer | Redis | Sub-ms ring buffer, TTL |
| Container API | Docker socket | Native, no agents |
| Host metrics | `ss`, `conntrack`, `arp` | Standard, no deps |

## Scope (v1)
| Domain | What Sentinel Watches | Data Source |
|--------|----------------------|-------------|
| **Docker mesh** | Container-to-container traffic, exposed ports, who pings which service, DNS lookups | Docker socket API, container netns, `/proc`/ns |
| **Host PC network (WSL2)** | NIC traffic, listening ports, outbound connections, ARP table, active sessions | `ss`, `conntrack`, `arp`, container state |
| **TBD (v2)** | LAN-wide, VPS, Pi cluster, router-level | Deferred |

**Explicitly out of scope for v1:** Acting on threats. Sentinel *reports*. Kohan decides.
**Explicitly out of scope, period:**
- Payload capture or DLP. Metadata only. Ever.
- Automatic iptables writes. Recommendations only. Non-negotiable.
- Multi-host. One Sentinel, one host. v3+ problem.

## Data Models (from SENTINEL.md §7)

### Events Table (TimescaleDB hypertable)
- `ts` (timestamptz), `src_ip`, `dst_ip`, `src_port`, `dst_port`, `proto`, `bytes`, `direction`, `container_id`, `host_interface`, `event_type`

### Flows Table (aggregated)
- 5-min rollups: `src_ip`, `dst_ip`, `proto`, `byte_count`, `packet_count`, `first_seen`, `last_seen`, `container_pair`

### Baselines Table
- `entity_id` (IP/container), `metric` (bytes/sec, conn_count, unique_peers), `p50`, `p95`, `p99`, `window_start`, `window_end`

### Incidents Table
- `id`, `ts`, `type` (new_peer, volume_spike, port_scan, dns_anomaly, baseline_deviation), `severity`, `context_json`, `status` (open, acked, resolved, false_positive), `operator_notes`

### Topology Snapshots
- Hourly: `snapshot_id`, `ts`, `containers_json`, `ports_json`, `connections_json`

### Allowlist
- `id`, `cidr`, `port`, `proto`, `container_label`, `reason`, `added_by`, `added_at`, `expires_at` (nullable)

### Source Reputation (pgvector)
- `ip`, `embedding` (behavior pattern), `ack_count`, `false_positive_count`, `last_seen`, `tags`

## Key People
- Kohan — Sole operator, architect, executor of all actions

## Dev Commands
```bash
cd "D:/Neural Core Engine/03 Projects/Sentinel"
# Database
docker-compose up -d timescaledb redis
psql -h localhost -U sentinel -d sentinel -f init_schema.sql
psql -h localhost -U sentinel -d sentinel -f seed_allowlist.sql

# Backend
source venv/bin/activate
python -m sentinel.api.main        # FastAPI on :8080
python -m sentinel.collectors.docker_watcher
python -m sentinel.collectors.host_watcher
python -m sentinel.agent.correlator

# CLI
python -m sentinel.cli query "what pinged redis in last 10m"
python -m sentinel.cli anomalies --since 1h
python -m sentinel.cli allowlist add 10.0.0.0/8 --reason "internal mesh"
```

## Rules & Conventions
- **(C) prefix** — Files created by Claude are prefixed with `(C)` so it's clear they're AI-generated.
- **Editing rule** — Before editing any file without the `(C)` prefix, ask for permission first.
- **Skills** — Detection rules, query parsers, reputation heuristics saved as markdown in Skills folder.
- **Local-first** — Non-negotiable. No cloud telemetry, no external APIs for core detection.
- **Operator-in-the-loop** — Sentinel recommends, never applies. All actions require Kohan approval.
- **Metadata only** — Never capture payloads. Headers, flow metadata, DNS queries only.
- **Baseline-driven** — Anomaly detection requires established baseline (min 24h data).
- **Reputation memory** — Operator acknowledgments feed source reputation embeddings (pgvector).
- **TimescaleDB hypertables** — All time-series data uses hypertables with appropriate chunk intervals.
- **Redis TTL** — Hot buffer entries expire at 1h; session state at 24h.

## Current Status
> **Last updated:** 2026-08-08
> **Status:** Planning complete (SENTINEL.md v1 spec locked). Schema SQL written. Docker compose defined. Collectors and FastAPI scaffold in `src/`. Not yet running. Logs show previous test runs (`sentinel-api.log`, `sentinel-core.log`).

## Existing Files
- `init_schema.sql` — TimescaleDB schema (events, flows, baselines, incidents, topology, allowlist)
- `seed_allowlist.sql` — Initial allowlist entries
- `known-good.md` — Baseline topology reference
- `SENTINEL.md` — Full 417-line living spec
- `sentinel-api.service` / `sentinel-core.service` — systemd unit files
- `src/` — Python package structure
- `venv/` — Virtual environment with dependencies

## Next Steps
1. Verify TimescaleDB + Redis containers start cleanly
2. Run schema initialization and seed allowlist
3. Start collectors (Docker watcher, Host watcher) in background
4. Start FastAPI backend and verify `/health` endpoint
5. Test CLI queries against live data
6. Build first baseline (24h collection)
7. Implement correlator agent with Ollama
8. Add WhatsApp alert delivery (Baileys integration)
9. Build Web UI dashboard (FastAPI + static HTML/JS)