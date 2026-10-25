import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime, timezone
import asyncio
import time
import uvicorn
import json
import logging
import docker
from contextlib import asynccontextmanager
from pathlib import Path
from db import SentinelDB
from notifier import SentinelNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("SentinelAPI")

db = SentinelDB()
notifier = SentinelNotifier(db=db)

# ── Shared read helpers for the observer-facing routes ────────────────
# Created lazily so an unavailable socket degrades to empty results rather
# than taking the whole API down at import time.
_docker_client = None


def _get_docker_client():
    global _docker_client
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Docker socket unavailable: {e}")
    return _docker_client


# Collector artifacts are written by the host-side collector and observer.
# In the container they land on the bind mount; on the host, beside the repo.
COLLECTOR_DIRS = [
    Path("/data/collector"),
    Path(__file__).resolve().parent.parent / "collector-data",
]

# Credentials file written by the Setup page. The image copies sentinel/ to
# /app/sentinel/, so the real file is /app/sentinel/sentinel.env — not
# /app/sentinel.env, which is what this used to write to (nothing reads it).
SENTINEL_ROOT = os.getenv("SENTINEL_ROOT", "/app")
ENV_FILE_CANDIDATES = [
    Path(SENTINEL_ROOT) / "sentinel.env",
    Path(SENTINEL_ROOT) / "sentinel" / "sentinel.env",
]


def _env_file_path():
    """First existing credentials file, else the intended write target."""
    for candidate in ENV_FILE_CANDIDATES:
        if candidate.exists():
            return candidate
    return ENV_FILE_CANDIDATES[-1]


def _load_host_snapshot() -> dict:
    """Read the host collector's snapshot (host-ss.json); first readable path wins."""
    for collector_dir in COLLECTOR_DIRS:
        path = collector_dir / "host-ss.json"
        if not path.exists():
            continue
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Unreadable host snapshot {path}: {e}")
    return {}


def get_container_topology() -> dict:
    """Live per-container topology from the Docker socket.

    Keyed by full container id; each value carries the fields observer.py
    reads (name, short_id, image, status, ip, ports, health, created).
    """
    client = _get_docker_client()
    if client is None:
        return {}

    try:
        containers = client.containers.list()
    except Exception as e:
        logger.error(f"Container list failed: {e}")
        return {}

    topology = {}
    for c in containers:
        attrs = c.attrs
        network_settings = attrs.get("NetworkSettings", {}) or {}
        networks = network_settings.get("Networks", {}) or {}
        ports = network_settings.get("Ports", {}) or {}
        state = attrs.get("State", {}) or {}

        port_list = []
        for container_port, bindings in ports.items():
            protocol = container_port.split("/")[1] if "/" in container_port else "tcp"
            if bindings:
                for b in bindings:
                    port_list.append({
                        "host_ip": b.get("HostIp", ""),
                        "host_port": str(b.get("HostPort", "")),
                        "container_port": container_port,
                        "protocol": protocol,
                    })
            else:
                port_list.append({
                    "host_ip": "",
                    "host_port": "",
                    "container_port": container_port,
                    "protocol": protocol,
                })

        # Prefer a kohana-* mesh network, else whatever is attached first.
        primary = next(
            (v for k, v in networks.items() if k.startswith("kohana")),
            next(iter(networks.values()), {}),
        )

        topology[c.id] = {
            "name": attrs.get("Name", "").lstrip("/"),
            "id": c.id[:12],
            "short_id": c.id[:12],
            "image": attrs.get("Config", {}).get("Image", ""),
            "state": state,
            "status": state.get("Status", "unknown"),
            "created": attrs.get("Created", ""),
            "ip": primary.get("IPAddress", ""),
            "network": list(networks.keys()),
            "ports": port_list,
            "labels": attrs.get("Config", {}).get("Labels", {}) or {},
            "health": (state.get("Health") or {}).get("Status"),
        }

    return topology




def _iter_port_bindings(raw) -> list:
    """Normalize the two shapes a container's `ports` takes in stored snapshots.

    The monitor writes a list of {host_ip, host_port, container_port, protocol}
    dicts; analyzer-era rows used Docker's own mapping of
    {"8100/tcp": [{"HostIp": ..., "HostPort": ...}]}. /api/ports assumed only
    the latter and 500'd on the former.
    """
    out = []
    if isinstance(raw, dict):
        for port_key, bindings in raw.items():
            if "/" not in str(port_key):
                continue
            port_str, proto = str(port_key).split("/", 1)
            if not port_str.isdigit():
                continue
            for binding in (bindings or []):
                out.append({
                    "port": int(port_str),
                    "proto": proto,
                    "ip": (binding or {}).get("HostIp", "0.0.0.0"),
                })
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            port_str, _, proto = str(item.get("container_port") or "").partition("/")
            if not port_str.isdigit():
                continue
            out.append({
                "port": int(port_str),
                "proto": proto or "tcp",
                "ip": item.get("host_ip") or "0.0.0.0",
            })
    return out


