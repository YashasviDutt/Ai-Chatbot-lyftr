import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(settings.db_path)), exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def ping() -> bool:
    try:
        with connect() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


def get_session_prompt(session_id: str):
    with connect() as c:
        row = c.execute("SELECT system_prompt FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    return row["system_prompt"] if row else None


def get_history(session_id: str) -> list[dict]:
    """LLM-ready history (role/content only), oldest first."""
    with connect() as c:
        rows = c.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_messages(session_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
    out = []
    for r in rows:
        m = {"role": r["role"], "content": r["content"]}
        if r["metadata"]:
            m["metadata"] = json.loads(r["metadata"])
        out.append(m)
    return out


def save_exchange(session_id: str, system_prompt, user_msg: str, reply: str, metadata: dict) -> None:
    """Persist user + assistant messages atomically. Only called on success."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as c:
        c.execute(
            "INSERT INTO sessions(session_id, system_prompt) VALUES(?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET system_prompt=COALESCE(excluded.system_prompt, system_prompt)",
            (session_id, system_prompt),
        )
        c.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "user", user_msg, None, now),
        )
        c.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "assistant", reply, json.dumps(metadata), datetime.now(timezone.utc).isoformat()),
        )
