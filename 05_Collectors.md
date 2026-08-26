# 05 Collectors — As Built

> **Source:** Live `collectors/host_collector.py`, `collectors/docker_collector.py`, `observer.py`, and container mount inspection  
> **Purpose:** Rebuild the collection layer and observer.

---

## Host Collector

**File:** `collectors/host_collector.py`  
**Role:** Standalone script that runs `ss` and `ip neigh` on the WSL2 host, writes JSON to bind-mounted volume.

### Commands Run

1. `ss -tulpn` → listening ports
2. `ss -tun` → active connections
3. `ip neigh` → ARP/neighbor table

### Output Format

```json
{
  "timestamp": "2026-08-24T21:22:00Z",
  "listening_ports": {
    "5432": {"ip": "127.0.0.1", "process": "...", "protocol": "tcp"},
    "5678": {"ip": "127.0.0.1", "process": "...", "protocol": "tcp"}
  },
  "active_connections": [
    {"dst_ip": "127.0.0.53", "dst_port": 53, "proto": "udp", "local": "127.0.0.1:54321"}
  ],
  "arp_table": [
    {"ip": "192.168.1.1", "interface": "eth0", "mac": "aa:bb:cc:dd:ee:ff", "state": "REACHABLE"}
  ]
}
```

### Current Status

- `host-ss.json` exists at `E:\kohanastack\sentinel\collector-data\host-ss.json` (2,417 B)
- **Not currently invoked by a systemd timer**
- Read by `analyzer.py` via `_load_host_snapshot()` each cycle
- Last modified: 2026-08-24 21:22

---

## Docker Collector

**File:** `collectors/docker_collector.py`  
**Role:** Standalone script that queries Docker socket, writes JSON snapshot.

### Output Format

```json
{
  "timestamp": "2026-08-24T14:00:00Z",
  "containers": {
    "<container_id>": {
      "name": "n8n",
      "image": "n8nio/n8n:latest",
      "status": "running",
      "ports": {"5678/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5678"}]},
      "networks": ["kohana"],
      "created": "2026-08-24T12:00:00.000000Z",
      "labels": {}
    }
  }
}
```

### Current Status

- **Not used by analyzer.** Analyzer reads Docker socket directly via `docker-py`.
- Exists for bare-metal deployment path or archival snapshots.

---

## Observer Watcher

**File:** `observer.py`  
**Role:** External watchdog that polls Sentinel API every 60s and writes JSONL observation log.

### Output Files

| File | Purpose |
|---|---|
| `observation_log.jsonl` | Append-only cycle log, one JSON object per line |
| `observation_summary.json` | Aggregated stats updated each cycle |

### Usage

```bash
python observer.py                        # Continuous
python observer.py --once                 # Single snapshot
python observer.py --review               # Review candidates before expiry
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SENTINEL_URL` | `http://127.0.0.1:8100` | API endpoint |
| `OBSERVER_DATA_DIR` | `/mnt/e/kohanastack/sentinel/collector-data` | Output directory |
| `EXCLUDE_LIST` | `""` | Comma-separated patterns to skip |
| `OBSERVATION_MODE` | `silent` | `"silent"` or `"alerting"` |

### Current Status

- **Actively running** and writing to `observation_log.jsonl` (179,807 B as of 2026-08-26)
- Writes `observation_summary.json` after each cycle
- Polls: `/status`, `/query/anomalies`, `/query/drift`, `/query/candidates`

---

## Bind Mount Requirement

| Host Path | Container Path | Mode |
|---|---|---|
| `E:\kohanastack\sentinel\collector-data\` | `/data/collector/` | rw |

Files expected:
- `host-ss.json` — host collector output
- `observation_log.jsonl` — observer output
- `observation_summary.json` — observer summary

---

## Current State Summary

| Component | Status | Notes |
|---|---|---|
| `host_collector.py` | 📦 Present | Not running, `host-ss.json` stale since 2026-08-24 |
| `docker_collector.py` | 📦 Present | Not used by analyzer |
| `observer.py` | ✅ Running | Actively writing JSONL |
| `host-ss.json` | ⚠️ Stale | Last written 2026-08-24 21:22 |
| Systemd timer | ❌ Not configured | No timer for collectors |
