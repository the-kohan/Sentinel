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
        except FileNotFoundError:
            # Command not available (e.g. ss/ip in slim containers) - fall through to /proc
            return ""

    def _parse_proc_net(self, path, proto):
        """Parse /proc/net/tcp or /proc/net/udp for socket info."""
        result = []
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
                    # state filtering happens in callers, not here
                    result.append({
                        "local_ip": local_ip,
                        "local_port": local_port,
                        "dst_ip": peer_ip,
                        "dst_port": peer_port,
                        "proto": proto,
                        "state": state
                    })
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")
        return result

    def _hex_ip_to_str(self, hex_ip):
        """Convert /proc/net hex IP to dotted string."""
        if len(hex_ip) == 8:
            return ".".join(str(int(hex_ip[i:i+2], 16)) for i in range(0, 8, 2))
        elif len(hex_ip) == 32:
            import socket, struct
            try:
                return socket.inet_ntop(socket.AF_INET6, bytes.fromhex(hex_ip))
            except Exception:
                return "::"
        return hex_ip

    def _get_listening_from_proc(self):
        """Get listening ports from /proc/net/tcp and udp (state 0A = LISTEN)."""
        ports = {}
        for proto, path in [("tcp", "/proc/net/tcp"), ("udp", "/proc/net/udp")]:
            for entry in self._parse_proc_net(path, proto):
                if entry["state"] == "0A":  # LISTEN
                    ports[str(entry["local_port"])] = {
                        "ip": entry["local_ip"],
                        "process": "unknown",
                        "protocol": proto
                    }
        return ports

    def get_listening_ports(self):
        """Find listening ports via ss (preferred) or /proc/net fallback."""
        output = self._run_cmd("ss -tulpn")
        if output:
            ports = {}
            for line in output.splitlines()[1:]:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+|[::1?]+):(\d+)', line)
                if match:
                    ip, port = match.groups()
                    process_info = line.split('users:')[-1].strip() if 'users:' in line else "unknown"
                    ports[port] = {"ip": ip, "process": process_info}
            return ports
        # Fallback: parse /proc/net
        return self._get_listening_from_proc()

    def get_active_connections(self):
        """Find active connections via ss (preferred) or /proc/net fallback."""
        output = self._run_cmd("ss -tun")
        connections = []
        if output:
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        peer = parts[5]
                        dst_ip, dst_port = peer.rsplit(':', 1)
                        connections.append({
                            "dst_ip": dst_ip.strip('[]'),
                            "dst_port": int(dst_port),
                            "proto": "tcp" if "tcp" in parts[0] else "udp"
                        })
                    except (ValueError, IndexError):
                        continue
            if connections:
                return connections
        # Fallback: parse /proc/net (only TCP established)
        for entry in self._parse_proc_net("/proc/net/tcp", "tcp"):
            if entry["state"] not in ("0A",):  # non-listening
                connections.append({
                    "dst_ip": entry["dst_ip"],
                    "dst_port": entry["dst_port"],
                    "proto": entry["proto"]
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
