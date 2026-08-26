# 07 Alerting — As Built

> **Source:** Live `src/notifier.py`, `docker logs sentinel`, `03_Alerting.md`  
> **Purpose:** Rebuild the alerting layer and understand current delivery state.

---

## Alert Delivery Chain

```text
Sentinel Analyzer
    │
    ├─ P5: check_docker_drift() → notify_drift()
    └─ P3: check_host_anomalies() → notify_anomaly()
            │
            ▼
      SentinelNotifier.send_alert()
            │
            ├─ should_suppress(severity, target)
            │     ├─ P5 → NEVER suppress
            │     ├─ P3/P4 + quiet hours → suppress
            │     └─ P3/P4 + muted target → suppress
            │
            ▼
      _post_webhook(payload) → OpenClaw /hooks/sentinel
            │
            ├─ Success → done
            └─ Failure → _fallback_telegram()
                         └─ Direct Telegram API
```

---

## Alert Types

### P5 — Container Drift

**Trigger:** `notify_drift(container_name, container_id)`  
**Never suppressed.** Fires during quiet hours, fires even if target is muted.

**Message format:**
```
⚠️ *Container Drift Detected!*

New container has appeared on the `kohana` mesh:

*Name:* <container_name>
*ID:* `<container_id>`
```

**Context:** `Network Topology Change`

---

### P3 — Unrecognized Connection

**Trigger:** `notify_anomaly(pattern)`  
**May be suppressed:** during quiet hours, or if target pattern is muted.

**Message format:**
```
🔍 *Unrecognized Connection*

An outbound request was made to an unknown destination:

`<pattern>`
```

**Context:** `Network Anomaly`

---

## Severity Levels

| Level | Emoji | Use | Suppressible |
|---|---|---|---|
| P1 | 🔴 CRITICAL | Service down, data loss | Yes |
| P2 | 🟠 HIGH | Serious degradation | Yes |
| P3 | 🟡 MEDIUM | Unrecognized connection | Yes |
| P4 | 🔵 INFO | Informational | Yes |
| P5 | 🔥 IMMEDIATE ACTION | Container drift | **Never** |

---

## Quiet Hours

**Implemented in:** `src/notifier.py` — `is_quiet_hours()`

| Rule | Behavior |
|---|---|
| Weekdays (Mon-Fri) | 18:00–08:59 EAT → P3, P4 suppressed |
| Weekends | All day → P3, P4 suppressed |
| P5 (container drift) | Always fires regardless of quiet hours or mute |

**Timezone:** EAT (`Africa/Nairobi`)  
**Code:** `ZoneInfo("Africa/Nairobi")`

---

## /mute Command

**Implemented in:** `src/analyzer.py` — `POST /mute`, `GET /mute`, `DELETE /mute/{target}`

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/mute?target=<target>&duration=<dur>&reason=<text>` | Create mute window |
| `GET` | `/mute` | List active mutes |
| `DELETE` | `/mute/<target>` | Remove mute window |

**Duration format:** `30m`, `1h`, `2d`  
**Target formats:** `container:n8n`, `127.0.0.1:52878`, `192.168.1.100`

**Behavior:**
- P3-P4 suppressed if target is muted
- P5 never suppressed, even if target is muted
- Auto-expiring — never permanent
- Stored in `sentinel_db.mute_window` table

---

## OpenClaw Webhook (Primary)

**Endpoint:** `POST http://openclaw:18789/hooks/sentinel`  
**Auth:** `Authorization: Bearer <OPENCLAW_HOOK_TOKEN>`  
**Current status:** ❌ Returns **404** — OpenClaw serves web UI only, no webhook endpoints exposed

---

## Telegram Fallback (Secondary)

**Implemented in:** `src/notifier.py` — `_fallback_telegram()`  
**Current status:** ⚠️ Blocked — `TELEGRAM_TOKEN` is a placeholder, not a real bot token

**Token location:** `sentinel/sentinel.env`  
**Chat ID:** `5694077582`

---

## Shell Script Fallback

**File:** `sentinel/scripts/alert.sh`  
Direct Telegram router with rate limiting. Same token issue as Python fallback.

---

## Current Alerting Status

| Component | Status | Notes |
|---|---|---|
| Notifier code | ✅ Complete | Quiet hours + mute + webhook + Telegram fallback |
| OpenClaw webhook | ❌ 404 | `/hooks/sentinel` not exposed |
| Telegram fallback | ❌ Blocked | Token is placeholder |
| Quiet hours | ✅ Working | P3 suppressed during quiet hours, P5 always fires |
| /mute | ✅ Working | POST/GET/DELETE, P5 overrides mute |
| Alert delivery | ⚠️ Blocked | Needs real Telegram token or OpenClaw webhook support |

---

## Known Bug

From live logs:
```
psycopg2.ProgrammingError: can't adapt type 'dict'
```

This occurs in `check_docker_drift()` when logging drift events to the DB. The `raw_data` dict is not being wrapped in `Json()` before insertion, causing the cycle to fail on every drift detection.

**Impact:** P5 alerts still fire (via `notify_drift()`), but the corresponding DB event insert fails. This means drift events are not persisted to the `events` table.
