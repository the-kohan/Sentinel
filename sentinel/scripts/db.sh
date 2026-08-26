#!/bin/bash
# sentinel/scripts/db.sh - Postgres Helper

set -e
source "$SENTINEL_ROOT/sentinel.env"

function log_event() {
    local severity=$1
    local module=$2
    local type=$3
    local msg=$4
    local meta=$5
    
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "INSERT INTO sentinel_events (severity, module, event_type, message, metadata) VALUES ('$severity', '$module', '$type', '$msg', '$meta');"
}

# If script is called directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    log_event "$1" "$2" "$3" "$4" "$5"
fi
