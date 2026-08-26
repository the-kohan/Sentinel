#!/usr/bin/env python3
"""
Sentinel Docker Collector - Standalone script for systemd timer
Collects Docker container state via Docker socket API
Writes JSON to bind-mounted volume for containerized analyzer to consume.
"""

import json
import docker
import logging
import argparse
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] DockerCollector: %(message)s'
)
logger = logging.getLogger("DockerCollector")


class DockerCollector:
    def __init__(self, output_path: Path):
        self.output_path = output_path
        try:
            self.client = docker.from_env()
            logger.info("Connected to Docker socket")
        except Exception as e:
            logger.error(f"Docker socket connection failed: {e}")
            raise

    def get_current_containers(self) -> dict:
        """Fetch current running containers and their metadata."""
        containers = self.client.containers.list()
        snapshot = {}
        for c in containers:
            # Get port bindings
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

    def run(self) -> dict:
        """Run a full collection cycle and return the snapshot."""
        logger.info("Starting Docker collection cycle...")

        snapshot = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "containers": self.get_current_containers()
        }

        logger.info(f"Collected: {len(snapshot['containers'])} containers")

        return snapshot

    def write_output(self, snapshot: dict):
        """Write snapshot to output file atomically."""
        temp_path = self.output_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump(snapshot, f, indent=2)
            temp_path.replace(self.output_path)
            logger.info(f"Written snapshot to {self.output_path}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            if temp_path.exists():
                temp_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Sentinel Docker Collector")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/data/collector/docker-ps.json"),
        help="Output JSON file path"
    )
    args = parser.parse_args()

    collector = DockerCollector(args.output)
    snapshot = collector.run()
    collector.write_output(snapshot)


if __name__ == "__main__":
    main()