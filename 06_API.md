# 06 API — As Built

> **Source:** Live `src/analyzer.py`, `curl http://127.0.0.1:8100/*`  
> **Purpose:** Rebuild the exact API surface and responses.

---

## FastAPI App

**File:** `src/analyzer.py`  
**Runs on:** `0.0.0.0:8100` inside container, exposed as `127.0.0.1:8100`  
**Lifespan:** Creates `SentinelAnalyzer`, starts background `run_loop()`, cancels on shutdown

---

## Endpoints

### `GET /status`

Health check + live metrics.

```bash
curl http://127.0.0.1:8100/status
```

**Live response:**
```json
{
  "status": "active",
  "version": "v1.0-containerized",
  "db": "connected",
  "cycles_completed": 240,
  "last_docker_containers": 6,
  "last_host_ports": 18
}
```

---

### `GET /query/drift`

Latest topology snapshot from DB.

```bash
curl http://127.0.0.1:8100/query/drift
```

**Response:**
```json
{
  "latest_snapshot": {
    "id": 1,
    "snapshot_ts": "2026-08-24T14:00:00.000000+00:00",
    "listening_ports": null,
    "containers": null,
    "arp_table": null,
    "diff_against_previous": null
  }
}
```

---

### `GET /query/diff?days=1`

Topology diff — compares latest snapshot with one from N days ago.

```bash
curl "http://127.0.0.1:8100/query/diff?days=1"
```

**Response:**
```json
{
  "compared": "previous snapshot vs latest (interval: 1 day(s))",
  "new_containers": [...],
  "removed_containers": [...],
  "new_ports": [...],
  "removed_ports": [...],
  "new_arp_entries": [...],
  "total_new": 2
}
```

---

### `GET /query/anomalies?limit=10`

Recent host-origin events.

```bash
curl "http://127.0.0.1:8100/query/anomalies?limit=10"
```

**Live response:** `[]` (no host anomalies in events table, despite 750 total events)

---

### `GET /query/collectors`

Collector file freshness.

```bash
curl http://127.0.0.1:8100/query/collectors
```

**Live response:**
```json
{
  "host_collector": {
    "exists": true,
    "size": 2417,
    "age_seconds": 165638
  },
  "docker_collector": {
    "mode": "internal_docker_socket",
    "last_containers": 6
  }
}
```

---

### Mute Endpoints

```bash
# Create mute
POST /mute?target=<target>&duration=<dur>&reason=<text>
# Example:
curl -X POST "http://127.0.0.1:8100/mute?target=127.0.0.1:52878&duration=30m&reason=testing"

# List active mutes
curl http://127.0.0.1:8100/mute

# Remove mute
curl -X DELETE "http://127.0.0.1:8100/mute/127.0.0.1:52878"
```

**Duration format:** `30m`, `1h`, `2d`  
**Target formats:** `container:n8n`, `127.0.0.1:52878`, `192.168.1.100`

---

### Observation Endpoints

```bash
# List observation candidates
curl http://127.0.0.1:8100/query/candidates

# Promote candidate to permanent allowlist
curl -X POST "http://127.0.0.1:8100/promote?pattern=127.0.0.1:52878"

# Recent observation log
curl "http://127.0.0.1:8100/query/observation_log?limit=100"
```

---

## Legacy API

**File:** `src/api.py` — standalone FastAPI on port 8000 with deprecated `on_event("startup")`  
**Status:** ❌ Not deployed. The containerized `analyzer.py` on :8100 is canonical.

---

## Current API Status

| Endpoint | Status | Notes |
|---|---|---|
| `/status` | ✅ 200 | `cycles_completed: 240`, `last_docker_containers: 6` |
| `/query/drift` | ✅ 200 | Returns latest topology snapshot |
| `/query/diff` | ✅ 200 | Returns new/removed containers, ports, ARP |
| `/query/anomalies` | ✅ 200 | Currently empty `[]` |
| `/query/collectors` | ✅ 200 | `host_collector.exists: true`, age: 165638s |
| `/mute` (POST) | ✅ Working | Duration parsing, DB insert |
| `/mute` (GET) | ✅ Working | Lists active mutes |
| `/mute/<target>` (DELETE) | ✅ Working | Removes mute window |
| `/query/candidates` | ✅ Working | Returns observation candidates |
| `/promote` | ✅ Working | Promotes candidate to permanent |
| `/query/observation_log` | ✅ Working | Returns recent candidates |
