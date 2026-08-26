#!/usr/bin/env python3
"""
Sentinel Host Collector - Standalone script for systemd timer
Collects host network state (listening ports, active connections) via ss/ip commands
Writes JSON to bind-mounted volume for containerized analyzer to consume.
"""

import json
import subprocess
import re
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] HostCollector: %(message)s'
)
logger = logging.getLogger("HostCollector")


class HostCollector:
    def __init__(self, output_path: Path):
        self.output_path = output_path

    def _run_cmd(self, cmd: str) -> str:
        """Run shell command and return stdout, or empty string on failure."""
        try:
            result = subprocess.check_output(
                cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=10
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd} - Error: {e.output}")
            return ""
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {cmd}")
            return ""

    def get_listening_ports(self) -> dict:
        """Uses 'ss -tulpn' to find listening ports."""
        output = self._run_cmd("ss -tulpn")
        ports = {}
        for line in output.splitlines()[1:]:  # Skip header
            # Parse: Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
            # Example: tcp LISTEN 0 128 127.0.0.1:5432 0.0.0.0:* users:(("postgres",pid=123,fd=4))
            parts = line.split()
            if len(parts) < 5:
                continue

            local_addr = parts[4]
            # Extract IP and port - handle IPv4, IPv6, and interface suffixes like %lo
            # Matches: 127.0.0.1:5432, 127.0.0.53%lo:53, [::1]:323, <WSL2_DNS_IP>:53
            match = re.search(r'(\[?[\da-fA-F:.]+(?:\%\w+)?\]?):(\d+)$', local_addr)
            if not match:
                continue

            ip, port = match.groups()

            # Extract process info
            process_info = "unknown"
            if 'users:' in line:
                users_part = line.split('users:')[-1].strip()
                process_info = users_part

            ports[port] = {
                "ip": ip,
                "process": process_info,
                "protocol": "tcp" if "tcp" in parts[0] else "udp"
            }

        return ports

    def get_active_connections(self) -> list:
        """Uses 'ss -tun' to find active connections."""
        output = self._run_cmd("ss -tun")
        connections = []
        for line in output.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) < 6:
                continue

            # Format: Netid State Recv-Q Send-Q Local:Port Peer:Port
            # peer can be: 127.0.0.1:5432, 127.0.0.53%lo:53, [::1]:323
            peer = parts[5]

            # Parse destination IP and port - handle IPv4, IPv6, interface suffixes
            try:
                dst_ip, dst_port = peer.rsplit(':', 1)
                # Clean up IPv6 brackets
                dst_ip = dst_ip.strip('[]')
            except ValueError:
                continue

            proto = "tcp" if "tcp" in parts[0] else "udp"

            # Local address is in parts[4]
            local = parts[4]
            connections.append({
                "dst_ip": dst_ip,
                "dst_port": int(dst_port),
                "proto": proto,
                "local": local
            })

        return connections

    def get_arp_table(self) -> list:
        """Uses 'ip neigh' to get ARP/neighbor table (modern replacement for arp)."""
        output = self._run_cmd("ip neigh")
        arp_entries = []
        for line in output.splitlines():
            # Format: 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "lladdr":
                arp_entries.append({
                    "ip": parts[0],
                    "interface": parts[2],
                    "mac": parts[4],
                    "state": parts[5] if len(parts) > 5 else "unknown"
                })
        return arp_entries

    def run(self) -> dict:
        """Run a full collection cycle and return the snapshot."""
        logger.info("Starting host collection cycle...")

        snapshot = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "listening_ports": self.get_listening_ports(),
            "active_connections": self.get_active_connections(),
            "arp_table": self.get_arp_table()
        }

        logger.info(f"Collected: {len(snapshot['listening_ports'])} listening ports, "
                    f"{len(snapshot['active_connections'])} active connections, "
                    f"{len(snapshot['arp_table'])} ARP entries")

        return snapshot

    def write_output(self, snapshot: dict):
        """Write snapshot to output file atomically."""
        # Write to temp file then rename for atomicity
        temp_path = self.output_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump(snapshot, f, indent=2)
            # Use os.replace for cross-platform atomic rename
            import os
            os.replace(temp_path, self.output_path)
            logger.info(f"Written snapshot to {self.output_path}")
        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if temp_path.exists():
                temp_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Sentinel Host Network Collector")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/data/collector/host-ss.json"),
        help="Output JSON file path"
    )
    args = parser.parse_args()

    collector = HostCollector(args.output)
    snapshot = collector.run()
    collector.write_output(snapshot)


if __name__ == "__main__":
    main()