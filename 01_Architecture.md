# 01 Architecture — As Built

> **Source:** Live inspection of `E:\kohanastack\sentinel\` + Docker container `sentinel`  
> **Purpose:** Rebuild the exact running system, not the original plan.

---

## Actual Data Flow

```text
┌─────────────────────────────────────────────────────┐
│ SENTINEL CONTAINER (kohanastack-sentinel)            │
│  Port: 127.0.0.1:8100 → 8100                        │
│  CMD: uvicorn src.analyzer:app --host 0.0.0.0 --port 8100 │
└──────────────────┬──────────────────────────────────┘
                   │
     ┌─────────────┴─────────────┐
     │                           │
     ▼                           ▼
/var/run/docker.sock (ro)   ./collector-data → /data/collector (rw)
     │                           │
     ▼                           ▼
_docker_client             host-ss.json
(docker-py)                (from host collector)
     │                           │
     └─────────────┬─────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ analyzer.py     │
         │ SentinelAnalyzer│
         │ run_loop() 60s  │
         └────────┬────────┘
                  │
          ┌───────┴───────┐
          │               │
          ▼               ▼
     check_docker_  check_host_
     drift()         anomalies()
          │               │
          │               │
          ▼               ▼
     P5 alert        P3 alert
     (never          (suppressible)
      suppressed)         │
          │               │
          └───────┬───────┘
                  │
                  ▼
          ┌─────────────────┐
          │ notifier.py     │
          │ SentinelNotifier│
          └────────┬────────┘
                   │
          ┌────────┴────────┐
          │                 │
          ▼                 ▼
  OpenClaw webhook      Telegram fallback
  POST /hooks/sentinel  direct curl
  (currently 404)       (token present but likely placeholder)
          │                 │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ postgres:5432   │
          │ schema: sentinel_db │
          └─────────────────┘
```

---

## Component Inventory

| Component | File | Role | Status |
|---|---|---|---|
| FastAPI app + background loop | `src/analyzer.py` | Canonical service on :8100 | ✅ Running |
| DB access | `src/db.py` | Postgres queries, JSONB wrapping | ✅ Connected |
| Alert delivery | `src/notifier.py` | Webhook + Telegram fallback | ⚠️ Webhook 404 |
| Observer | `observer.py` | Appends to JSONL every 60s | ✅ Running |
| Host collector | `collectors/host_collector.py` | Standalone `ss`/`ip neigh` parser | 📦 Not invoked by timer |
| Docker collector | `collectors/docker_collector.py` | Standalone Docker snapshot | 📦 Not used by analyzer |

---

## Cycle Behavior (Actual)

- **Every 60 seconds:**
  1. `_get_docker_containers()` — direct Docker socket read
  2. `check_docker_drift()` — P5 alert + DB insert + topology save
  3. `_get_host_data()` — read `host-ss.json`
  4. `check_host_anomalies()` — allowlist check + P3 alert + candidate insert
  5. Every 60th cycle: `save_topology()` hourly snapshot

---

## Known Design Constraints (As Built)

- **No network writes.** Sentinel cannot break the network it watches.
- **Metadata only.** No payload capture.
- **P5 never suppressed.** Container drift ignores quiet hours and mute.
- **P3 suppressible.** By quiet hours or mute window.
- **Single host.** One Sentinel instance, one Postgres DB.
