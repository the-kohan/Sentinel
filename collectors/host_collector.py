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
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            if isinstance(e, subprocess.CalledProcessError):
                logger.error(f"Command failed: {cmd} - Error: {e.output}")
            else:
                logger.debug(f"Command unavailable: {cmd} ({type(e).__name__})")
            return ""

    def _parse_proc_net(self, path, proto):
        """Parse /proc/net/tcp or /proc/net/udp for socket entries."""
        entries = []
        try:
            with open(path, "r") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    local = parts[1]
                    peer = parts[2]
                    state = parts[3]
                    local_ip_hex, local_port_hex = local.split(":", 1)
                    peer_ip_hex, peer_port_hex = peer.split(":", 1)
                    local_port = int(local_port_hex, 16)
                    peer_port = int(peer_port_hex, 16)
                    local_ip = self._hex_ip_to_str(local_ip_hex)
                    peer_ip = self._hex_ip_to_str(peer_ip_hex)
                    entries.append({
                        "local_ip": local_ip, "local_port": local_port,
                        "dst_ip": peer_ip, "dst_port": peer_port,
                        "proto": proto, "state": state
                    })
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")
        return entries

    def _hex_ip_to_str(self, hex_ip):
        """Convert /proc/net hex IP to dotted string."""
        if len(hex_ip) == 8:
            return ".".join(str(int(hex_ip[i:i+2], 16)) for i in range(0, 8, 2))
        elif len(hex_ip) == 32:
            import socket
            try:
                return socket.inet_ntop(socket.AF_INET6, bytes.fromhex(hex_ip))
            except Exception:
                return "::"
        return hex_ip

    def _get_listening_from_proc(self):
        """Get listening ports from /proc/net (state 0A = LISTEN)."""
        ports = {}
        for proto, path in [("tcp", "/proc/net/tcp"), ("udp", "/proc/net/udp")]:
            for e in self._parse_proc_net(path, proto):
                if e["state"] == "0A":
                    ports[str(e["local_port"])] = {
                        "ip": e["local_ip"], "process": "unknown", "protocol": e["proto"]
                    }
        return ports

    def get_listening_ports(self) -> dict:
        """Uses 'ss -tulpn' (fallback: /proc/net)."""
        output = self._run_cmd("ss -tulpn")
        if output:
            ports = {}
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 5:
                    continue
                local_addr = parts[4]
                match = re.search(r'(\[?[\[\da-fA-F:.]+\]?:)(\d+)$', local_addr)
                if not match:
                    match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)$', local_addr)
                if match:
                    ip, port = match.groups()
                    process_info = "unknown"
                    if 'users:' in line:
                        process_info = line.split('users:')[-1].strip()
                    ports[port] = {"ip": ip, "process": process_info, "protocol": "tcp" if "tcp" in parts[0] else "udp"}
            return ports
        return self._get_listening_from_proc()

    def get_active_connections(self) -> list:
        """Uses 'ss -tun' (fallback: /proc/net/tcp established)."""
        output = self._run_cmd("ss -tun")
        connections = []
        if output:
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue
                try:
                    peer = parts[5]
                    dst_ip, dst_port = peer.rsplit(':', 1)
                    connections.append({
                        "dst_ip": dst_ip.strip('[]'),
                        "dst_port": int(dst_port),
                        "proto": "tcp" if "tcp" in parts[0] else "udp",
                        "local": parts[4]
                    })
                except (ValueError, IndexError):
                    continue
            if connections:
                return connections
        # Fallback: non-listening TCP entries in /proc/net/tcp
        for e in self._parse_proc_net("/proc/net/tcp", "tcp"):
            if e["state"] != "0A":
                connections.append({
                    "dst_ip": e["dst_ip"], "dst_port": e["dst_port"],
                    "proto": e["proto"], "local": f"{e['local_ip']}:{e['local_port']}"
                })
        return connections

    def get_arp_table(self) -> list:
        """Uses 'ip neigh' (fallback: empty list — ARP requires host networking)."""
        output = self._run_cmd("ip neigh")
        if output:
            arp_entries = []
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3] == "lladdr":
                    arp_entries.append({
                        "ip": parts[0], "interface": parts[2],
                        "mac": parts[4], "state": parts[5] if len(parts) > 5 else "unknown"
                    })
            return arp_entries
        return []

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