def _tail_lines(path, count: int) -> list:
    """Read the last `count` lines of a file without loading the whole thing.

    The observation log is tens of MB on a Windows bind mount; a full
    readlines() measured 35s cold, which made /api/baseline/deviations look
    hung to any client that wasn't served from page cache.
    """
    block = 64 * 1024
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        buf = b""
        while size > 0 and buf.count(b"\n") <= count:
            step = min(block, size)
            size -= step
            f.seek(size)
            buf = f.read(step) + buf
    return [
        line.decode("utf-8", "replace")
        for line in buf.split(b"\n")[-count:]
        if line.strip()
    ]


# ── Background monitor (Docker socket only) ───────────────────────────
# Drift detection runs in-process on the same uvicorn worker. Host network
# state is deliberately NOT collected here: this container sits on bridge
# networks, so `ss` and /proc/net would only ever see Sentinel's own sockets
# and would flag its own DB/Ollama traffic as unrecognised connections. Host
# data arrives via collector-data/host-ss.json instead, written by
# collectors/host_collector.py on the host.
CYCLE_SECONDS = 60
SNAPSHOT_EVERY_CYCLES = 60  # 60 cycles x 60s = 1 hour
HOST_ANOMALY_COOLDOWN = 3600  # seconds before the same host pattern is re-logged


class SentinelMonitor:
    """Watches the Docker mesh for new containers and snapshots topology."""

    def __init__(self):
        self.cycle_count = 0
        self.seen_ids: set = set()
        self.last_topology: dict = {}
        self.is_running = True
        self._host_pattern_seen: dict = {}

    def _handle_drift(self, current: dict) -> list:
        """P5: containers we have never observed before.

        Diffed against a grow-only set, not the previous cycle's snapshot. A
        transient partial result from the Docker socket would otherwise shrink
        the baseline and re-alert on every container that reappeared — seen
        live as three P5s for an n8n container whose RestartCount never moved.
        """
        if not self.seen_ids:
            self.seen_ids |= set(current)  # first observation: baseline, no alerts
            return []
        new_ids = set(current) - self.seen_ids
        self.seen_ids |= set(current)
        for cid in new_ids:
            info = current[cid]
            name = info.get("name") or cid
            logger.warning(
                f"[P5 ALERT] Container drift detected: {name} ({info.get('short_id', cid)})"
            )
            try:
                db.log_event({
                    "source": "docker",
                    "event_type": "container_drift",
                    "container_id": cid,
                    "service_name": name,
                    "direction": "inbound",
                    "raw_data": {
                        "action": "container_created",
                        "container_info": {
                            key: info.get(key)
                            for key in ("name", "image", "status", "ports", "labels", "created")
                        },
                    },
                })
            except Exception as e:
                logger.error(f"Failed to log drift event for {name}: {e}")
            notifier.notify_drift(name, info.get("short_id", cid))
        return list(new_ids)

    def _save_snapshot(self, topology: dict):
        """Hourly snapshot: containers from the socket, host side from the collector file."""
        host_snapshot = _load_host_snapshot()
        db.save_topology({
            "containers": json.dumps(topology, default=str),
            "ports": json.dumps(host_snapshot.get("listening_ports", {})),
            "arp": json.dumps(host_snapshot.get("arp_table", [])),
        })
        logger.info(
            f"Topology snapshot saved: {len(topology)} containers, "
            f"{len(host_snapshot.get('listening_ports', {}))} host ports"
        )

    def _check_host_anomalies(self) -> list:
        """Flag host connections that are not in the allowlist.

        Reads the collector's snapshot instead of running `ss`: this container
        sits on bridge networks, so anything it could see locally would be its
        own traffic. Deduped with a cooldown — the host's connection table
        barely changes, and re-logging every cycle would write ~1,440 duplicate
        rows per pattern per day.
        """
        connections = _load_host_snapshot().get("active_connections") or []
        if not connections:
            return []

        # Keep the dedup map bounded; entries are cheap but unbounded growth
        # over a long uptime is not.
        if len(self._host_pattern_seen) > 1000:
            cutoff = time.monotonic() - HOST_ANOMALY_COOLDOWN
            self._host_pattern_seen = {
                k: v for k, v in self._host_pattern_seen.items() if v > cutoff
            }

        now = time.monotonic()
        anomalies = []
        for conn in connections:
            dst_ip = conn.get("dst_ip")
            dst_port = conn.get("dst_port")
            if not dst_ip or dst_port is None:
                continue
            pattern = f"{dst_ip}:{dst_port}"

            # Checked every cycle (not cached) so allowlist edits take effect
            # immediately.
            try:
                if db.check_allowlist(pattern):
                    continue
            except Exception as e:
                logger.error(f"Allowlist check failed for {pattern}: {e}")
                continue

            last = self._host_pattern_seen.get(pattern)
            if last is not None and now - last < HOST_ANOMALY_COOLDOWN:
                continue
            self._host_pattern_seen[pattern] = now

            logger.warning(f"[ANOMALY] Unrecognized host connection to {pattern}")
            try:
                db.log_event({
                    "source": "host",
                    "dst_ip": dst_ip,
                    "dst_port": dst_port,
                    "proto": conn.get("proto"),
                    "direction": "outbound",
                    "raw_data": {"pattern": pattern, "connection": conn},
                })
                db.add_candidate(
                    pattern, source="host",
                    reason=f"pattern observed: {conn.get('proto', '?')} -> {pattern}",
                )
            except Exception as e:
                logger.error(f"Failed to log host anomaly {pattern}: {e}")
            notifier.notify_anomaly(pattern)
            anomalies.append(pattern)
        return anomalies

    async def run_loop(self):
        while self.is_running:
            self.cycle_count += 1
            try:
                current = get_container_topology()
                # An empty result means the socket failed, not that every
                # container vanished; skip rather than treat it as a mass
                # removal. _handle_drift seeds its own baseline on first sight.
                if current:
                    first_cycle = not self.last_topology
                    self._handle_drift(current)
                    self.last_topology = current
                    # Snapshot immediately on the first cycle so the dashboard's
                    # topology/port widgets have data at once, then hourly.
                    if first_cycle or self.cycle_count % SNAPSHOT_EVERY_CYCLES == 0:
                        self._save_snapshot(current)
                self._check_host_anomalies()
            except Exception as e:
                logger.exception(f"Monitor cycle {self.cycle_count} failed: {e}")
            await asyncio.sleep(CYCLE_SECONDS)

    def stop(self):
        self.is_running = False


