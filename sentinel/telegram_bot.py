#!/usr/bin/env python3
"""
Sentinel Telegram Bot — read-only command handler.
Commands: /status, /anomalies [hours], /drift, /query <text>, /help
"""
import os
import sys
import asyncio
import logging
import requests
from pathlib import Path

# Load sentinel.env (same locations as API)
SENTINEL_ROOT = os.getenv("SENTINEL_ROOT", "/app")
ENV_FILE_CANDIDATES = [
    Path(SENTINEL_ROOT) / "sentinel.env",
    Path(SENTINEL_ROOT) / "sentinel" / "sentinel.env",
]

def load_env():
    for candidate in ENV_FILE_CANDIDATES:
        if candidate.exists():
            with open(candidate) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k, v)
            break

load_env()

API_BASE = os.getenv("SENTINEL_API_URL", "http://localhost:8100")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in sentinel.env", file=sys.stderr)
    sys.exit(1)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinel-telegram")

def tg_send(text: str):
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")

def tg_get_updates(offset: int = 0):
    try:
        r = requests.get(f"{TELEGRAM_API}/getUpdates", params={
            "offset": offset,
            "timeout": 30,
            "allowed_updates": ["message"]
        }, timeout=35)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        logger.error(f"getUpdates failed: {e}")
        return []

def api_get(path: str, params=None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"API {path} failed: {e}")
        return None

def cmd_status():
    data = api_get("/api/status")
    if not data:
        return "❌ API unavailable"
    return (
        f"🟢 *Sentinel Status*\n"
        f"Cycles: {data.get('cycles_completed', '?')}\n"
        f"Containers: {data.get('last_docker_containers', '?')}\n"
        f"Host ports: {data.get('last_host_ports', '?')}\n"
        f"Setup complete: {'✅' if data.get('setup_complete') else '❌'}\n"
        f"Telegram configured: {'✅' if data.get('telegram_configured') else '❌'}"
    )

def cmd_anomalies(hours: int = 1):
    data = api_get("/api/anomalies", {"hours": hours})
    if not data:
        return "❌ API unavailable"
    anomalies = data.get("anomalies", [])
    if not anomalies:
        return f"✅ No anomalies in last {hours}h"
    lines = [f"⚠️ *Anomalies (last {hours}h) — {len(anomalies)}*"]
    for a in anomalies[:8]:
        sev = a.get("severity", "?")
        dst = a.get("dst_ip", "?")
        typ = a.get("type", "?")
        lines.append(f"  `{dst}` — {typ} [{sev}]")
    return "\n".join(lines)

def cmd_drift():
    data = api_get("/api/drift")
    if not data:
        return "❌ API unavailable"
    if not data.get("drift_detected"):
        return "✅ No container drift detected"
    new = data.get("new_containers", [])
    rem = data.get("removed_containers", [])
    lines = ["🔄 *Container Drift Detected*"]
    if new:
        lines.append(f"  New: {', '.join(new)}")
    if rem:
        lines.append(f"  Removed: {', '.join(rem)}")
    return "\n".join(lines)

def cmd_query(text: str):
    data = api_get("/api/query/search", {"q": text, "limit": 10})
    if not data:
        return "❌ API unavailable"
    events = data.get("events", [])
    rep = data.get("reputation", [])
    allow = data.get("allowlist", [])
    lines = [f"🔎 *Query:* `{text}`"]
    if events:
        lines.append(f"\n📊 *Events ({len(events)})*")
        for e in events[:5]:
            src = e.get("src_ip", "?")
            dst = e.get("dst_ip", "?")
            proto = e.get("proto", "?")
            lines.append(f"  `{src} → {dst}` ({proto})")
    if rep:
        lines.append(f"\n👤 *Reputation ({len(rep)})*")
        for r in rep[:5]:
            ident = r.get("identifier", "?")
            verdict = r.get("verdict", "?")
            cnt = r.get("contact_count", 0)
            lines.append(f"  `{ident}` — {verdict} ({cnt} contacts)")
    if allow:
        lines.append(f"\n✅ *Allowlist ({len(allow)})*")
        for a in allow[:5]:
            pat = a.get("pattern", "?")
            src = a.get("source", "?")
            lines.append(f"  `{pat}` • {src}")
    if not events and not rep and not allow:
        lines.append("\n_No matches_")
    return "\n".join(lines)

def cmd_help():
    return (
        "*Sentinel Commands*\n"
        "`/status` — System health\n"
        "`/anomalies [hours]` — Recent anomalies (default 1h)\n"
        "`/drift` — Container drift events\n"
        "`/query <text>` — Search events, reputation, allowlist\n"
        "`/help` — This message"
    )

async def main():
    offset = 0
    logger.info("Sentinel Telegram bot started")
    tg_send("🤖 Sentinel bot online")

    while True:
        updates = tg_get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id != str(TELEGRAM_CHAT_ID):
                continue
            text = msg.get("text", "").strip()
            if not text.startswith("/"):
                continue
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "/status":
                tg_send(cmd_status())
            elif cmd == "/anomalies":
                hours = int(arg) if arg.isdigit() else 1
                tg_send(cmd_anomalies(hours))
            elif cmd == "/drift":
                tg_send(cmd_drift())
            elif cmd == "/query":
                if not arg:
                    tg_send("Usage: `/query <text>`")
                else:
                    tg_send(cmd_query(arg))
            elif cmd == "/help":
                tg_send(cmd_help())
            else:
                tg_send(f"Unknown command: {cmd}\nUse `/help`")

        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")