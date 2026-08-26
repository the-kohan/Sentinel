# 03 Database — As Built

> **Source:** Live `init_schema.sql` + `SELECT * FROM sentinel_db.*`  
> **Purpose:** Recreate the exact DB schema and seed the allowlist.

---

## Schema

```sql
CREATE SCHEMA IF NOT EXISTS sentinel_db;
SET search_path TO sentinel_db;
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Events Table
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL, -- 'docker', 'host', 'pcap'
    src_ip INET,
    src_port INTEGER,
    dst_ip INET,
    dst_port INTEGER,
    proto TEXT,
    direction TEXT, -- 'inbound', 'outbound'
    bytes BIGINT,
    container_id TEXT,
    service_name TEXT,
    raw_data JSONB
);

-- 2. Known Good (Allowlist)
CREATE TABLE IF NOT EXISTS known_good (
    id SERIAL PRIMARY KEY,
    pattern TEXT UNIQUE NOT NULL,
    source TEXT,
    reason TEXT,
    added_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT, -- 'operator' or 'sentinel:observation'
    expiry TIMESTAMP WITH TIME ZONE
);

-- 3. Topology Snapshots
CREATE TABLE IF NOT EXISTS topology_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    listening_ports JSONB,
    containers JSONB,
    arp_table JSONB,
    diff_against_previous JSONB
);

-- 4. Incidents
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    opened_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_ts TIMESTAMP WITH TIME ZONE,
    severity INTEGER, -- P1 to P5
    summary TEXT,
    related_events BIGINT[],
    llm_assessment TEXT,
    operator_acknowledged BOOLEAN DEFAULT FALSE,
    operator_note TEXT,
    recommended_action TEXT
);

-- 5. Source Reputation
CREATE TABLE IF NOT EXISTS source_reputation (
    id SERIAL PRIMARY KEY,
    identifier TEXT UNIQUE NOT NULL,
    embedding VECTOR(768),
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE,
    contact_count BIGINT DEFAULT 0,
    verdict TEXT CHECK (verdict IN ('benign', 'unknown', 'suspicious')),
    note TEXT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Mute Window
CREATE TABLE IF NOT EXISTS mute_window (
    id SERIAL PRIMARY KEY,
    target TEXT NOT NULL,
    muted_until_ts TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT,
    created_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_src_ip ON events(src_ip);
CREATE INDEX IF NOT EXISTS idx_events_dst_ip ON events(dst_ip);
CREATE INDEX IF NOT EXISTS idx_known_good_pattern ON known_good(pattern);
CREATE INDEX IF NOT EXISTS idx_events_raw_data ON events USING GIN (raw_data);
CREATE INDEX IF NOT EXISTS idx_source_reputation_identifier ON source_reputation(identifier);
```

---

## Live Table State (2026-08-26)

| Table | Rows | Notes |
|---|---|---|
| `events` | 750 | Accumulated host + docker events |
| `known_good` | 13 | 10 operator + 3 observation candidates |
| `topology_snapshots` | 16 | Hourly snapshots |
| `incidents` | 0 | Empty |
| `mute_window` | 0 | Empty |
| `source_reputation` | 0 | Empty — no embeddings yet |

---

## Example Allowlist

> **Note:** These are example patterns for template purposes only.
> Do not commit your actual `known_good` contents. Populate this table after your own 48h observation phase.

| pattern | source | added_by | expiry |
|---|---|---|---|
| `127.0.0.53:53` | System DNS | operator | — |
| `127.0.0.54:53` | System DNS | operator | — |
| `<WSL2_DNS_IP>:53` | WSL2 DNS | operator | — |
| `container:<EXAMPLE_SERVICE_1>` | Docker | operator | — |
| `container:<EXAMPLE_SERVICE_2>` | Docker | operator | — |
| `container:<EXAMPLE_SERVICE_3>` | Docker | operator | — |
| `container:<EXAMPLE_SERVICE_4>` | Docker | operator | — |
| `container:<EXAMPLE_SERVICE_5>` | Docker | operator | — |
| `container:<EXAMPLE_SERVICE_6>` | Docker | operator | — |
| `127.0.0.1` | Loopback | operator | — |

---

## Seed SQL

Run against `postgres` container after schema creation:

```bash
cat init_schema.sql | docker exec -i postgres psql -U Kohan -d Kohan
cat seed_allowlist.sql | docker exec -i postgres psql -U Kohan -d Kohan
```
