import asyncio
import logging
import json
from datetime import datetime
from db import SentinelDB
from watchers.docker_watcher import DockerWatcher
from watchers.host_watcher import HostWatcher
from notifier import SentinelNotifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("SentinelMain")

class Sentinel:
    def __init__(self):
        self.db = SentinelDB()
        self.docker_watcher = None
        self.host_watcher = None
        self.notifier = SentinelNotifier()
        self.last_docker_snapshot = {}
        self.is_running = True

    async def initialize(self):
        logger.info("Initializing Sentinel Core...")
        self.db.connect()
        self.docker_watcher = DockerWatcher(self.db)
        self.host_watcher = HostWatcher(self.db)
        
        # Initial baseline
        self.last_docker_snapshot = self.docker_watcher.get_current_containers()
        logger.info("Initial baseline established. Sentinel is now active.")

    async def loop(self):
        while self.is_running:
            try:
                logger.info("--- Starting Polling Cycle ---")
                
                # 1. Docker Watcher (P5 Drift Detection)
                current_docker, drift = self.docker_watcher.run_cycle(self.last_docker_snapshot)
                self.last_docker_snapshot = current_docker
                
                # Handle Drift Alerts
                for container_id in drift:
                    c_info = current_docker[container_id]
                    self.notifier.notify_drift(c_info['name'], container_id)
                
                # 2. Host Watcher (Connection Anomaly Detection)
                # We modify the host_watcher logic here to return anomalies instead of just logging
                listening_ports = self.host_watcher.run_cycle()
                
                # Integration Note: The HostWatcher now logs anomalies directly to the DB.
                # We could extend it to return a list of anomalies to trigger immediate alerts.
                
                # 3. Global Topology Update
                self.db.save_topology({
                    "containers": json.dumps(current_docker),
                    "ports": json.dumps(listening_ports),
                    "arp": {} 
                })
                
                logger.info(f"Cycle complete. Containers: {len(current_docker)}, Listening Ports: {len(listening_ports)}")
                
            except Exception as e:
                logger.exception(f"Critical error in polling cycle: {e}")
            
            await asyncio.sleep(60)

    def stop(self):
        self.is_running = False
        self.db.close()

async def main():
    sentinel = Sentinel()
    await sentinel.initialize()
    await sentinel.loop()

if __name__ == "__main__":
    asyncio.run(main())
