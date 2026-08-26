-- Sentinel Database Schema Implementation
-- Target: sentinel_db schema within Kohan database
-- Updated for containerized deployment (no TimescaleDB, vanilla pgvector/pgvector:pg16)

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS sentinel_db;

SET search_path TO sentinel_db;

-- Enable pgvector extension for source reputation embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Events Table (The main firehose)
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
    pattern TEXT UNIQUE NOT NULL, -- e.g., '<LOCAL_DNS_IP>:53', 'container:<SERVICE_NAME>'
    source TEXT,
    reason TEXT,
    added_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT, -- 'operator' or 'observation_48h'
    expiry TIMESTAMP WITH TIME ZONE
);

-- 3. Topology Snapshots (For Drift Detection)
CREATE TABLE IF NOT EXISTS topology_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    listening_ports JSONB,
    containers JSONB,
    arp_table JSONB,
    diff_against_previous JSONB
);

-- 4. Incidents (The Triage Log)
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

-- 5. Source Reputation (with pgvector embeddings)
CREATE TABLE IF NOT EXISTS source_reputation (
    id SERIAL PRIMARY KEY,
    identifier TEXT UNIQUE NOT NULL, -- IP or Subnet
    embedding VECTOR(768), -- pgvector for similarity search
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

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_src_ip ON events(src_ip);
CREATE INDEX IF NOT EXISTS idx_events_dst_ip ON events(dst_ip);
CREATE INDEX IF NOT EXISTS idx_known_good_pattern ON known_good(pattern);
-- GIN index for JSONB queries on raw_data
CREATE INDEX IF NOT EXISTS idx_events_raw_data ON events USING GIN (raw_data);
-- Index for source_reputation lookups
CREATE INDEX IF NOT EXISTS idx_source_reputation_identifier ON source_reputation(identifier);