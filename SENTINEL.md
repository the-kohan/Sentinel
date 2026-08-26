# SENTINEL.md — God-Mode Network Guard

<!--
Living spec. Distilled from planning sessions on 2026-06-03.
PLANNING ONLY. No code, no commits, no execution.
-->

---

## 0. Mission Statement

**Sentinel** watches Kohan's local networks — Docker service mesh and host PC — for inbound/outbound pings, connection attempts, and unusual activity. It answers one question, continuously:

> *What is touching my stuff, and is it supposed to?*

- **Operator:** Kohan (sole)
- **Posture:** Passive surveillance + active alerting. Not a firewall. Not a blocker. An eye that doesn't blink.
- **Local-first:** Non-negotiable. Per stack rule.
- **Executor of any action:** Kohan. Always. Sentinel recommends, never applies.

---

## 1. Scope (v1)

| Domain | What Sentinel Watches | Data Source |
|---|---|---|
| **Docker mesh** | Container-to-container traffic, exposed ports, who is pinging which service, DNS lookups by containers | Docker socket API, container netns, `/proc`/ns |
| **Host PC network** (WSL2) | NIC traffic, listening ports, outbound connections, ARP table, active sessions | `ss`, `conntrack`, `arp`, container state |
| TBD (v2) | LAN-wide, VPS, Pi cluster, router-level | Deferred |

**Explicitly out of scope for v1:** Acting on threats. Sentinel *reports*. Kohan decides.

**Explicitly out of scope, period:**
- Payload capture or DLP. Metadata only. Ever.
- Automatic iptables writes. Recommendations only. Non-negotiable.
- Multi-host. One Sentinel, one host. v3+ problem.

---

## 2. Core Questions (Definition of Done)

If Sentinel can't answer all six cleanly, it's not done:

1. *What is currently pinging `[service/container/IP]`?*
2. *What has `[container X]` talked to in the last N minutes?*
3. *Did anything new appear in the last hour that wasn't here yesterday?*  *(promoted to first-class feature — see §9)*
4. *Is `[host/service]` behaving normally vs. its baseline?*
5. *Show me everything from `[source IP/MAC]`.*
6. *Anomaly digest — what's weird right now?*

---

## 3. Architecture (Conceptual Layers)

```
┌─────────────────────────────────────────────────────┐
│ INTERFACE LAYER │
│ WhatsApp / TUI / Web UI / API — operator queries, │
│ Sentinel answers + alerts + recommends │
└──────────────────┬──────────────────────────────────┘
 │
┌──────────────────▼──────────────────────────────────┐
│ CORRELATION & ANALYSIS LAYER │
│ LangChain agent + Ollama (local LLM) │
│ - Baseline modeling (what "normal" looks like) │
│ - Anomaly detection (rule + statistical + LLM) │
│ - Natural-language query interpretation │
│ - Alert generation with context │
│ - Source reputation memory (operator acknowledgments) │
└──────────────────┬──────────────────────────────────┘
 │
┌──────────────────▼──────────────────────────────────┐
│ COLLECTION LAYER │
│ ┌────────────┬──────────────┬──────────────────┐ │
│ │ Docker │ Host Network │ Optional Pcap │ │
│ │ Watcher │ Watcher │ (off by default)│ │
│ │ (socket) │ (ss,conntrack,│ (v2 opt-in per │ │
│ │ │ arp,ip neigh) │ interface) │ │
│ └────────────┴──────────────┴──────────────────┘ │
└──────────────────┬──────────────────────────────────┘
 │
┌──────────────────▼──────────────────────────────────┐
│ STORAGE LAYER │
│ TimescaleDB/Postgres — events, flows, baselines, │
│ incidents, topology_snapshots, allowlist │
│ pgvector (same DB) — similarity search, reputation │
│ Redis — hot ring buffer, session state, mute list │
└─────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack (Locked to Operator Defaults)

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Primary |
| Backend | FastAPI | Async, plays nice with collectors |
| LLM | Ollama (local) | Local-first, no cloud leak |
| Agent | LangChain | Already in stack |
| Database | PostgreSQL + TimescaleDB | Time-series native |
| Vector store | pgvector (same Postgres) | One DB, one pool, no extra infra |
| Cache / ring buffer | Redis | Already in stack |
| Host watcher | `ss`, `conntrack`, `arp`, `ip neigh` | Read-only, no NIC touching |
| Docker watcher | Docker Engine API (socket) | First-party |
| Optional pcap | `tcpdump` + scapy | **Off by default in v1** — opt-in per interface, off-limits inside WSL2 |
| Notifications | WhatsApp (OpenClaw) → TUI (Rich) → Web (v2) | Operator lives in WhatsApp |
| Containerization | Docker — for Sentinel **itself** we use systemd | See §6 |
| CI | GitHub Actions | Already in stack |

**Explicitly NOT using:** Any cloud SIEM, any SaaS, anything that phones home.

---

## 5. Data Model (Conceptual)

```
events
  - ts, source (docker|host|pcap), src_ip, src_port,
    dst_ip, dst_port, proto, direction, bytes,
    container_id?, service_name?, raw

