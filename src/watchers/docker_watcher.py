import docker
import logging
import json
from datetime import datetime
from db import SentinelDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DockerWatcher")

class DockerWatcher:
    def __init__(self, db: SentinelDB):
        self.db = db
        try:
            self.client = docker.from_env()
            logger.info("Connected to Docker socket")
        except Exception as e:
            logger.error(f"Docker socket connection failed: {e}")
            raise

    def get_current_containers(self):
        """Fetch current running containers and their metadata."""
        containers = self.client.containers.list()
        snapshot = {}
        for c in containers:
            snapshot[c.id] = {
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else "unknown",
                "status": c.status,
                "ports": c.attrs['NetworkSettings']['Ports']
            }
        return snapshot

    def check_for_drift(self, previous_snapshot):
        """
        The P5 Rule: Detect new containers.
        Returns a list of new container IDs.
        """
        current = self.get_current_containers()
        new_containers = set(current.keys()) - set(previous_snapshot.keys())
        
        for cid in new_containers:
            c_info = current[cid]
            logger.warning(f"[P5 ALERT] Container Drift Detected: {c_info['name']} ({cid})")
            # In a full impl, this would trigger an incident in sentinel_db.incidents
            
        return current, list(new_containers)

    def run_cycle(self, previous_snapshot):
        """A single polling cycle."""
        current, drift = self.check_for_drift(previous_snapshot)
        
        # Log the snapshot to DB
        self.db.save_topology({
            "containers": json.dumps(current),
            "ports": {}, # Populated by host_watcher
            "arp": {}    # Populated by host_watcher
        })
        
        return current, drift
