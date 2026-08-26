#!/bin/bash
# sentinel/scripts/sentinel.sh - Main Loop (Foundation)

set -e
source "$SENTINEL_ROOT/sentinel.env"

# Initialize Module states
declare -A STRIKES
declare -A CIRCUIT_OPEN_UNTIL

echo "[$(date)] Sentinel V2 Foundation starting..."

while true; do
    # 1. Health Module: Synthetic Checks
    # Example for n8n
    if ! curl -s --head "http://localhost:5678/health" | grep "200 OK" > /dev/null; then
        S_NAME="n8n"
        S_TIME=$(date +%s)
        
        # Circuit Breaker Logic
        if [[ ${CIRCUIT_OPEN_UNTIL[$S_NAME]} && $S_TIME -lt ${CIRCUIT_OPEN_UNTIL[$S_NAME]} ]]; then
            echo "Circuit open for $S_NAME, skipping."
        else
            STRIKES[$S_NAME]=$(( ${STRIKES[$S_NAME]:-0} + 1 ))
            echo "Strike ${STRIKES[$S_NAME]} for $S_NAME"
            
            if [ ${STRIKES[$S_NAME]} -ge 3 ]; then
                CIRCUIT_OPEN_UNTIL[$S_NAME]=$(( $S_TIME + 600 ))
                STRIKES[$S_NAME]=0
                "$SENTINEL_ROOT/scripts/alert.sh" "CRITICAL" "Circuit OPEN for $S_NAME. 3 failures in 5m. Manual intervention required."
                "$SENTINEL_ROOT/scripts/db.sh" "CRITICAL" "Health" "CIRCUIT_OPEN" "Service $S_NAME failed 3 times" "{}"
            else
                docker restart $S_NAME || true
                "$SENTINEL_ROOT/scripts/db.sh" "MEDIUM" "Health" "RESTART" "Restarted $S_NAME (Strike ${STRIKES[$S_NAME]})" "{}"
            fi
        fi
    fi

    # 2. Simple Event Stream Listener (Non-blocking sample)
    # In full V2, this will be a background process piping to db.sh

    sleep 30
done