monitor = SentinelMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    task = asyncio.create_task(monitor.run_loop())
    logger.info("Sentinel monitor started (Docker socket drift detection)")
    try:
        yield
    finally:
        monitor.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        db.close()


app = FastAPI(title="Sentinel API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@ app.get("/api/setup/status")
async def get_setup_status():
    """Check what's configured and what's missing."""
    from datetime import datetime, timezone
    issues = []
    
    # Check if any events exist
    event_count = db.execute("SELECT count(*) as cnt FROM events")[0]["cnt"]
    if event_count == 0:
        issues.append("no_events")
    
    # Check if topology has data
    topo_count = db.execute("SELECT count(*) as cnt FROM topology_snapshots")[0]["cnt"]
    if topo_count == 0:
        issues.append("no_topology")
    
    # Check allowlist
    allow_count = db.execute("SELECT count(*) as cnt FROM known_good")[0]["cnt"]
    operator_count = db.execute("SELECT count(*) as cnt FROM known_good WHERE added_by = 'operator'")[0]["cnt"]
    if allow_count == 0:
        issues.append("empty_allowlist")

    setup_complete = operator_count > 0
    
    # Check incidents
    inc_count = db.execute("SELECT count(*) as cnt FROM incidents WHERE closed_ts IS NULL")[0]["cnt"]
    
    # Check if Telegram is configured (check env)
    import os
    tg_token = os.getenv("TELEGRAM_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_configured = bool(tg_token and tg_chat)
    
    return {
        "initialized": len(issues) == 0,
        "issues": issues,
        "event_count": event_count,
        "topology_count": topo_count,
        "allowlist_count": allow_count,
        "open_incidents": inc_count,
        "telegram_configured": telegram_configured,
        "setup_complete": setup_complete,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@ app.get("/api/setup/discover")
async def setup_discover():
    """Read-only discovery of running containers + host ports for first-time setup."""
    import docker
    containers = []
    try:
        client = _get_docker_client()
        if client:
            for c in client.containers.list():
                ports = {}
                try:
                    ports = c.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
                except Exception:
                    ports = {}
                exposed = []
                for k, v in (ports or {}).items():
                    exposed.append(k)
                containers.append({
                    "id": c.id[:12],
                    "name": c.name,
                    "status": c.status,
                    "image": (c.image.tags[0] if c.image.tags else str(c.image.id)[:12]),
                    "exposed_ports": exposed,
                })
    except Exception as e:
        logger.warning(f"Docker discovery failed: {e}")

    host = _load_host_snapshot() or {}
    host_ports = host.get("listening_ports") or []
    # normalize
    normalized_ports = []
    for p in host_ports:
        if isinstance(p, dict):
            normalized_ports.append({
                "port": p.get("port") or p.get("local_port"),
                "proto": p.get("proto") or p.get("protocol", "tcp"),
                "process": p.get("process") or p.get("name"),
            })
        else:
            normalized_ports.append({"port": p, "proto": "tcp", "process": None})

    suggested = []
    for c in containers:
        for ep in c["exposed_ports"]:
            # ep like "80/tcp"
            port = ep.split("/")[0]
            suggested.append({"pattern": f"container:{c['name']}", "source": "docker", "reason": f"discovered container {c['name']}"})
    for hp in normalized_ports:
        if hp.get("port"):
            suggested.append({"pattern": f"127.0.0.1:{hp['port']}", "source": "host", "reason": "discovered host port"})

    # de-dupe
    seen = set()
    uniq = []
    for s in suggested:
        if s["pattern"] in seen:
            continue
        seen.add(s["pattern"])
        uniq.append(s)

    return {
        "containers": containers,
        "host_ports": normalized_ports,
        "suggested_patterns": uniq,
        "host_snapshot_present": bool(host),
    }


@ app.post("/api/setup/confirm")
async def setup_confirm(payload: dict):
    """Persist operator-confirmed allowlist patterns. Idempotent."""
    patterns = payload.get("patterns", []) if isinstance(payload, dict) else []
    inserted = 0
    for p in patterns:
        pattern = (p.get("pattern") or "")[:256]
        source = (p.get("source") or "setup")[:64]
        reason = (p.get("reason") or "first-time setup")[:256]
        if not pattern:
            continue
        try:
            db.execute(
                """INSERT INTO known_good (pattern, source, reason, added_by, expiry)
                   VALUES (%s, %s, %s, %s, NULL)
                   ON CONFLICT (pattern) DO NOTHING""",
                (pattern, source, reason, "operator"),
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"setup_confirm insert failed for {pattern}: {e}")

    # mark complete via a flag file (Postgres is source of truth for rows)
    try:
        flag = Path("/data/collector/.setup-complete")
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("ok")
    except Exception:
        try:
            flag = Path(__file__).resolve().parent.parent / "collector-data" / ".setup-complete"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("ok")
        except Exception as e:
            logger.warning(f"could not write setup flag: {e}")

    return {"saved": inserted, "total_submitted": len(patterns)}
@ app.post("/api/setup/telegram")
async def configure_telegram(token: str, chat_id: str):
    """Save Telegram bot token and chat ID to the environment file and restart notifier."""
    import os
    env_path = _env_file_path()
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        new_lines = []
        token_set = False
        chat_set = False
        for line in lines:
            if line.startswith("TELEGRAM_TOKEN="):
                new_lines.append(f"TELEGRAM_TOKEN={token}\n")
                token_set = True
            elif line.startswith("TELEGRAM_CHAT_ID="):
                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                chat_set = True
            else:
                new_lines.append(line)
        if not token_set:
            new_lines.append(f"TELEGRAM_TOKEN={token}\n")
        if not chat_set:
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        os.environ["TELEGRAM_TOKEN"] = token
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        return {"status": "configured", "token_set": True, "chat_set": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@ app.get("/api/baseline/deviations")
async def get_baseline_deviations(hours: int = Query(24, ge=1, le=168)):
    """Compute baseline deviations from historical observation_log.jsonl data.
    against baseline frequencies to flag anomalies.
    """
    import json
    import os

    jsonl_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'collector-data', 'observation_log.jsonl',
    )
    # Also check bind-mounted path (docker-compose volume: ./collector-data:/data/collector)
    jsonl_path_alt = '/data/collector/observation_log.jsonl'
    actual_path = jsonl_path if os.path.exists(jsonl_path) else (jsonl_path_alt if os.path.exists(jsonl_path_alt) else None)

    baseline_counts: dict[str, int] = {}
    if actual_path:
        try:
            for line in _tail_lines(actual_path, 500):
                try:
                    entry = json.loads(line)
                    for a in (entry.get('anomalies') or []):
                        ip = a.get('dst_ip')
                        if ip:
                            baseline_counts[ip] = baseline_counts.get(ip, 0) + 1
                except json.JSONDecodeError:
                    continue
        except (OSError, IOError):
            pass

    hours_val = max(1, min(hours, 168))
    recent_result = db.execute(
        f"SELECT src_ip, dst_ip, dst_port, proto, direction FROM events WHERE ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '{hours_val} hours'",
    )

    entity_counts: dict[str, int] = {}
    entity_peers: dict[str, set[str]] = {}

    for row in (recent_result or []):
        r = dict(row)
        entity = r.get('dst_ip') or r.get('src_ip') or 'unknown'
        entity_counts[entity] = entity_counts.get(entity, 0) + 1
        if entity not in entity_peers:
            entity_peers[entity] = set()
        peer = r.get('src_ip') or r.get('dst_ip')
        if peer and peer != entity and peer != 'unknown':
            entity_peers[entity].add(peer)

    deviations: list[dict] = []
    for entity, count in list(entity_counts.items())[:10]:
        baseline = baseline_counts.get(entity, max(1, count * 0.5))
        deviation_pct = ((count - baseline) / max(1, baseline)) * 100
        severity = (
            'high' if abs(deviation_pct) > 80 else
            'elevated' if abs(deviation_pct) > 30 else
            'normal'
        )
        deviations.append({
            'entity': str(entity),
            'metric': 'connections',
            'current': count,
            'baseline': round(baseline),
            'deviation': round(deviation_pct),
            'severity': severity,
        })

    for entity, peers in list(entity_peers.items())[:5]:
        current = len(peers)
        baseline = max(1, current * 0.7)
        deviation_pct = ((current - baseline) / baseline) * 100
        severity = (
            'high' if abs(deviation_pct) > 50 else
            'elevated' if abs(deviation_pct) > 20 else
            'normal'
        )
        deviations.append({
            'entity': str(entity),
            'metric': 'unique_peers',
            'current': current,
            'baseline': round(baseline),
            'deviation': round(deviation_pct),
            'severity': severity,
        })

    return {'deviations': deviations, 'baseline_source': 'observation_log.jsonl'}


@ app.get("/api/status")
async def get_status():
    return {"status": "active", "version": "v1.0-alpha", "db": "connected", "timestamp": datetime.now(timezone.utc).isoformat()}


@ app.get("/api/topology/current")
async def get_current_topology():
    result = db.execute("SELECT * FROM topology_snapshots ORDER BY snapshot_ts DESC LIMIT 1")
    if not result:
        return {"snapshot": None}
    snapshot = dict(result[0])
    # Parse JSON string columns into objects
    for col in ("containers", "listening_ports", "arp_table", "diff_against_previous"):
        val = snapshot.get(col)
        if isinstance(val, str):
            try:
                snapshot[col] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                snapshot[col] = None
    prev_result = db.execute("SELECT containers, listening_ports, arp_table FROM topology_snapshots ORDER BY snapshot_ts DESC OFFSET 1 LIMIT 1")
    if prev_result:
        prev = dict(prev_result[0])
        for col in ("containers", "listening_ports", "arp_table"):
            val = prev.get(col)
            if isinstance(val, str):
                try:
                    prev[col] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    prev[col] = None
        snapshot["diff"] = prev
    else:
        snapshot["diff"] = None
    return {"snapshot": snapshot}


@ app.get("/api/ports")
async def get_ports():
    """Get listening ports and active connections from latest topology snapshot."""
    import json
    result = db.execute("SELECT listening_ports, containers FROM topology_snapshots ORDER BY snapshot_ts DESC LIMIT 1")
    if not result:
        return {"listening": [], "connections": []}
    snapshot = dict(result[0])
    
    # Parse JSON strings
    listening_ports_raw = snapshot.get("listening_ports")
    containers_raw = snapshot.get("containers")
    
    listening_ports = json.loads(listening_ports_raw) if isinstance(listening_ports_raw, str) else (listening_ports_raw or {})
    containers = json.loads(containers_raw) if isinstance(containers_raw, str) else (containers_raw or {})
    
    # Extract listening ports from containers
    listening = []
    for container_id, container in containers.items():
        name = container.get("name") or container_id[:12]
        for binding in _iter_port_bindings(container.get("ports")):
            listening.append({
                "port": binding["port"],
                "proto": binding["proto"],
                "container": name,
                "ip": binding["ip"],
            })

    # Also check listening_ports from host
    if isinstance(listening_ports, dict):
        for port_str, info in listening_ports.items():
            try:
                port = int(port_str)
                proto = info.get("protocol", "tcp")
                listening.append({
                    "port": port,
                    "proto": proto,
                    "container": "host",
                    "ip": info.get("ip", "0.0.0.0")
                })
            except ValueError:
                continue
    
    # Extract active connections from events in last hour
    conn_result = db.execute(
        "SELECT src_ip, dst_ip, dst_port, proto, direction FROM events WHERE ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '1 hour' AND direction = 'outbound' LIMIT 100"
    )
    connections = [dict(r) for r in conn_result] if conn_result else []
    
    return {"listening": listening, "connections": connections}


@ app.get("/api/topology/history")
async def get_topology_history(hours: int = Query(24, ge=1, le=720), limit: int = Query(50, ge=1, le=500)):
    results = db.execute(
    "SELECT snapshot_ts, containers, listening_ports, arp_table FROM topology_snapshots WHERE snapshot_ts > NOW() AT TIME ZONE 'UTC' - INTERVAL %s ORDER BY snapshot_ts DESC LIMIT %s",
    (f"{max(1, min(hours, 720))} hours", limit),
)
    return {"snapshots": [dict(r) for r in results] if results else []}


@ app.get("/api/events")
async def get_events(source: Optional[str] = None, src_ip: Optional[str] = None, dst_ip: Optional[str] = None, direction: Optional[str] = None, hours: int = Query(24, ge=1, le=168), limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    conditions = [f"ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '{max(1, min(hours, 168))} hours'"]
    params: list = []
    if source:
        conditions.append(f"source = %s")
        params.append(source)
    if src_ip:
        conditions.append(f"src_ip = %s")
        params.append(src_ip)
    if dst_ip:
        conditions.append(f"dst_ip = %s")
        params.append(dst_ip)
    if direction:
        conditions.append(f"direction = %s")
        params.append(direction)
    query = f"SELECT * FROM events WHERE {' AND '.join(conditions)} ORDER BY ts DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    results = db.execute(query, tuple(params))
    count_query = f"SELECT count(*) as cnt FROM events WHERE {' AND '.join(conditions)}"
    count_result = db.execute(count_query, tuple(params[:-2]) if len(params) >= 2 else ())
    total = count_result[0]["cnt"] if count_result else 0
    return {"events": [dict(r) for r in results] if results else [], "total": total, "limit": limit, "offset": offset}


@ app.get("/api/events/{event_id}")
async def get_event(event_id: int):
    result = db.execute("SELECT * FROM events WHERE id = %s", (event_id,))
    if not result:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"event": dict(result[0])}


@ app.get("/api/anomalies")
async def get_anomalies(hours: int = Query(24, ge=1, le=168), limit: int = Query(50, ge=1, le=500)):
    query = f"SELECT e.*, CASE WHEN e.dst_ip IS NOT NULL AND NOT EXISTS (SELECT 1 FROM known_good k WHERE k.pattern = e.dst_ip || ':' || e.dst_port) THEN 'unrecognized_destination' ELSE 'anomalous_pattern' END as anomaly_type FROM events e LEFT JOIN incidents i ON e.id = ANY(i.related_events) WHERE e.ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '{max(1, min(hours, 168))} hours' AND i.closed_ts IS NULL ORDER BY e.ts DESC LIMIT {limit}"
    results = db.execute(query, (hours, limit))
    return {"anomalies": [dict(r) for r in results] if results else []}


@ app.get("/api/incidents")
async def get_incidents(status: Optional[str] = None, severity: Optional[str] = None, limit: int = 50, offset: int = 0):
    conditions = ["1=1"]
    params: list = []
    if status == "open":
        conditions.append("closed_ts IS NULL")
    elif status == "closed":
        conditions.append("closed_ts IS NOT NULL")
    if severity:
        conditions.append("severity = %s")
        params.append(int(severity.replace("P", "")))
    query = f"SELECT * FROM incidents WHERE {' AND '.join(conditions)} ORDER BY opened_ts DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    results = db.execute(query, tuple(params))
    return {"incidents": [dict(r) for r in results] if results else []}


@ app.post("/api/incidents")
async def create_incident(severity: int, summary: str, related_events: Optional[List[int]] = None):
    result = db.execute("INSERT INTO incidents (severity, summary, related_events) VALUES (%s, %s, %s) RETURNING id", (severity, summary, related_events or []))
    if result:
        return {"id": result[0]["id"], "status": "created"}
    raise HTTPException(status_code=500, detail="Failed to create incident")


@ app.patch("/api/incidents/{incident_id}")
async def update_incident(incident_id: int, closed: Optional[bool] = None, acknowledged: Optional[bool] = None, note: Optional[str] = None, recommended_action: Optional[str] = None):
    updates = []
    params = []
    if closed is not None:
        updates.append("closed_ts = NOW() AT TIME ZONE 'UTC'" if closed else "closed_ts = NULL")
    if acknowledged is not None:
        updates.append("operator_acknowledged = %s")
        params.append(acknowledged)
    if note:
        updates.append("operator_note = %s")
        params.append(note)
    if recommended_action:
        updates.append("recommended_action = %s")
        params.append(recommended_action)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    query = f"UPDATE incidents SET {', '.join(updates)} WHERE id = %s"
    params.append(incident_id)
    db.execute(query, tuple(params))
    return {"status": "updated", "id": incident_id}


@ app.get("/api/reputation")
async def get_reputation(verdict: Optional[str] = None, limit: int = 100, offset: int = 0):
    conditions = ["1=1"]
    params: list = []
    if verdict:
        conditions.append("verdict = %s")
        params.append(verdict)
    query = f"SELECT identifier, first_seen, last_seen, contact_count, verdict, note, last_updated FROM source_reputation WHERE {' AND '.join(conditions)} ORDER BY contact_count DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    results = db.execute(query, tuple(params))
    return {"sources": [dict(r) for r in results] if results else []}


@ app.patch("/api/reputation/{identifier}")
async def update_reputation(identifier: str, verdict: Optional[str] = None, note: Optional[str] = None):
    updates = ["last_updated = NOW() AT TIME ZONE 'UTC'"]
    params = []
    if verdict:
        updates.append("verdict = %s")
        params.append(verdict)
    if note:
        updates.append("note = %s")
        params.append(note)
    if len(updates) <= 1:
        raise HTTPException(status_code=400, detail="No updates provided")
    query = f"UPDATE source_reputation SET {', '.join(updates)} WHERE identifier = %s"
    params.append(identifier)
    db.execute(query, tuple(params))
    return {"status": "updated", "identifier": identifier}


@ app.get("/api/allowlist")
async def get_allowlist(status: Optional[str] = None, limit: int = 100, offset: int = 0):
    conditions = ["1=1"]
    params: list = []
    if status == "active":
        conditions.append("(expiry IS NULL OR expiry > NOW() AT TIME ZONE 'UTC')")
    elif status == "expired":
        conditions.append("expiry IS NOT NULL AND expiry <= NOW() AT TIME ZONE 'UTC'")
    elif status == "pending":
        conditions.append("expiry IS NOT NULL AND expiry > NOW() AT TIME ZONE 'UTC'")
    query = f"SELECT * FROM known_good WHERE {' AND '.join(conditions)} ORDER BY added_ts DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    results = db.execute(query, tuple(params))
    return {"entries": [dict(r) for r in results] if results else []}


@ app.post("/api/allowlist")
async def add_allowlist_entry(pattern: str, source: str = "operator", reason: str = "manual entry"):
    db.execute("INSERT INTO known_good (pattern, source, reason, added_by, expiry) VALUES (%s, %s, %s, %s, NULL) ON CONFLICT (pattern) DO UPDATE SET reason = EXCLUDED.reason", (pattern, source, reason, "operator"))
    return {"status": "added", "pattern": pattern}


@ app.delete("/api/allowlist/{pattern}")
async def delete_allowlist_entry(pattern: str):
    db.execute("DELETE FROM known_good WHERE pattern = %s", (pattern,))
    return {"status": "removed", "pattern": pattern}


@ app.post("/api/allowlist/{pattern}/promote")
async def promote_allowlist_entry(pattern: str):
    db.execute("UPDATE known_good SET expiry = NULL WHERE pattern = %s", (pattern,))
    return {"status": "promoted", "pattern": pattern}


@ app.get("/api/mute")
async def get_mutes():
    results = db.execute("SELECT * FROM mute_window WHERE muted_until_ts > NOW() AT TIME ZONE 'UTC' ORDER BY muted_until_ts ASC")
    return {"mutes": [dict(r) for r in results] if results else []}


@ app.post("/api/mute")
async def add_mute(target: str, duration_minutes: int = Query(..., ge=1, le=10080), reason: str = "operator mute"):
    db.execute("INSERT INTO mute_window (target, muted_until_ts, reason, created_ts) VALUES (%s, NOW() AT TIME ZONE 'UTC' + INTERVAL '%s minutes', %s, NOW() AT TIME ZONE 'UTC') ON CONFLICT (target) DO UPDATE SET muted_until_ts = EXCLUDED.muted_until_ts, reason = EXCLUDED.reason, created_ts = EXCLUDED.created_ts", (target, str(duration_minutes), reason))
    return {"status": "muted", "target": target, "duration_minutes": duration_minutes}


@ app.delete("/api/mute/{target}")
async def remove_mute(target: str):
    db.execute("DELETE FROM mute_window WHERE target = %s", (target,))
    return {"status": "unmuted", "target": target}


@ app.get("/api/query/summary")
async def get_summary(hours: int = Query(24, ge=1, le=168)):
    source_result = db.execute(f"SELECT source, count(*) as cnt FROM events WHERE ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '{max(1, min(hours, 168))} hours' GROUP BY source")
    talker_result = db.execute(f"SELECT dst_ip, count(*) as contacts, max(ts) as last_seen FROM events WHERE ts > NOW() AT TIME ZONE 'UTC' - INTERVAL '{max(1, min(hours, 168))} hours' AND dst_ip IS NOT NULL GROUP BY dst_ip ORDER BY contacts DESC LIMIT 10")
    incidents_result = db.execute("SELECT count(*) as cnt FROM incidents WHERE closed_ts IS NULL")
    rep_result = db.execute("SELECT verdict, count(*) as cnt FROM source_reputation GROUP BY verdict")
    mute_result = db.execute("SELECT count(*) as cnt FROM mute_window WHERE muted_until_ts > NOW() AT TIME ZONE 'UTC'")
    return {
        "period_hours": hours,
        "events_by_source": {r["source"]: r["cnt"] for r in source_result} if source_result else {},
        "top_talkers": [dict(r) for r in talker_result] if talker_result else [],
        "open_incidents": incidents_result[0]["cnt"] if incidents_result else 0,
        "reputation": {r["verdict"]: r["cnt"] for r in rep_result} if rep_result else {},
        "active_mutes": mute_result[0]["cnt"] if mute_result else 0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@ app.get("/api/query/search")
async def search(q: str, limit: int = 50):
    sp = f"%{q}%"
    event_results = db.execute("SELECT * FROM events WHERE src_ip::text ILIKE %s OR dst_ip::text ILIKE %s OR raw_data::text ILIKE %s ORDER BY ts DESC LIMIT %s", (sp, sp, sp, limit))
    rep_results = db.execute("SELECT identifier, verdict, contact_count, note FROM source_reputation WHERE identifier ILIKE %s OR note ILIKE %s LIMIT %s", (sp, sp, limit))
    allow_results = db.execute("SELECT pattern, source, reason, added_by FROM known_good WHERE pattern ILIKE %s OR reason ILIKE %s LIMIT %s", (sp, sp, limit))
    return {"query": q, "events": [dict(r) for r in event_results] if event_results else [], "reputation": [dict(r) for r in rep_results] if rep_results else [], "allowlist": [dict(r) for r in allow_results] if allow_results else []}


@ app.post("/api/alert")
async def trigger_alert(severity: str, message: str, context: Optional[str] = None):
    notifier.send_alert(severity, message, context)
    return {"status": "alert_sent"}


@ app.get("/api/drift")
async def get_drift():
    results = db.execute("SELECT snapshot_ts, containers FROM topology_snapshots ORDER BY snapshot_ts DESC LIMIT 2")
    if not results or len(results) < 2:
        return {"drift_detected": False, "message": "Need at least 2 snapshots"}
    current_raw = results[0]["containers"]
    previous_raw = results[1]["containers"]
    if not current_raw or not previous_raw:
        return {"drift_detected": False, "message": "Missing container data"}
    try:
        current = json.loads(current_raw) if isinstance(current_raw, str) else current_raw
        previous = json.loads(previous_raw) if isinstance(previous_raw, str) else previous_raw
    except (json.JSONDecodeError, TypeError):
        return {"drift_detected": False, "message": "Invalid container data"}
    current_names = set()
    previous_names = set()
    if isinstance(current, dict):
        for c in current.values():
            if isinstance(c, dict):
                current_names.add(c.get("name", c.get("id", "")))
    elif isinstance(current, list):
        for c in current:
            if isinstance(c, dict):
                current_names.add(c.get("name", c.get("id", "")))
    if isinstance(previous, dict):
        for c in previous.values():
            if isinstance(c, dict):
                previous_names.add(c.get("name", c.get("id", "")))
    elif isinstance(previous, list):
        for c in previous:
            if isinstance(c, dict):
                previous_names.add(c.get("name", c.get("id", "")))
    return {"drift_detected": bool(current_names - previous_names or previous_names - current_names), "new_containers": list(current_names - previous_names), "removed_containers": list(previous_names - current_names), "current_count": len(current_names), "previous_count": len(previous_names)}




# ── Observer-facing routes ────────────────────────────────────────────
# observer.py (host-side systemd unit) polls these four unversioned paths on
# this same port. They were originally defined in src/analyzer.py, which this
# container does not run — so every poll used to 404. Response shapes here are
# a contract with observer.py's _fetch_status / _fetch_anomalies /
# _fetch_topology / _fetch_candidates; change them in lockstep or not at all.


@ app.get("/status")
async def get_observer_status():
    """Analyzer-shaped status. observer.py reads `status` and `last_host_ports`."""
    return {
        "status": "active",
        "version": "v1.0-containerized",
        "db": "connected",
        "last_docker_containers": len(get_container_topology()),
        "last_host_ports": len(_load_host_snapshot().get("listening_ports", {})),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@ app.get("/query/container_topology")
async def query_container_topology():
    """Live container topology, read straight from the Docker socket."""
    return get_container_topology()


@ app.get("/query/anomalies")
async def query_anomalies(limit: int = 10):
    """Most recent host-sourced events, newest first — observer's ingest feed."""
    rows = db.execute(
        "SELECT * FROM events WHERE source = 'host' ORDER BY ts DESC LIMIT %s",
        (limit,),
    )
    anomalies = []
    for row in (rows or []):
        entry = dict(row)
        # observer.py filters these against EXCLUDE_LIST by `pattern`, which
        # lives inside raw_data rather than as a column — surface it flat.
        if not entry.get("pattern") and entry.get("dst_ip") and entry.get("dst_port") is not None:
            entry["pattern"] = f"{entry['dst_ip']}:{entry['dst_port']}"
        anomalies.append(entry)
    return anomalies


@ app.get("/query/candidates")
async def query_candidates():
    """Observation candidates still inside their 48h review window."""
    rows = db.execute(
        "SELECT pattern, source, reason, added_ts, expiry, added_by "
        "FROM known_good WHERE added_by = 'sentinel:observation' "
        "ORDER BY added_ts DESC"
    )
    return [dict(r) for r in (rows or [])]


# ── Dashboard serving ─────────────────────────────────────────────────
# Mount .next at /_next so HTML pages can find their /_next/static/chunks/*.js
app.mount("/_next", StaticFiles(directory="/app/dashboard/.next"), name="next-static")

DASHBOARD_PAGES = {
    "": "/app/dashboard/.next/server/app/index.html",
    "events": "/app/dashboard/.next/server/app/events.html",
    "topology": "/app/dashboard/.next/server/app/topology.html",
    "anomalies": "/app/dashboard/.next/server/app/anomalies.html",
    "incidents": "/app/dashboard/.next/server/app/incidents.html",
    "allowlist": "/app/dashboard/.next/server/app/allowlist.html",
    "queries": "/app/dashboard/.next/server/app/queries.html",
    "reputation": "/app/dashboard/.next/server/app/reputation.html",
    "setup": "/app/dashboard/setup.html",
}

@ app.get("/{page_path:path}", include_in_schema=False)
async def serve_dashboard(page_path: str):
    """Serve static dashboard pages. API routes take priority (defined above)."""
    page_path = page_path.lstrip("/")
    if page_path in DASHBOARD_PAGES:
        return FileResponse(DASHBOARD_PAGES[page_path])
    base = page_path.split("/")[0] if "/" in page_path else page_path
    if base in DASHBOARD_PAGES:
        return FileResponse(DASHBOARD_PAGES[base])
    raise HTTPException(status_code=404, detail="Not found")


