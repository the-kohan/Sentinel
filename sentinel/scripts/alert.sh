#!/bin/bash
# sentinel/scripts/alert.sh - Direct Telegram Router

set -e
source "$SENTINEL_ROOT/sentinel.env"

SEVERITY=$1
MESSAGE=$2

# Rate limiting for non-critical alerts
if [ "$SEVERITY" != "CRITICAL" ]; then
    LAST_ALERT_FILE="/tmp/sentinel_last_alert"
    if [ -f "$LAST_ALERT_FILE" ]; then
        LAST_TIME=$(cat "$LAST_ALERT_FILE")
        NOW=$(date +%s)
        if [ $((NOW - LAST_TIME)) -lt 300 ]; then
            exit 0 # Suppress
        fi
    fi
    date +%s > "$LAST_ALERT_FILE"
fi

PAYLOAD="{\"chat_id\": \"$TELEGRAM_CHAT_ID\", \"text\": \"🚨 *SENTINEL $SEVERITY*\n\n$MESSAGE\", \"parse_mode\": \"Markdown\"}"
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" -d "$PAYLOAD" > /dev/null
