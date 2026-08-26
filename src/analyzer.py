#!/usr/bin/env python3
"""
Sentinel Analyzer - Containerized service
Reads host collector JSON snapshot, performs Docker drift detection via Docker socket,
performs anomaly analysis, sends alerts via OpenClaw webhook, exposes FastAPI for queries.
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import docker
import requests
from fastapi import FastAPI, HTTPException
import uvicorn

from src.db import SentinelDB
from src.notifier import SentinelNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("SentinelAnalyzer")


class SentinelAnalyzer:
    def __init__(self):
        self.db = SentinelDB()
        self.notifier = SentinelNotifier(db=self.db)
        self.collector_dir = Path("/data/collector")
        self.last_docker_snapshot: Dict[str, Any] = {}
        self.last_host_snapshot: Dict[str, Any] = {}
        self.is_running = True
        self.cycle_count = 0
        
        # Docker client for drift detection (uses mounted socket)
        try:
            self.docker_client = docker.from_env()
            logger.info("Connected to Docker socket for drift detection")
        except Exception as e:
            logger.error(f"Docker socket connection failed: {e}")
            self.docker_client = None

    async def initialize(self):
        logger.info("Initializing Sentinel Analyzer...")
        self.db.connect()
        
        # Load initial snapshots if they exist
        self.last_host_snapshot = self._load_host_snapshot()
        
        # Get initial Docker baseline directly from socket
        if self.docker_client:
            self.last_docker_snapshot = self._get_docker_containers()
            logger.info(f"Loaded initial Docker baseline: {len(self.last_docker_snapshot)} containers")
        
        if self.last_host_snapshot:
            logger.info(f"Loaded initial Host baseline: {len(self.last_host_snapshot.get('listening_ports', {}))} ports")
        
        logger.info("Sentinel Analyzer initialized and active.")

    def _load_host_snapshot(self) -> Dict[str, Any]:
        """Load host snapshot from collector file."""
        path = self.collector_dir / "host-ss.json"
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                return data
            except Exception as e:
                logger.warning(f"Failed to load host-ss.json: {e}")
        return {}

    def _get_docker_containers(self) -> Dict[str, Any]:
        """Fetch current running containers directly from Docker socket."""
        if not self.docker_client:
            return {}
        
        try:
            containers = self.docker_client.containers.list()
            snapshot = {}
            for c in containers:
                ports = c.attrs.get('NetworkSettings', {}).get('Ports', {})
                snapshot[c.id] = {
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "status": c.status,
                    "ports": ports,
                    "networks": list(c.attrs.get('NetworkSettings', {}).get('Networks', {}).keys()),
                    "created": c.attrs.get('Created'),
                    "labels": c.labels
                }
            return snapshot
        except Exception as e:
            logger.error(f"Failed to get Docker containers: {e}")
            return {}

    def _get_host_data(self) -> Dict[str, Any]:
        """Read host snapshot from collector file."""
        return self._load_host_snapshot()

    def check_docker_drift(self, current: Dict[str, Any], previous: Dict[str, Any]) -> List[str]:
        """P5 Rule: Detect new containers."""
        new_containers = set(current.keys()) - set(previous.keys())
        drift = []
        
        for cid in new_containers:
            c_info = current[cid]
            logger.warning(f"[P5 ALERT] Container Drift Detected: {c_info['name']} ({cid})")
            drift.append(cid)
            
            # Log as incident in DB
            # Serialize container_info for JSONB storage (handles datetime, complex types)
            serializable_info = {
                "name": c_info.get('name'),
                "image": c_info.get('image'),
                "status": c_info.get('status'),
                "ports": c_info.get('ports'),
                "networks": c_info.get('networks'),
                "created": str(c_info.get('created')) if c_info.get('created') else None,
                "labels": c_info.get('labels')
            }
            self.db.log_event({
                "source": "docker",
                "event_type": "container_drift",
                "container_id": cid,
                "service_name": c_info.get('name'),
                "direction": "inbound",
                "raw_data": {"action": "container_created", "container_info": serializable_info}
            })
            
            # Save topology snapshot
            self.db.save_topology({
                "containers": json.dumps(current),
                "ports": json.dumps(self.last_host_snapshot.get('listening_ports', {})),
                "arp": json.dumps(self.last_host_snapshot.get('arp_table', []))
            })
            
            # Send P5 alert
            self.notifier.notify_drift(c_info['name'], cid)
        
        return drift

    def check_host_anomalies(self, host_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check active connections against allowlist."""
        anomalies = []
        connections = host_data.get('active_connections', [])
        
        for conn in connections:
            pattern = f"{conn['dst_ip']}:{conn['dst_port']}"
            
            if not self.db.check_allowlist(pattern):
                logger.warning(f"[ANOMALY] Unrecognized connection to {pattern}")
                
                # Log event - serialize connection dict for JSONB
                serializable_conn = {
                    "dst_ip": conn.get('dst_ip'),
                    "dst_port": conn.get('dst_port'),
                    "proto": conn.get('proto'),
                    "local": conn.get('local')
                }
                self.db.log_event({
                    "source": "host",
                    "dst_ip": conn['dst_ip'],
                    "dst_port": conn['dst_port'],
                    "proto": conn['proto'],
                    "direction": "outbound",
                    "raw_data": {"pattern": pattern, "connection": serializable_conn}
                })
                
                # Add as observation candidate for 48h baseline building
                self.db.add_candidate(pattern, source="host", reason=f"pattern observed: {conn.get('proto','?')} → {conn.get('dst_ip','?')}:{conn.get('dst_port','?')}")
                
                anomalies.append({
                    "pattern": pattern,
                    "connection": conn
                })
                
                # Send P3 alert
                self.notifier.notify_anomaly(pattern)
        
        return anomalies

    async def run_cycle(self):
        """Single analysis cycle."""
        self.cycle_count += 1
        logger.info(f"--- Starting Analysis Cycle #{self.cycle_count} ---")

        try:
            # 1. Get Docker snapshot directly from socket
            current_docker = self._get_docker_containers()
            
            # 2. Check for Docker drift (P5)
            if self.last_docker_snapshot:
                drift = self.check_docker_drift(current_docker, self.last_docker_snapshot)
                if drift:
                    logger.info(f"Drift detected: {len(drift)} new container(s)")
            
            self.last_docker_snapshot = current_docker

            # 3. Load Host snapshot
            current_host = self._get_host_data()
            
            # 4. Check for host anomalies
            if current_host:
                anomalies = self.check_host_anomalies(current_host)
                if anomalies:
                    logger.info(f"Anomalies detected: {len(anomalies)} unrecognized connection(s)")
            
            self.last_host_snapshot = current_host

            # 5. Save topology snapshot (periodic - every hour)
            if self.cycle_count % 60 == 0:  # 60 cycles * 60s = 1 hour
                self.db.save_topology({
                    "containers": json.dumps(current_docker),
                    "ports": json.dumps(current_host.get('listening_ports', {})),
                    "arp": json.dumps(current_host.get('arp_table', []))
                })
                logger.info("Hourly topology snapshot saved")

            logger.info(f"Cycle #{self.cycle_count} complete. "
                       f"Containers: {len(current_docker)}, "
                       f"Ports: {len(current_host.get('listening_ports', {}))}")

        except Exception as e:
            logger.exception(f"Error in analysis cycle: {e}")

    def stop(self):
        self.is_running = False
        self.db.close()

    async def run_loop(self):
        """Main analysis loop."""
        await self.initialize()
        
        while self.is_running:
            await self.run_cycle()
            await asyncio.sleep(60)  # 60 second cycle


