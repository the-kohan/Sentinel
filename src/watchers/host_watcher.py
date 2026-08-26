import subprocess
import logging
import json
import re
from db import SentinelDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HostWatcher")

class HostWatcher:
    def __init__(self, db: SentinelDB):
        self.db = db

    def _run_cmd(self, cmd):
        try:
            result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {cmd} - Error: {e.output}")
            return ""

    def get_listening_ports(self):
        """
        Uses 'ss -tulpn' to find listening ports.
        Returns a dictionary of {port: process_info}.
        """
        output = self._run_cmd("ss -tulpn")
        ports = {}
        # Skip header, parse lines
        for line in output.splitlines()[1:]:
            # Simple regex to extract local address:port
            match = re.search(r'(\d+\.\d+\.\d+\.\d+|\[::\]|127\.0\.0\.1):(\d+)', line)
            if match:
                ip, port = match.groups()
                # Extract process info from the end of the line
                process_info = line.split('users:')[-1].strip() if 'users:' in line else "unknown"
                ports[port] = {
                    "ip": ip,
                    "process": process_info
                }
        return ports

    def get_active_connections(self):
        """
        Uses 'ss -tun' to find active connections.
        """
        output = self._run_cmd("ss -tun")
        connections = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                # Local: [2] Peer: [3]
                local = parts[4]
                peer = parts[5]
                
                # Split IP and Port
                try:
                    dst_ip, dst_port = peer.rsplit(':', 1)
                except ValueError:
                    continue
                
                connections.append({
                    "dst_ip": dst_ip,
                    "dst_port": int(dst_port),
                    "proto": "tcp" if "tcp" in line else "udp"
                })
        return connections

    def run_cycle(self):
        """Polls the network state and logs anomalies."""
        listening = self.get_listening_ports()
        connections = self.get_active_connections()
        
        for conn in connections:
            # Construct the pattern to check against the allowlist
            # Pattern examples: '127.0.0.53:53'
            pattern = f"{conn['dst_ip']}:{conn['dst_port']}"
            
            if not self.db.check_allowlist(pattern):
                logger.warning(f"[ANOMALY] Unrecognized connection to {pattern}")
                # Log the event for later analysis/incident creation
                self.db.log_event({
                    "source": "host",
                    "dst_ip": conn['dst_ip'],
                    "dst_port": conn['dst_port'],
                    "proto": conn['proto'],
                    "direction": "outbound",
                    "raw_data": {"pattern": pattern}
                })
                
        return listening
