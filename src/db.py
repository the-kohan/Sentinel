import os
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor, Json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SentinelDB")


class SentinelDB:
    def __init__(
        self,
        host: str = None,
        dbname: str = None,
        user: str = None,
        password: str = None,
        port: int = 5432
    ):
        # Use Docker DNS names when running in container, fallback to env/localhost
        self.host = host or os.getenv("POSTGRES_HOST", "postgres")
        self.dbname = dbname or os.getenv("POSTGRES_DB", "Kohan")
        self.user = user or os.getenv("POSTGRES_USER", "Kohan")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self._conn = None

    def connect(self):
        try:
            self._conn = psycopg2.connect(
                host=self.host,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                port=self.port
            )
            self._conn.autocommit = True
            
            # Set search_path to sentinel_db schema for all queries
            with self._conn.cursor() as cur:
                cur.execute("SET search_path TO sentinel_db, public;")
            
            logger.info(f"Connected to Sentinel DB at {self.host}:{self.port}/{self.dbname} (schema: sentinel_db)")
        except Exception as e:
            logger.error(f"DB Connection failed: {e}")
            raise

    def execute(self, query: str, params=None):
        """Execute a query and return results as list of dicts."""
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return None

    def execute_batch(self, query: str, data):
        """Execute a batch insert."""
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        with self._conn.cursor() as cur:
            execute_values(cur, query, data)

    def check_allowlist(self, pattern: str) -> bool:
        """Check if a network pattern is in the known_good table."""
        query = "SELECT 1 FROM known_good WHERE pattern = %s"
        res = self.execute(query, (pattern,))
        return len(res) > 0 if res else False

    def add_candidate(self, pattern: str, source: str = "host", reason: str = "auto-observation"):
        """Add unknown pattern as candidate. Expires in 48h for review.
        ON CONFLICT DO NOTHING — duplicates are silently skipped."""
        query = """
            INSERT INTO known_good (pattern, source, reason, added_by, expiry)
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '48 hours')
            ON CONFLICT (pattern) DO NOTHING
        """
        self.execute(query, (pattern, source, reason, "sentinel:observation"))

    def promote_candidate(self, pattern: str):
        """Promote a candidate to permanent allowlist entry (remove expiry)."""
        query = "UPDATE known_good SET expiry = NULL WHERE pattern = %s AND expiry IS NOT NULL"
        self.execute(query, (pattern,))

    def get_expiring_candidates(self, hours: int = 24):
        """Get candidates expiring within N hours for operator review."""
        query = """
            SELECT pattern, source, reason, added_ts, expiry, added_by
            FROM known_good
            WHERE expiry IS NOT NULL
              AND expiry <= NOW() AT TIME ZONE 'UTC' + INTERVAL '%s hours'
              AND expiry > NOW() AT TIME ZONE 'UTC'
            ORDER BY expiry ASC
        """
        return self.execute(query, (str(hours),))

    def expire_candidates(self):
        """Mark all expired candidates as expired (for cleanup/review)."""
        query = "UPDATE known_good SET reason = reason || ' [EXPIRED ' || NOW() AT TIME ZONE 'UTC' || ']' WHERE expiry IS NOT NULL AND expiry <= NOW() AT TIME ZONE 'UTC'"
        self.execute(query)

    def log_event(self, event_data: dict):
        """
        Insert a network event into the events table.
        event_data: dict with keys matching table columns.
        """
        query = """
            INSERT INTO events 
            (source, src_ip, src_port, dst_ip, dst_port, proto, direction, bytes, container_id, service_name, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            event_data.get('source'),
            event_data.get('src_ip'),
            event_data.get('src_port'),
            event_data.get('dst_ip'),
            event_data.get('dst_port'),
            event_data.get('proto'),
            event_data.get('direction'),
            event_data.get('bytes'),
            event_data.get('container_id'),
            event_data.get('service_name'),
            Json(event_data.get('raw_data')) if event_data.get('raw_data') is not None else None
        )
        self.execute(query, params)

    def save_topology(self, snapshot_data: dict):
        """Save a full topology snapshot for drift analysis."""
        query = """
            INSERT INTO topology_snapshots (listening_ports, containers, arp_table)
            VALUES (%s, %s, %s)
        """
        self.execute(query, (
            Json(snapshot_data.get('ports')) if snapshot_data.get('ports') is not None else None,
            Json(snapshot_data.get('containers')) if snapshot_data.get('containers') is not None else None,
            Json(snapshot_data.get('arp')) if snapshot_data.get('arp') is not None else None
        ))

    def close(self):
        if self._conn:
            self._conn.close()
            logger.info("DB connection closed")