# Global analyzer instance
analyzer_instance: Optional[SentinelAnalyzer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global analyzer_instance
    logger.info("Starting Sentinel Analyzer...")
    analyzer_instance = SentinelAnalyzer()
    await analyzer_instance.initialize()
    # Start background analysis loop
    loop_task = asyncio.create_task(analyzer_instance.run_loop())
    logger.info("Sentinel Analyzer started with background loop")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Sentinel Analyzer...")
    analyzer_instance.stop()
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    logger.info("Sentinel Analyzer stopped")


# FastAPI app for queries
app = FastAPI(title="Sentinel Analyzer API", lifespan=lifespan)


@app.get("/status")
async def get_status():
    return {
        "status": "active",
        "version": "v1.0-containerized",
        "db": "connected",
        "cycles_completed": analyzer_instance.cycle_count if analyzer_instance else 0,
        "last_docker_containers": len(analyzer_instance.last_docker_snapshot) if analyzer_instance else 0,
        "last_host_ports": len(analyzer_instance.last_host_snapshot.get('listening_ports', {})) if analyzer_instance else 0
    }


@app.get("/query/drift")
async def get_drift():
    """Fetch the latest container drift events."""
    query = "SELECT * FROM sentinel_db.topology_snapshots ORDER BY snapshot_ts DESC LIMIT 1"
    snapshot = analyzer_instance.db.execute(query) if analyzer_instance else None
    return {"latest_snapshot": snapshot[0] if snapshot else None}


@app.get("/query/diff")
async def get_topology_diff(days: int = 1):
    """
    Compare latest topology snapshot with one from N days ago.
    Returns: new containers, removed containers, new ports, removed ports, new ARP entries.
    Example: GET /query/diff?days=1 → what changed since yesterday
    """
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    cutoff = f"NOW() AT TIME ZONE 'UTC' - interval '{days} day'"
    
    query = f"""
        SELECT * FROM sentinel_db.topology_snapshots
        WHERE snapshot_ts >= {cutoff}
        ORDER BY snapshot_ts ASC, snapshot_ts DESC
        LIMIT 1
    """
    older = analyzer_instance.db.execute(query)
    
    query = f"""
        SELECT * FROM sentinel_db.topology_snapshots
        WHERE snapshot_ts >= {cutoff}
        ORDER BY snapshot_ts DESC
        LIMIT 1
    """
    newer = analyzer_instance.db.execute(query)
    
    if not older or not newer:
        return {"error": "Insufficient snapshots", "snapshots_available": len(newer)}
    
    old = older[0]
    new = newer[0]
    
    old_containers = json.loads(old['containers']) if old['containers'] else {}
    new_containers = json.loads(new['containers']) if new['containers'] else {}
    old_ports = json.loads(old['listening_ports']) if old['listening_ports'] else {}
    new_ports = json.loads(new['listening_ports']) if new['listening_ports'] else {}
    old_arp = json.loads(old['arp_table']) if old['arp_table'] else []
    new_arp = json.loads(new['arp_table']) if new['arp_table'] else []
    
    old_ids = set(old_containers.keys())
    new_ids = set(new_containers.keys())
    
    new_containers_set = new_ids - old_ids
    removed_containers_set = old_ids - new_ids
    
    old_port_set = set(old_ports.keys())
    new_port_set = set(new_ports.keys())
    new_ports_set = new_port_set - old_port_set
    removed_ports_set = old_port_set - new_port_set
    
    new_arp_ips = {e.get('ip') for e in new_arp} if new_arp else set()
    old_arp_ips = {e.get('ip') for e in old_arp} if old_arp else set()
    new_arp_entries = [e for e in new_arp if e.get('ip') not in old_arp_ips]
    
    return {
        "compared": f"previous snapshot vs latest (interval: {days} day(s))",
        "new_containers": [old_containers[cid] if cid not in new_containers else new_containers[cid] for cid in new_containers_set],
        "removed_containers": list(old_containers[cid].get('name', cid) for cid in removed_containers_set),
        "new_ports": list(new_ports[cid] for cid in new_ports_set),
        "removed_ports": list(old_ports[cid].get('ip', cid) + ':' + str(cid) for cid in removed_ports_set),
        "new_arp_entries": new_arp_entries,
        "total_new": len(new_containers_set) + len(new_ports_set) + len(new_arp_entries)
    }


@app.get("/query/anomalies")
async def get_anomalies(limit: int = 10):
    """Fetch the most recent unrecognized network events."""
    query = "SELECT * FROM sentinel_db.events WHERE source = 'host' ORDER BY ts DESC LIMIT %s"
    return analyzer_instance.db.execute(query, (limit,)) if analyzer_instance else []


@app.get("/query/collectors")
async def get_collector_status():
    """Check collector file freshness."""
    host_file = Path("/data/collector/host-ss.json")
    
    return {
        "host_collector": {
            "exists": host_file.exists(),
            "size": host_file.stat().st_size if host_file.exists() else 0,
            "age_seconds": time.time() - host_file.stat().st_mtime if host_file.exists() else None
        },
        "docker_collector": {
            "mode": "internal_docker_socket",
            "last_containers": len(analyzer_instance.last_docker_snapshot) if analyzer_instance else 0
        }
    }


@app.post("/mute")
async def mute_target(target: str, duration: str = "1h", reason: str = "operator mute"):
    """
    Mute alerts for a target (container, IP, port, pattern).
    Duration format: '30m', '1h', '2h', etc.
    """
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    # Parse duration
    import re
    match = re.match(r"^(\d+)([mhd])$", duration.lower())
    if not match:
        raise HTTPException(status_code=400, detail="Invalid duration format. Use '30m', '1h', '2d', etc.")
    
    value, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        seconds = value * 60
    elif unit == "h":
        seconds = value * 3600
    elif unit == "d":
        seconds = value * 86400
    else:
        raise HTTPException(status_code=400, detail="Invalid unit. Use m, h, or d.")
    
    # Insert mute window
    from datetime import datetime, timezone, timedelta
    muted_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    
    query = """
        INSERT INTO sentinel_db.mute_window (target, muted_until_ts, reason, created_ts)
        VALUES (%s, %s, %s, NOW() AT TIME ZONE 'UTC')
        ON CONFLICT (target) DO UPDATE SET
            muted_until_ts = EXCLUDED.muted_until_ts,
            reason = EXCLUDED.reason,
            created_ts = EXCLUDED.created_ts
    """
    analyzer_instance.db.execute(query, (target, muted_until, reason))
    
    return {"muted": target, "until": muted_until.isoformat(), "reason": reason}


@app.get("/mute")
async def list_mutes():
    """List active mute windows."""
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    query = "SELECT target, muted_until_ts, reason, created_ts FROM sentinel_db.mute_window WHERE muted_until_ts > NOW() AT TIME ZONE 'UTC' ORDER BY muted_until_ts"
    return analyzer_instance.db.execute(query)


@app.delete("/mute/{target}")
async def unmute_target(target: str):
    """Remove a mute window."""
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    query = "DELETE FROM sentinel_db.mute_window WHERE target = %s"
    analyzer_instance.db.execute(query, (target,))
    
    return {"unmuted": target}


@app.get("/query/candidates")
async def get_candidates():
    """Fetch all observation candidates from known_good table (for watcher review)."""
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    query = """
        SELECT pattern, source, reason, added_ts, expiry, added_by
        FROM sentinel_db.known_good
        WHERE added_by = 'sentinel:observation'
        ORDER BY added_ts DESC
    """
    return analyzer_instance.db.execute(query)


@app.post("/promote")
async def promote_candidate(pattern: str):
    """Promote an observation candidate to permanent allowlist entry (remove expiry)."""
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    query = "UPDATE sentinel_db.known_good SET expiry = NULL, added_by = 'operator' WHERE pattern = %s AND expiry IS NOT NULL"
    analyzer_instance.db.execute(query, (pattern,))
    
    return {"promoted": pattern}


@app.get("/query/observation_log")
async def get_observation_log(limit: int = 100):
    """Fetch recent observation log entries (for operator review after 48h)."""
    if not analyzer_instance:
        raise HTTPException(status_code=503, detail="Analyzer not initialized")
    
    query = """
        SELECT pattern, source, reason, added_ts, expiry, added_by
        FROM sentinel_db.known_good
        WHERE added_by = 'sentinel:observation'
        ORDER BY added_ts DESC
        LIMIT %s
    """
    return analyzer_instance.db.execute(query, (limit,))