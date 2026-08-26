# 04 Source Files — As Built

> **Source:** Live files in `E:\kohanastack\sentinel\src\`, `collectors\`, `sentinel\`  
> **Purpose:** Exact code inventory to recreate the project.

---

## Directory Structure

```
E:\kohanastack\sentinel\
├── Dockerfile
├── requirements.txt
├── init_schema.sql
├── seed_allowlist.sql
├── observer.py
├── known-good.md
├── src/
│   ├── __init__.py
│   ├── analyzer.py      # Canonical FastAPI app + background loop
│   ├── api.py           # Legacy standalone API (not deployed)
│   ├── db.py            # Postgres access layer
│   ├── notifier.py      # Alert delivery
│   └── main.py          # Legacy core loop (not deployed)
├── collectors/
│   ├── docker_collector.py
│   └── host_collector.py
└── sentinel/
    ├── __init__.py
    ├── sentinel.env
    └── scripts/
        ├── alert.sh
        ├── db.sh
        └── sentinel.sh
```

---

## File Inventory

| File | Role | Deployed? |
|---|---|---|
| `src/analyzer.py` | FastAPI app + `SentinelAnalyzer` background loop | ✅ Yes — runs on :8100 |
| `src/db.py` | `SentinelDB` class — connects to `postgres:5432/Kohan` | ✅ Yes |
| `src/notifier.py` | `SentinelNotifier` — OpenClaw webhook + Telegram fallback | ✅ Yes |
| `src/api.py` | Legacy standalone API on port 8000 | ❌ Not deployed |
| `src/main.py` | Legacy core polling loop | ❌ Not deployed |
| `collectors/host_collector.py` | Standalone `ss`/`ip neigh` collector | 📦 Not invoked by timer |
| `collectors/docker_collector.py` | Standalone Docker collector | 📦 Not used by analyzer |
| `observer.py` | Observation watcher — appends to `observation_log.jsonl` | ✅ Actively running |
| `sentinel/scripts/alert.sh` | Direct Telegram router | 📦 Present |
| `sentinel/scripts/db.sh` | Postgres event logger | 📦 Present |
| `sentinel/scripts/sentinel.sh` | Legacy shell loop with circuit breaker | 📦 Present |

---

## Key Code Snippets

### `src/analyzer.py` — Main Loop

```python
async def run_loop(self):
    await self.initialize()
    while self.is_running:
        await self.run_cycle()
        await asyncio.sleep(60)  # 60 second cycle
```

```python
async def run_cycle(self):
    # 1. Docker snapshot
    current_docker = self._get_docker_containers()
    # 2. Drift detection (P5)
    if self.last_docker_snapshot:
        drift = self.check_docker_drift(current_docker, self.last_docker_snapshot)
    self.last_docker_snapshot = current_docker
    # 3. Host snapshot
    current_host = self._get_host_data()
    # 4. Anomaly detection (P3)
    if current_host:
        anomalies = self.check_host_anomalies(current_host)
    self.last_host_snapshot = current_host
    # 5. Hourly topology snapshot
    if self.cycle_count % 60 == 0:
        self.db.save_topology({...})
```

### `src/db.py` — JSONB Wrapper

```python
self.execute(query, (
    ...
    Json(event_data.get('raw_data')) if event_data.get('raw_data') is not None else None
))
```

### `src/notifier.py` — Alert Suppression

```python
def should_suppress(self, severity: str, target: str = None) -> bool:
    if severity == "P5":
        return False  # Never suppress P5
    if target and self.is_muted(target):
        return True
    if severity in ("P3", "P4") and self.is_quiet_hours():
        return True
    return False
```

### `src/analyzer.py` — Mute Endpoints

```python
@app.post("/mute")
async def mute_target(target: str, duration: str = "1h", reason: str = "operator mute")

@app.get("/mute")
async def list_mutes()

@app.delete("/mute/{target}")
async def unmute_target(target: str)
```

### `src/analyzer.py` — Topology Diff

```python
@app.get("/query/diff")
async def get_topology_diff(days: int = 1)
```

Returns: `new_containers`, `removed_containers`, `new_ports`, `removed_ports`, `new_arp_entries`

---

## observer.py — Observation Watcher

- Polls `/status`, `/query/anomalies`, `/query/drift`, `/query/candidates` every 60s
- Appends one JSON line per cycle to `observation_log.jsonl`
- Writes `observation_summary.json` after each cycle
- Supports `--once`, `--review`, `--interval` flags

---

## sentinel/sentinel.env

```properties
TELEGRAM_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
TELEGRAM_CHAT_ID=<YOUR_TELEGRAM_CHAT_ID>
POSTGRES_USER=Kohan
POSTGRES_PASSWORD=<YOUR_POSTGRES_PASSWORD>
POSTGRES_DB=sentinel_db
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
N8N_WEBHOOK=<YOUR_N8N_WEBHOOK_URL>
SENTINEL_ROOT=/mnt/d/kohanastack/sentinel
SENTINEL_HOOK_TOKEN=<YOUR_OPENCLAW_HOOK_TOKEN>
```

---

## CWD / Workspace

- Project root: `E:\kohanastack\sentinel\`
- Collector data: `E:\kohanastack\sentinel\collector-data\`
- Venv: `E:\kohanastack\sentinel\venv\` (Python 3.14)
