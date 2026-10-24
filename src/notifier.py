import logging
import os
import requests
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import configparser

logger = logging.getLogger("SentinelNotifier")

EAT = ZoneInfo("Africa/Nairobi")

# Dry-run affordance: with NOTIFY_DRY_RUN set, or this file present, alerts are
# logged instead of delivered. Checked per call, so the file can be created and
# removed without restarting the container. Used to exercise alert paths on
# purpose without paging the operator.
_DRY_RUN_PATHS = [
    Path("/data/collector/.alert-dry-run"),
    Path(os.getenv("SENTINEL_ROOT", "/app")) / "collector-data" / ".alert-dry-run",
]

# Quiet hours: 18:00-08:59 EAT Mon-Fri, all weekend
QUIET_START = dtime(18, 0)
QUIET_END = dtime(8, 59)
QUIET_DAYS = {0, 1, 2, 3, 4}  # Mon-Fri (0=Monday in Python)


_ENV_FILE_CANDIDATES = [
    Path(os.getenv("SENTINEL_ROOT", "/app")) / "sentinel.env",
    Path(os.getenv("SENTINEL_ROOT", "/app")) / "sentinel" / "sentinel.env",
    Path(__file__).resolve().parent.parent / "sentinel" / "sentinel.env",
]


def _load_env_file(path: str = None) -> dict:
    """Load key=value pairs from sentinel.env (fallback when Docker env is stale).

    The image copies sentinel/ to /app/sentinel/, so the file is
    /app/sentinel/sentinel.env — the single path this used to check
    (/app/sentinel.env) never existed, making the fallback a no-op.
    """
    result = {}
    for env_path in ([Path(path)] if path else _ENV_FILE_CANDIDATES):
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        result[key.strip()] = val.strip()
            break  # first readable file wins
        except (FileNotFoundError, OSError):
            continue
    return result


