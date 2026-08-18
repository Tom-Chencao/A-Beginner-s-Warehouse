#!/usr/bin/env python3
"""
FastAPI web dashboard — visualize API key pool usage, add/remove keys.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from key_pool import KeyPool

app = FastAPI(title="Tavily Key Pool Dashboard")
# Loopback-only service; the DSH settings panel (browser) calls these APIs
# cross-origin, so allow all origins (bound to 127.0.0.1 by default).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
pool = KeyPool()

TPL = Path(__file__).resolve().parent / "templates" / "dashboard.html"
DASHBOARD_HTML = TPL.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index():
    return DASHBOARD_HTML


@app.get("/api/stats")
def api_stats():
    stats = pool.get_stats()
    stats["logs"] = pool.get_recent_logs(50)
    return stats


@app.post("/api/keys/add")
def api_keys_add(payload: dict = Body(...)):
    keys = payload.get("keys", [])
    labels = payload.get("labels", [])
    added = pool.add_keys_batch(keys, labels)
    return {"ok": True, "added": added}


@app.post("/api/keys/remove")
def api_keys_remove(payload: dict = Body(...)):
    pool.remove_key(payload["masked"])
    return {"ok": True}


@app.post("/api/keys/deactivate")
def api_keys_deactivate(payload: dict = Body(...)):
    pool.deactivate_key(payload["masked"], payload.get("reason", "manual"))
    return {"ok": True}


@app.post("/api/keys/activate")
def api_keys_activate(payload: dict = Body(...)):
    pool.activate_key(payload["masked"])
    return {"ok": True}


@app.post("/api/health")
def api_health():
    results = pool.check_health_all()
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
