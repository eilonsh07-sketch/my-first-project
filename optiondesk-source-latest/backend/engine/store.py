"""
store.py — Persistence layer for Watchlist + Tracker (features 1 & 2).

Pluggable backend:
  * If DATABASE_URL (postgres://...) is set  -> use Postgres (psycopg) — for Vercel/Supabase.
  * Otherwise                                 -> use local SQLite file (optiondesk.db).

Two tables:
  watchlist : user-saved items (option contract OR stock-for-long-term).
  snapshots : daily tracked metrics per watchlist item (score/IV/probabilities/price).

The schema and the public API are identical across both backends so the rest of
the app never needs to care which one is active.
"""
from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, date, timezone
from typing import Optional

_DB_URL = os.environ.get("DATABASE_URL", "").strip()
_IS_PG = _DB_URL.startswith("postgres://") or _DB_URL.startswith("postgresql://")

_SQLITE_PATH = os.environ.get("OPTIONDESK_DB", os.path.join(os.path.dirname(__file__), "..", "optiondesk.db"))


# --------------------------------------------------------------------------
# Connection helpers
# --------------------------------------------------------------------------
def _pg_conn():
    import psycopg  # type: ignore
    return psycopg.connect(_DB_URL, autocommit=True)


def _sqlite_conn():
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ph(i: int) -> str:
    """Placeholder for parameterized queries: %s for PG, ? for SQLite."""
    return "%s" if _IS_PG else "?"


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
def init_db():
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    kind TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    label TEXT,
                    contract TEXT,
                    option_kind TEXT,
                    strike DOUBLE PRECISION,
                    expiry TEXT,
                    target_return_pct DOUBLE PRECISION DEFAULT 100,
                    alert_score DOUBLE PRECISION DEFAULT 70,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL,
                    taken_at TEXT NOT NULL,
                    spot DOUBLE PRECISION,
                    payload TEXT NOT NULL
                )""")
    else:
        with _sqlite_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    label TEXT,
                    contract TEXT,
                    option_kind TEXT,
                    strike REAL,
                    expiry TEXT,
                    target_return_pct REAL DEFAULT 100,
                    alert_score REAL DEFAULT 70,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    taken_at TEXT NOT NULL,
                    spot REAL,
                    payload TEXT NOT NULL
                )""")
            conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Watchlist CRUD
# --------------------------------------------------------------------------
def add_item(item: dict) -> dict:
    """item: {kind:'option'|'stock', ticker, label?, contract?, option_kind?, strike?,
             expiry?, target_return_pct?, alert_score?, notes?}"""
    row = (
        item.get("kind", "stock"),
        item["ticker"].upper(),
        item.get("label"),
        item.get("contract"),
        item.get("option_kind"),
        item.get("strike"),
        item.get("expiry"),
        float(item.get("target_return_pct", 100) or 100),
        float(item.get("alert_score", 70) or 70),
        item.get("notes"),
        _now_iso(),
    )
    cols = ("kind,ticker,label,contract,option_kind,strike,expiry,"
            "target_return_pct,alert_score,notes,created_at")
    phs = ",".join([_ph(i) for i in range(11)])
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"INSERT INTO watchlist ({cols}) VALUES ({phs}) RETURNING id", row)
            new_id = cur.fetchone()[0]
    else:
        with _sqlite_conn() as conn:
            cur = conn.execute(f"INSERT INTO watchlist ({cols}) VALUES ({phs})", row)
            new_id = cur.lastrowid
            conn.commit()
    return get_item(new_id)


def list_items() -> list[dict]:
    q = "SELECT * FROM watchlist ORDER BY created_at DESC"
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(q)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    with _sqlite_conn() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_item(item_id: int) -> Optional[dict]:
    q = f"SELECT * FROM watchlist WHERE id = {_ph(0)}"
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(q, (item_id,))
            r = cur.fetchone()
            if not r:
                return None
            cols = [c.name for c in cur.description]
            return dict(zip(cols, r))
    with _sqlite_conn() as conn:
        r = conn.execute(q, (item_id,)).fetchone()
        return dict(r) if r else None


def update_item(item_id: int, fields: dict) -> Optional[dict]:
    allowed = {"label", "target_return_pct", "alert_score", "notes"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = {_ph(0)}")
            vals.append(v)
    if not sets:
        return get_item(item_id)
    vals.append(item_id)
    q = f"UPDATE watchlist SET {', '.join(sets)} WHERE id = {_ph(0)}"
    if _IS_PG:
        with _pg_conn() as conn:
            conn.cursor().execute(q, tuple(vals))
    else:
        with _sqlite_conn() as conn:
            conn.execute(q, tuple(vals))
            conn.commit()
    return get_item(item_id)


def delete_item(item_id: int) -> bool:
    q1 = f"DELETE FROM snapshots WHERE item_id = {_ph(0)}"
    q2 = f"DELETE FROM watchlist WHERE id = {_ph(0)}"
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(q1, (item_id,))
            cur.execute(q2, (item_id,))
    else:
        with _sqlite_conn() as conn:
            conn.execute(q1, (item_id,))
            conn.execute(q2, (item_id,))
            conn.commit()
    return True


# --------------------------------------------------------------------------
# Snapshots (daily tracking)
# --------------------------------------------------------------------------
def add_snapshot(item_id: int, spot: Optional[float], payload: dict) -> dict:
    row = (item_id, _now_iso(), spot, json.dumps(payload))
    q = (f"INSERT INTO snapshots (item_id, taken_at, spot, payload) "
         f"VALUES ({_ph(0)},{_ph(1)},{_ph(2)},{_ph(3)})")
    if _IS_PG:
        with _pg_conn() as conn:
            conn.cursor().execute(q, row)
    else:
        with _sqlite_conn() as conn:
            conn.execute(q, row)
            conn.commit()
    return {"item_id": item_id, "taken_at": row[1], "spot": spot, "payload": payload}


def list_snapshots(item_id: int, limit: int = 60) -> list[dict]:
    q = (f"SELECT taken_at, spot, payload FROM snapshots WHERE item_id = {_ph(0)} "
         f"ORDER BY taken_at ASC LIMIT {int(limit)}")
    out = []
    if _IS_PG:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(q, (item_id,))
            rows = cur.fetchall()
    else:
        with _sqlite_conn() as conn:
            rows = conn.execute(q, (item_id,)).fetchall()
    for r in rows:
        taken_at = r[0]
        spot = r[1]
        payload = r[2]
        out.append({
            "taken_at": taken_at,
            "spot": spot,
            **(json.loads(payload) if payload else {}),
        })
    return out
