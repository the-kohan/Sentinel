#!/usr/bin/env python3
"""
Sentinel Observation Watcher v1.0
=============================
Watches Sentinel's analysis cycle and persists observations to disk.
Survives power loss: JSONL format, flushed after each write.

Usage:
    python observer.py                        # Run continuously
    python observer.py --once                 # Single snapshot
    python observer.py --review               # Review candidates before expiry

Configuration:
    SENTINEL_URL      - API endpoint (default: http://127.0.0.1:8100)
    OBSERVER_DATA_DIR - Where to write observation log (default: ./collector-data)
    EXCLUDE_LIST      - Comma-separated patterns to skip (optional)
    OBSERVATION_MODE  - "silent" or "alerting" (default: silent)

Output:
    observation_log.jsonl - One JSON object per line, append-only
    observation_summary.json - Aggregated stats (updated each cycle)

JSONL schema per line:
    {
        "ts": "ISO8601 timestamp",
        "cycle": 123,
        "containers": 14,
        "ports": 18,
        "anomalies": [{"pattern": "...", "connection": {...}}],
        "candidates_added": ["pattern1", "pattern2"],
        "drift_events": [{"name": "...", "id": "..."}],
        "status": "active|error"
    }
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# Configuration
SENTINEL_URL = os.getenv("SENTINEL_URL", "http://127.0.0.1:8100")
OBSERVER_DATA_DIR = os.getenv("OBSERVER_DATA_DIR", "/mnt/e/kohanastack/sentinel/collector-data")
EXCLUDE_LIST_RAW = os.getenv("EXCLUDE_LIST", "")
OBSERVATION_MODE = os.getenv("OBSERVATION_MODE", "silent")  # "silent" or "alerting"

# Parse exclude list
EXCLUDE_SET: set = set()
if EXCLUDE_LIST_RAW:
    EXCLUDE_SET = {p.strip() for p in EXCLUDE_LIST_RAW.split(",") if p.strip()}

LOG_FILE = Path(OBSERVER_DATA_DIR) / "observation_log.jsonl"
SUMMARY_FILE = Path(OBSERVER_DATA_DIR) / "observation_summary.json"


class ObservationWatcher:
    """Watches Sentinel and persists observations to disk."""

    def __init__(self):
        self.cycle_count = 0
        self.total_anomalies = 0
        self.total_candidates = 0
        self.total_drift = 0
        self.start_ts = datetime.now(timezone.utc)
        self._ensure_data_dir()

    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        Path(OBSERVER_DATA_DIR).mkdir(parents=True, exist_ok=True)

    def _log_observation(self, observation: Dict[str, Any], candidates_count: int = 0):
        """Append observation to JSONL log file. Flushed immediately."""
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(observation, default=str) + "\n")
            f.flush()  # Survives power loss — each line is complete

        # Update summary
        self.total_candidates = candidates_count  # Refresh from API each cycle
        self._update_summary(observation)

    def _update_summary(self, observation: Dict[str, Any]):
        """Update the aggregated summary file."""
        summary = {
            "start_ts": self.start_ts.isoformat(),
            "last_update": datetime.now(timezone.utc).isoformat(),
            "total_cycles": self.cycle_count,
            "total_anomalies": self.total_anomalies,
            "total_candidates": self.total_candidates,
            "total_drift_events": self.total_drift,
            "exclude_list": sorted(EXCLUDE_SET),
            "observation_mode": OBSERVATION_MODE,
            "last_observation": {
                "cycle": observation.get("cycle"),
                "containers": observation.get("containers"),
                "ports": observation.get("ports"),
                "anomalies_count": len(observation.get("anomalies", [])),
                "candidates_added": observation.get("candidates_added", []),
            }
        }
        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f, indent=2, default=str)

    def _fetch_status(self) -> Dict[str, Any]:
        """Fetch Sentinel status."""
        try:
            resp = requests.get(f"{SENTINEL_URL}/status", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def _fetch_anomalies(self) -> List[Dict[str, Any]]:
        """Fetch recent anomalies."""
        try:
            resp = requests.get(f"{SENTINEL_URL}/query/anomalies", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    def _fetch_drift(self) -> Dict[str, Any]:
        """Fetch latest drift events."""
        try:
            resp = requests.get(f"{SENTINEL_URL}/query/drift", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {}

    def _fetch_candidates(self) -> List[Dict[str, Any]]:
        """Fetch current observation candidates from DB."""
        try:
            resp = requests.get(f"{SENTINEL_URL}/query/candidates", timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    def should_exclude(self, pattern: str) -> bool:
        """Check if a pattern should be excluded from observation."""
        return pattern in EXCLUDE_SET

    def observe(self) -> Dict[str, Any]:
        """Perform one observation cycle."""
        self.cycle_count += 1

        status = self._fetch_status()
        anomalies = self._fetch_anomalies()
        drift = self._fetch_drift()
        candidates = self._fetch_candidates()

        # Filter excluded patterns
        filtered_anomalies = [
            a for a in anomalies
            if not self.should_exclude(a.get("pattern", ""))
        ]

        # Count stats
        anomaly_count = len(filtered_anomalies)
        candidate_count = len(candidates)
        drift_count = drift.get("total_new", 0) if isinstance(drift, dict) else 0

        self.total_anomalies += anomaly_count
        self.total_candidates = candidate_count
        self.total_drift += drift_count

        observation = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "cycle": self.cycle_count,
            "containers": status.get("last_docker_containers", 0),
            "ports": status.get("last_host_ports", 0),
            "anomalies": filtered_anomalies,
            "candidates_added": candidates,
            "drift_events": drift.get("new_containers", []),
            "status": status.get("status", "unknown"),
            "exclude_filter": {
                "active": bool(EXCLUDE_SET),
                "excluded_patterns": EXCLUDE_SET
            },
            "mode": OBSERVATION_MODE
        }

        self._log_observation(observation, candidates_count=candidate_count)
        return observation

    def run(self, interval: int = 60):
        """Run continuously, observing every `interval` seconds."""
        print(f"=== Sentinel Observation Watcher v1.0 ===")
        print(f"URL: {SENTINEL_URL}")
        print(f"Log: {LOG_FILE}")
        print(f"Mode: {OBSERVATION_MODE}")
        print(f"Exclude list: {EXCLUDE_SET if EXCLUDE_SET else 'none'}")
        print(f"Interval: {interval}s")
        print(f"Press Ctrl+C to stop.\n")

        try:
            while True:
                obs = self.observe()
                print(f"[Cycle {self.cycle_count}] "
                      f"Containers: {obs['containers']}, "
                      f"Ports: {obs['ports']}, "
                      f"Anomalies: {len(obs['anomalies'])}, "
                      f"Candidates: {len(obs['candidates_added'])}, "
                      f"Drift: {obs['drift_events']}")

                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\nWatcher stopped after {self.cycle_count} cycles.")
            print(f"Log: {LOG_FILE}")
            print(f"Summary: {SUMMARY_FILE}")

    def review(self):
        """Review current candidates before expiry."""
        candidates = self._fetch_candidates()
        if not candidates:
            print("No candidates found.")
            return

        print(f"=== Candidates for Review ({len(candidates)} total) ===")
        print(f"{'Pattern':<30} {'Source':<10} {'Reason':<40} {'Expiry':<25}")
        print("-" * 105)

        for c in candidates:
            print(f"{c.get('pattern','?'):<30} "
                  f"{c.get('source','?'):<10} "
                  f"{c.get('reason','?')[:40]:<40} "
                  f"{c.get('expiry','?')[:25]}")

        print(f"\nTo promote a candidate, use: "
              f"curl -X POST {SENTINEL_URL}/promote?pattern=<pattern>")
        print(f"To exclude a pattern, add to EXCLUDE_LIST env var.")


def main():
    parser = argparse.ArgumentParser(description="Sentinel Observation Watcher")
    parser.add_argument("--once", action="store_true", help="Single observation cycle")
    parser.add_argument("--review", action="store_true", help="Review current candidates")
    parser.add_argument("--interval", type=int, default=60, help="Observation interval in seconds")
    args = parser.parse_args()

    watcher = ObservationWatcher()

    if args.review:
        watcher.review()
    elif args.once:
        obs = watcher.observe()
        print(json.dumps(obs, indent=2, default=str))
    else:
        watcher.run(interval=args.interval)


if __name__ == "__main__":
    main()
