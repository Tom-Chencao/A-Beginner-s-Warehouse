"""
Tavily API Key Pool — SQLite-backed key rotation, usage tracking, load balancing.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "tavily_keys.db"


@dataclass
class ApiKey:
    key: str
    masked: str
    label: str
    is_active: bool
    request_count: int
    error_count: int
    credits_used: int
    credits_limit: int
    last_used_at: float
    added_at: float
    last_error: str

    @property
    def usage_pct(self) -> float:
        if self.credits_limit <= 0:
            return 0.0
        return (self.credits_used / self.credits_limit) * 100


class KeyPool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str | None = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | None = None):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._db = db_path or str(DB_PATH)
        self._local = threading.local()
        self._next_index = 0
        self._index_lock = threading.Lock()
        self._init_db()

    # ── DB helpers ──────────────────────────────────────────────
    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=3000")
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self._db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                masked TEXT NOT NULL,
                label TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                request_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                credits_used INTEGER DEFAULT 0,
                credits_limit INTEGER DEFAULT 0,
                last_used_at REAL DEFAULT 0,
                added_at REAL NOT NULL,
                last_error TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_masked TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                credits_consumed INTEGER DEFAULT 0,
                success INTEGER DEFAULT 1,
                error_msg TEXT DEFAULT '',
                latency_ms REAL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    # ── Key CRUD ────────────────────────────────────────────────
    def add_key(self, key: str, label: str = "") -> ApiKey:
        key = key.strip()
        masked = _mask(key)
        now = time.time()
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO api_keys (key, masked, label, added_at) VALUES (?,?,?,?)",
                (key, masked, label, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Key {masked} already exists")
        return self.get_key(masked)

    def add_keys_batch(self, keys: list[str], labels: list[str] | None = None) -> int:
        added = 0
        if labels is None:
            labels = [""] * len(keys)
        conn = self._get_conn()
        now = time.time()
        for i, k in enumerate(keys):
            k = k.strip()
            if not k:
                continue
            masked = _mask(k)
            lbl = labels[i] if i < len(labels) else ""
            try:
                conn.execute(
                    "INSERT INTO api_keys (key, masked, label, added_at) VALUES (?,?,?,?)",
                    (k, masked, lbl, now),
                )
                added += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
        return added

    def remove_key(self, masked_or_key: str):
        conn = self._get_conn()
        if "****" in masked_or_key:
            conn.execute("DELETE FROM api_keys WHERE masked = ?", (masked_or_key,))
        else:
            conn.execute("DELETE FROM api_keys WHERE key = ?", (masked_or_key,))
        conn.commit()

    def deactivate_key(self, masked: str, reason: str = ""):
        conn = self._get_conn()
        conn.execute(
            "UPDATE api_keys SET is_active=0, last_error=? WHERE masked=?",
            (reason, masked),
        )
        conn.commit()

    def activate_key(self, masked: str):
        conn = self._get_conn()
        conn.execute("UPDATE api_keys SET is_active=1, error_count=0 WHERE masked=?", (masked,))
        conn.commit()

    def list_keys(self) -> list[ApiKey]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM api_keys ORDER BY added_at DESC"
        ).fetchall()
        return [_row_to_apikey(r) for r in rows]

    def get_key(self, masked: str) -> ApiKey | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM api_keys WHERE masked=?", (masked,)
        ).fetchone()
        return _row_to_apikey(row) if row else None

    def get_key_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM api_keys WHERE is_active=1").fetchone()
        return row["cnt"]

    # ── Load balancing ─────────────────────────────────────────
    def next_key(self) -> tuple[str, str] | None:
        """Return (raw_key, masked) of next key via round-robin among active keys."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, masked FROM api_keys WHERE is_active=1 ORDER BY last_used_at ASC"
        ).fetchall()
        if not rows:
            return None
        with self._index_lock:
            idx = self._next_index % len(rows)
            self._next_index = (idx + 1) % len(rows)
        row = rows[idx]
        return (row["key"], row["masked"])

    def next_key_least_used(self) -> tuple[str, str] | None:
        """Return key with fewest requests today."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT key, masked FROM api_keys WHERE is_active=1 ORDER BY request_count ASC, last_used_at ASC"
        ).fetchall()
        if not rows:
            return None
        row = rows[0]
        return (row["key"], row["masked"])

    # ── Usage recording ────────────────────────────────────────
    def record_request(self, masked: str, endpoint: str, latency_ms: float, success: bool,
                       credits: int = 0, error_msg: str = ""):
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            "UPDATE api_keys SET request_count=request_count+1, last_used_at=? WHERE masked=?",
            (now, masked),
        )
        if success:
            conn.execute(
                "UPDATE api_keys SET credits_used=credits_used+? WHERE masked=?",
                (credits, masked),
            )
        else:
            conn.execute(
                "UPDATE api_keys SET error_count=error_count+1, last_error=? WHERE masked=?",
                (error_msg[:500], masked),
            )
        conn.execute(
            "INSERT INTO request_log (key_masked, endpoint, credits_consumed, success, error_msg, latency_ms, created_at) VALUES (?,?,?,?,?,?,?)",
            (masked, endpoint, credits, 1 if success else 0, error_msg[:500], latency_ms, now),
        )
        conn.commit()

    # ── Health check ────────────────────────────────────────────
    def check_health(self, key_masked: str | None = None) -> list[dict]:
        """Probe one or all active keys with a lightweight search. Auto-deactivate dead keys."""
        results = []
        keys = [self.get_key(key_masked)] if key_masked else self.list_keys()
        for k in keys:
            if not k or not k.is_active:
                continue
            try:
                from tavily import TavilyClient
                t0 = time.time()
                client = TavilyClient(k.key)
                resp = client.search("test", max_results=1, search_depth="basic", timeout=5)
                elapsed = (time.time() - t0) * 1000
                ok = "results" in resp and len(resp.get("results", [])) > 0
                if ok:
                    results.append({"masked": k.masked, "alive": True, "latency_ms": round(elapsed)})
                else:
                    results.append({"masked": k.masked, "alive": False, "error": "empty response"})
                    self.deactivate_key(k.masked, "health-check: empty response")
            except Exception as e:
                err = str(e)
                results.append({"masked": k.masked, "alive": False, "error": err})
                self.deactivate_key(k.masked, f"health-check: {err[:200]}")
        return results

    def check_health_all(self) -> list[dict]:
        return self.check_health()

    # ── Stats ───────────────────────────────────────────────────
    def get_stats(self) -> dict:
        conn = self._get_conn()
        keys = self.list_keys()
        total_requests = sum(k.request_count for k in keys)
        total_errors = sum(k.error_count for k in keys)
        total_credits = sum(k.credits_used for k in keys)
        active_count = sum(1 for k in keys if k.is_active)
        recent = conn.execute(
            "SELECT endpoint, success, COUNT(*) as cnt FROM request_log WHERE created_at > ? GROUP BY endpoint, success",
            (time.time() - 86400,),
        ).fetchall()

        recent_by_endpoint: dict[str, dict] = {}
        for r in recent:
            ep = r["endpoint"]
            if ep not in recent_by_endpoint:
                recent_by_endpoint[ep] = {"success": 0, "failed": 0}
            if r["success"]:
                recent_by_endpoint[ep]["success"] += r["cnt"]
            else:
                recent_by_endpoint[ep]["failed"] += r["cnt"]

        return {
            "keys": [_apikey_to_dict(k) for k in keys],
            "total_keys": len(keys),
            "active_keys": active_count,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "total_credits": total_credits,
            "recent_24h": recent_by_endpoint,
        }

    def get_recent_logs(self, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM request_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def _mask(key: str) -> str:
    if key.startswith("tvly-"):
        return key[:12] + "****" + key[-4:]
    return key[:4] + "****" + key[-4:] if len(key) > 8 else "****"


def _row_to_apikey(row: sqlite3.Row) -> ApiKey:
    return ApiKey(
        key=row["key"],
        masked=row["masked"],
        label=row["label"],
        is_active=bool(row["is_active"]),
        request_count=row["request_count"],
        error_count=row["error_count"],
        credits_used=row["credits_used"],
        credits_limit=row["credits_limit"],
        last_used_at=row["last_used_at"],
        added_at=row["added_at"],
        last_error=row["last_error"],
    )


def _apikey_to_dict(k: ApiKey) -> dict:
    return {
        "masked": k.masked,
        "label": k.label,
        "is_active": k.is_active,
        "request_count": k.request_count,
        "error_count": k.error_count,
        "credits_used": k.credits_used,
        "credits_limit": k.credits_limit,
        "usage_pct": round(k.usage_pct, 1),
        "last_used_at": k.last_used_at,
        "added_at": k.added_at,
        "last_error": k.last_error,
    }