class SentinelNotifier:
    def __init__(self, db=None):
        # Alert gateway. Historically OpenClaw on :18789, moving to Hermes on
        # :8888. SENTINEL_WEBHOOK_URL wins outright when set, so the target can
        # be repointed without touching code.
        self.gateway_url = os.getenv("OPENCLAW_GATEWAY_URL", "http://openclaw:18789")
        self.hook_token = os.getenv("OPENCLAW_HOOK_TOKEN", "")
        self.webhook_path = os.getenv("SENTINEL_WEBHOOK_PATH", "/hooks/sentinel")
        self.webhook_url = (
            os.getenv("SENTINEL_WEBHOOK_URL") or f"{self.gateway_url}{self.webhook_path}"
        )
        self.db = db

    def _post_webhook(self, payload: dict) -> bool:
        """POST to the configured alert gateway (OpenClaw, or Hermes)."""
        url = self.webhook_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.hook_token}" if self.hook_token else ""
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            logger.info(f"Webhook delivered: {resp.status_code}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to deliver webhook to {url}: {e}")
            return False

    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        now = datetime.now(EAT)
        current_time = now.time()
        weekday = now.weekday()  # 0=Monday

        if weekday not in QUIET_DAYS:
            return True  # Weekend = always quiet

        if QUIET_START <= current_time or current_time <= QUIET_END:
            return True
        return False

    def is_muted(self, target: str) -> bool:
        """Check if target is currently muted."""
        if not self.db:
            return False
        try:
            query = "SELECT 1 FROM mute_window WHERE target = %s AND muted_until_ts > NOW() AT TIME ZONE 'UTC'"
            res = self.db.execute(query, (target,))
            return len(res) > 0 if res else False
        except Exception as e:
            logger.warning(f"Mute check failed: {e}")
            return False

    def _dry_run(self) -> bool:
        """True when alerts should be logged rather than delivered."""
        if os.getenv("NOTIFY_DRY_RUN"):
            return True
        return any(path.exists() for path in _DRY_RUN_PATHS)

    def should_suppress(self, severity: str, target: str = None) -> bool:
        """
        Determine if an alert should be suppressed.
        P5 (container drift) never suppressed.
        P3-P4 suppressed during quiet hours.
        Any severity suppressed if target is muted (but P5 wins over mute).
        """
        if severity == "P5":
            return False  # Never suppress P5

        if target and self.is_muted(target):
            logger.info(f"Alert suppressed: {target} is muted")
            return True

        if severity in ("P3", "P4") and self.is_quiet_hours():
            logger.info(f"Alert suppressed: {severity} during quiet hours")
            return True

        return False

    def send_alert(self, severity: str, message: str, context: str = None, incident_id: str = None, target: str = None):
        """
        Sends a formatted alert to the operator via OpenClaw webhook.
        The webhook routes to the 'sentinel' agent which formats and sends to Telegram.
        """
        if self.should_suppress(severity, target):
            return False

        if self._dry_run():
            logger.warning(
                f"[DRY RUN] {severity} alert NOT delivered "
                f"(target={target}): {message[:160]!r}"
            )
            return True

        severity_map = {
            "P1": "🔴 CRITICAL",
            "P2": "🟠 HIGH",
            "P3": "🟡 MEDIUM",
            "P4": "🔵 INFO",
            "P5": "🔥 IMMEDIATE ACTION"
        }

        prefix = severity_map.get(severity, "⚠️ ALERT")

        formatted_message = f"*{prefix}* - Sentinel Network Guard\n\n{message}"
        if context:
            formatted_message += f"\n\n*Context:* `{context}`"

        formatted_message += f"\n\n_Timestamp: {datetime.now(EAT).strftime('%Y-%m-%d %H:%M:%S')} EAT_"

        # Payload for OpenClaw hook -> agent
        payload = {
            "severity": severity,
            "message": formatted_message,
            "context": context,
            "incident_id": incident_id,
            "source": "sentinel",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Sending {severity} alert via OpenClaw webhook")
        success = self._post_webhook(payload)

        if not success:
            logger.error(f"ALERT DELIVERY FAILED: {severity} - {message[:100]}")
            # Fallback: direct Telegram
            self._fallback_telegram(severity, formatted_message)

        return success

    def _fallback_telegram(self, severity: str, message: str):
        """Direct Telegram fallback when webhook fails. Reads from env file as fallback."""
        try:
            token = os.getenv("TELEGRAM_TOKEN")
            chat_id = os.getenv("TELEGRAM_CHAT_ID")
            # Fallback: read from sentinel.env file if env vars are stale
            if not token or not chat_id:
                env_vars = _load_env_file()
                token = token or env_vars.get("TELEGRAM_TOKEN")
                chat_id = chat_id or env_vars.get("TELEGRAM_CHAT_ID")
            if token and chat_id:
                import http.client
                import json
                payload = json.dumps({
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }).encode("utf-8")
                conn = http.client.HTTPSConnection("api.telegram.org", timeout=10)
                conn.request(
                    "POST",
                    f"/bot{token}/sendMessage",
                    body=payload,
                    headers={"Content-Type": "application/json"}
                )
                resp = conn.getresponse()
                data = resp.read().decode("utf-8")
                if resp.status != 200 or '"ok":false' in data:
                    logger.error(f"Fallback Telegram failed: {data[:200]}")
                else:
                    logger.info(f"Fallback Telegram sent for {severity}")
                conn.close()
        except Exception as e:
            logger.error(f"Fallback Telegram failed: {e}")

    def notify_drift(self, container_name: str, container_id: str):
        """P5: New container appeared on the mesh."""
        msg = (
            f"⚠️ *Container Drift Detected!*\n\n"
            f"New container has appeared on the `kohana` mesh:\n\n"
            f"*Name:* {container_name}\n"
            f"*ID:* `{container_id}`"
        )
        self.send_alert("P5", msg, context="Network Topology Change", target=f"container:{container_name}")

    def notify_anomaly(self, pattern: str):
        """P3: Unrecognized outbound connection."""
        msg = (
            f"🔍 *Unrecognized Connection*\n\n"
            f"An outbound request was made to an unknown destination:\n\n"
            f"`{pattern}`"
        )
        self.send_alert("P3", msg, context="Network Anomaly", target=pattern)