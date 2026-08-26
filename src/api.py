from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List
import uvicorn
from db import SentinelDB
from notifier import SentinelNotifier

app = FastAPI(title="Sentinel API")
db = SentinelDB()
notifier = SentinelNotifier()

# Ensure DB is connected on startup
@app.on_event("startup")
async def startup_event():
    db.connect()

@app.get("/status")
async def get_status():
    return {"status": "active", "version": "v1.0-alpha", "db": "connected"}

@app.get("/query/drift")
async def get_drift():
    """Fetch the latest container drift events."""
    query = "SELECT * FROM sentinel_db.topology_snapshots ORDER BY snapshot_ts DESC LIMIT 1"
    snapshot = db.execute(query)
    return {"latest_snapshot": snapshot[0] if snapshot else None}

@app.get("/query/anomalies")
async def get_anomalies(limit: int = 10):
    """Fetch the most recent unrecognized network events."""
    query = "SELECT * FROM sentinel_db.events WHERE source = 'host' ORDER BY ts DESC LIMIT %s"
    return db.execute(query, (limit,))

@app.post("/alert")
async def trigger_alert(severity: str, message: str, context: Optional[str] = None):
    """
    Internal endpoint for watchers to trigger an alert.
    """
    notifier.send_alert(severity, message, context)
    return {"status": "alert_sent"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