flows (aggregated)
  - window_start, src, dst, count, bytes_avg, deviation_score

baselines
  - entity (container|host|port|service), metric,
    mean, stddev, sample_count, last_updated

incidents
  - opened_ts, closed_ts, severity, summary,
    related_events[], llm_assessment,
    operator_acknowledged (bool + ts + note),
    recommended_action (text)

known_good (allowlist)
  - pattern, source, reason, added_ts,
    added_by ('operator' | 'observation_48h'),
    expiry (null for static services)

topology_snapshots
  - snapshot_ts, listening_ports[], containers[],
    arp_table[], mac_addrs[], diff_against_previous (jsonb)

source_reputation
  - ip_or_subnet, first_seen, last_seen, contact_count,
    operator_verdict ('benign' | 'unknown' | 'suspicious'),
    note, last_updated

operator_actions
  - ts, action_text, source ('manual_paste' | 'history_scrape'),
    context_incident_id?

mute_window
  - target (service|ip|port|container),
    muted_until_ts, reason
```

The allowlist is critical — without it Sentinel screams about every health check and Docker DNS ping.

---

## 6. Runtime & Deployment

| Decision | Choice |
|---|---|
| **Where it runs** | WSL2 host itself (confirmed: `systemd=true` in `/etc/wsl.conf`, systemd 259, system `running`) |
| **What form** | Bare-metal systemd service, NOT containerized |
| **Why not Docker** | Needs read access to Docker socket, host `/proc`, and `ss`/`conntrack` output. Containerizing costs more than it saves. |
| **Writes to network** | **None.** No iptables, no nftables, no `tc`. Read-only or it doesn't ship. |

**Why this is safe:** Sentinel has no network-modification paths. Worst it can do is fill a disk or a log file — both monitored by a watchdog. **It is structurally incapable of breaking the network it watches.**

---

## 7. Build Phases (Sequence Only — No Dates)

| Phase | Output | Exit Criteria |
|---|---|---|
| **P0 — Lock the perimeter** | Decide what "TBD" becomes. Document current Docker + host layout. Build the known-good allowlist manually. | Operator can point at any service and say "this is mine, this is the noise, this is suspect." |
| **P0.5 — Observe** | Run collection layer in silent mode for 48h. Generate a candidate allowlist from observed traffic. Operator reviews and promotes to `known_good`. | DB-backed allowlist populated with vetted entries. |
| **P1 — Collect** | Three watchers running: Docker socket, host (ss/conntrack/arp), optional pcap. All events into Postgres. | `SELECT count(*) FROM events WHERE ts > now() - interval '1 hour'` returns a believable number. |
| **P2 — Ask** | FastAPI + LangChain agent on top of the event store. NLQ via WhatsApp. | Operator can ask "what pinged cipher-bot in the last 10 minutes" and get a real answer. |
| **P3 — Baseline** | Rolling 7-day window per entity. Mean/stddev for traffic volume, peer count, port set. Daily `topology_snapshots`. | Baseline table populating. Deviation score computable. Diff against yesterday's topology returns useful results. |
| **P4 — Anomaly** | Rule engine (new source IP, new port, off-hours, volume spike, **container drift = highest priority**) + LLM-judged severity. | Incidents table populating. Operator is getting pings they actually want. |
| **P5 — Interface** | WhatsApp alerts + TUI dashboard (Rich) + operator commands. | Operator can check Sentinel from phone while away. |
| **P6 — Harden** | Systemd unit, log rotation, disk caps, watchdog (Sentinel watches itself), quiet-hours profile, mute-window command. | Runs unattended for a week without intervention. |

---

## 8. Key Design Decisions (Decided 2026-06-03)

| Decision | Choice |
|---|---|
| Scope v1 | Docker mesh + Host PC only. Third domain (TBD) deferred to v2. |
| Runtime | Bare-metal systemd in WSL2. |
| Storage | Single PostgreSQL: TimescaleDB + pgvector. Redis for hot ring buffer only. |
| Outbound monitoring | In scope. |
| Pcap in v1 | **Off by default.** Read-only via `ss`/`conntrack`/`arp`/`ip neigh` first. |
| iptables writes | **Banned.** Recommendations only. |
| LLM use | Triage incidents only. Never raw events. Batched. Cost ceiling enforced. |
| Allowlist mechanism | DB-backed. Seeded by 48h observation mode in P0.5. Static entries never expire. |
| Alerting priority order | WhatsApp → TUI → Web UI (Web = v2). |
| Retention | 30 days compressed, then drop. Topology snapshots: 90 days. |
| Top-priority anomaly rule | **Container drift.** A new container on `kohana` is *always* alerted on, regardless of quiet hours. |
| Timezone | Store UTC. Display EAT. Conversion at query/display time only. |
| Watcher failure mode | **Alert on failure, never silent.** If a watcher dies, that's a P5 incident. |
| Operator auth | Token-based from day one. Single operator, single token. Stored in env, not config. |
| Service naming | Canonical = container name (Docker) ∪ process name (host). NLQ maps user input through this. |
| Source reputation | Persistent across restarts. Operator can mark an IP "benign" with a note; future contacts are downgraded. |

---

## 9. First-Class Features (v1)

These were promoted from the v2 backlog during planning. Without them, the system is *technically* complete but *practically* useless.

### 9.1 Quiet Hours Profile

- Default schedule: 18:00–08:59 EAT Mon–Fri, all weekend.
- Suppresses: P3-P4 informational alerts.
- Always-on regardless of hour: P5 severity (active probing, known-bad source, exfiltration patterns, **container drift**).
- Configurable via WhatsApp command: `/quiet 22 8` (start hour, end hour, 24h format).
- Toggle: `/quiet off` to disable entirely.

### 9.2 Operator Self-Deafen (`/mute`)

- Use case: operator is restarting a service, running a security scan, installing a package.
- Command: `/mute <CONTAINER_NAME> 30m` or `/mute <LAN_IP> 1h` or `/mute container:<SERVICE_NAME> 5m`.
- Suppresses alerts on the target for the window.
- Logged in `mute_window` table for audit.
- Auto-expires. Never permanent.
- If an event matches *both* a mute and a P5 rule, P5 wins.

### 9.3 Container Drift = Highest Priority Rule

- Triggers when: a container appears on `kohana` that wasn't in the most recent `topology_snapshot`.
- Severity: P5 (always alerts, ignores quiet hours).
- Alert content: container name, image, joined timestamp, what it's connected to, full port bindings.
- Rationale: cheap to detect, highest signal, hardest to false-positive, single most useful alert Sentinel will ever produce.
- The only way to suppress: pre-register the container in the allowlist (planned deployment) or use `/mute` for the deployment window.

### 9.4 Topology Diff ("Show me the diff")

- Daily `topology_snapshots` written at 00:00 EAT (and on any change event).
- Stored 90 days.
- Powers Q3: "did anything new appear that wasn't here yesterday?"
- Powers Q5: "show me everything from [IP]" — joins events against snapshot for context.

---

## 10. v2 Backlog (Logged — Not in v1)

Promoted from planning discussions. These are real features, just deferred so v1 ships.

| # | Feature | Reason deferred |
|---|---|---|
| B1 | **GeoIP for inbound** — MaxMind GeoLite2 (free, local DB), single SQL join, "where is this traffic from geographically?" | Cheap, but needs DB import. Not a v1 blocker. |
| B2 | **Weekly digest** — Sunday 09:00 EAT summary: events, anomalies, top talker, noisiest hour, anything new | Notification engineering, not core surveillance |
| B3 | **Source reputation dashboard / review** — UI for re-classifying marked-benign sources | Needs Web UI; v2 |
| B4 | **Operator action log via shell history scraping** — auto-capture what operator actually ran | Privacy/ergonomics design, not v1 |
| B5 | **"I'm leaving" mode** — escalation toggle for travel/away periods | UX layer on top of quiet hours |
| B6 | **Threat intel feed opt-in** — AbuseIPDB / Emerging Threats / Spamhaus drop lists (locally-runnable) | Adds data dependency, deferred |
| B7 | **ML-based anomaly detection** | Weeks of tuning, false-positive hell, v3+ |
| B8 | **TBD third domain** (LAN-wide / VPS / Pi cluster / router-level) | Scope, not feature |
| B9 | **Web UI** | Distinct project, v2 |
| B10 | **Multi-host orchestration** | Sentinel becomes a different product; v3+ |
| B11 | **Per-interface opt-in pcap** | Use case unclear for v1; revisit when payload data is actually needed |
| B12 | **Container network policy suggestions** | Adjacent to "iptables recommendations" but Docker-scoped |

---

## 11. Risks & Watch-outs

| Risk | Mitigation |
|---|---|
| Sentinel gets noisy on Docker's internal DNS chatter | Allowlist seed phase in P0.5. systemd-resolved (`127.0.0.53`, `127.0.0.54`) and WSL2 DNS (`<WSL2_DNS_IP>`) are first entries. |
| PCAP disk fills the drive | Off by default. If enabled, ring buffer + TimescaleDB compression from day one. |
| Watching yourself recursively (Sentinel's own Docker traffic) | N/A — Sentinel runs as systemd, not a container. It cannot see itself as a container because it isn't one. |
| Ollama cold-start kills query latency | Keep model warm. Smaller model for incident classification, larger for NLQ. |
| Privacy if logs are ever shared | Never log payloads. Only metadata. Ever. |
| Watcher dies silently | Failure mode = P5 incident. Alerts on heartbeat miss. |
| WSL2 networking is virtualized and fragile | Read-only operations only. No iptables. No NIC-level capture. Conntrack and ss are the ceiling in WSL2. |
| Init-ollama is Exited, not a problem | Allowlist "Exited-but-expected" status. Don't flag one-shot containers. |
| Two Redis processes confusion (resolved 2026-06-03) | One host Redis purged. Container Redis remains as the app-stack one. |

---

## 12. Definition of Done (v1)

v1 ships when:

- [ ] All six core questions (§2) answerable via WhatsApp
- [ ] Allowlist seeded from 48h observation (P0.5 complete)
- [ ] Container drift rule firing on a test deployment
- [ ] Quiet hours + `/mute` working
- [ ] Topology diff queryable
- [ ] Source reputation persistent
- [ ] One week of unattended operation with no manual intervention
- [ ] Weekly digest NOT required for v1 (logged as v2)

## Current Stack Snapshot — 2026-06-03

**Host:** WSL2 Ubuntu, `eth0 = 172.30.109.122/20`, gateway `172.30.96.1`. Loopback services only on `127.0.0.1`.

**Docker network topology:**
- One user-defined network: **`kohana`** (bridge driver). All services attach here. This is the mesh Sentinel will watch.
- Default `bridge`, `host`, `none` also present but unused by stack.

**Running containers (11 total, all on `kohana` network):**

| Container | Image | Port (host) | Purpose |
|---|---|---|---|
| `n8n` | n8nio/n8n | 127.0.0.1:5678 | Workflow automation |
| `redis` | redis | (internal only) | Cache / queue |
| `postgres` | pgvector/pgvector:pg16 | 127.0.0.1:5432 | Primary DB + vector |
| `ollama` | ollama/ollama | 127.0.0.1:11434 | Local LLM server |
| `init-ollama` | ollama/ollama | — | One-shot model puller (Exited) |
| `qdrant` | qdrant/qdrant | 127.0.0.1:6333, 6334 | Vector store |
| `stirling-pdf` | stirlingtools/stirling-pdf | 127.0.0.1:8080 | PDF tooling |
| `crawl4ai` | unclecode/crawl4ai | 127.0.0.1:11235 | Web crawler |
| `minio` | minio/minio | 127.0.0.1:9000, 9001 | S3-compatible storage |
| `faster-whisper` | fedirz/faster-whisper-server | 127.0.0.1:8000 | Speech-to-text |
| `searxng` | searxng/searxng | 127.0.0.1:8081 | Meta search |

**Notes for Sentinel:**
- Every port is bound to `127.0.0.1` only — host is not exposed to LAN/internet. External attack surface = none.
- All container-to-container traffic goes over the `kohana` bridge network. Sentinel should watch this bridge interface, not `eth0`.
- `init-ollama` is a one-shot. Exited 12h ago. Should be expected to stay Exited — not an anomaly.
- `redis` is internal-only (no host port mapping) — only reachable from other containers on `kohana`.

**Other listening services on host (not in Docker):**
- `127.0.0.1:18789` — OpenClaw gateway (or similar). Loopback only.
| `127.0.0.54:53`, `127.0.0.53:53` — systemd-resolved stub resolvers. High traffic, must be in allowlist. |
| `<WSL2_DNS_IP>:53` — likely WSL2 internal DNS resolver. Same deal. |

---

## Communication Channel

- **Primary interface:** WhatsApp (via OpenClaw)
- **TUI:** Rich-based, for terminal sessions
- **Webchat:** webchat (this session)

---

## Sentinel — Decisions Locked (2026-06-03)

Full spec: `SENTINEL.md`. Snapshot of the locked decisions:

| Decision | Choice |
|---|---|
| Scope v1 | Docker mesh + Host PC only. Third domain (TBD) deferred to v2. |
| Runtime | Bare-metal systemd service in WSL2. Confirmed: `systemd=true`, systemd 259, running. |
| Storage | Single PostgreSQL: TimescaleDB + pgvector. Redis for hot ring buffer only. |
| Outbound monitoring | In scope. |
| Pcap | **Off by default in v1.** `ss`/`conntrack`/`arp`/`ip neigh` only. |
| iptables writes | **Banned.** Recommendations only. Sentinel cannot modify the network. |
| Packet capture | Off by default. `ss`/`conntrack`/`arp` for v1; pcap is opt-in per interface, off-limits inside WSL2. |
| LLM use | Triage incidents only. Never raw events. Batched with cost ceiling. |
| Allowlist mechanism | DB-backed, seeded by 48h observation mode in P0.5. |
| Alerting priority order | WhatsApp → TUI → Web UI (Web = v2). |
| Retention | 30 days compressed, then drop. Topology snapshots: 90 days. |
| Container drift | Highest-priority rule. Always alerts, ignores quiet hours. |
| Timezone | Store UTC, display EAT. |
| Watcher failure mode | Alert on failure, never silent. P5 incident on heartbeat miss. |
| Operator auth | Token-based from day one. Single operator, single token. |
| Service naming | Canonical = container name ∪ process name. |
| Source reputation | Persistent. Operator "benign" verdicts downgrade future contacts. |
| Quiet hours | 18:00–08:59 EAT Mon–Fri + all weekend. P3-P4 suppressed. P5 always fires. |
| Self-deafen | `/mute <target> <duration>` command. Auto-expires. P5 wins over mute. |

**First-class v1 features (promoted from v2 backlog):** quiet hours, `/mute` self-deafen, container-drift top rule, topology diff.

**v2 backlog:** GeoIP (B1), weekly digest (B2), source reputation dashboard (B3), shell history scraping (B4), "I'm leaving" mode (B5), threat intel feeds (B6), ML anomaly detection (B7), third domain (B8), Web UI (B9), multi-host (B10), per-interface pcap (B11), container network policy suggestions (B12).

**Still open (carry to P0.5/P1):**
- 48h observation mode → seed allowlist (P0.5)
- Operator auth implementation details
- Service naming taxonomy for NLQ (canonical list)
- Initial topology_snapshot baseline

**Resolved 2026-06-03:**
- Host Redis purged via `systemctl disable --now redis-server` + `apt remove redis-server`. Container `redis` is now the sole instance.

---

## Lessons / Patterns

- **Always check memory + verify live state before answering.** USER.md rule: never assume data exists from a prior check.
- **Ollama Access:** Ollama is NOT installed locally on the host. All interactions must be routed through Docker.
  - Use: `docker exec ollama ollama <command>`
  - Do not attempt to run `ollama` as a standalone binary.
- **`n8n-mcp`** was deleted on 2026-06-02 per explicit operator request. Do not recreate.
- **WhatsApp send on webchat session** requires channel + target params; main session doesn't have a default source.
- **Sentinel's structurally safe design** is load-bearing. No iptables, no NIC capture, no Docker network modifications. The whole point is that it *cannot* break the network it watches. Don't compromise this in any future iteration without serious thought.
- **WSL2 networking traps:** packet capture on `eth0` or iptables writes can blackhole WSL2's NAT path. Always read-only. `ss`/`conntrack` are the ceiling.

---

## Open Items / Backlog

- [x] Write `SENTINEL.md` to workspace with locked decisions — done 2026-06-03 11:59
- [ ] Sentinel P0.5: 48h observation mode → seed allowlist
- [ ] Operator auth model for Sentinel API (token storage location)
- [ ] Canonical service naming list (container name + process name registry)
- [ ] Initial `topology_snapshot` baseline
- [ ] Memory search embedding quota — top up or switch provider
- [ ] WhatsApp channel "allowlist" — operator needs to clarify target number(s)
- **Marker Protocol:**
  - `[TASK]` = Action items / Execution.
  - `[INFO]` = Context / Reference / Knowledge.
---

*Spec version: 0.3 — first complete draft*
*Last updated: 2026-06-03 11:59 EAT*
*Next review: after P0 work begins*
