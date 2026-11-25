import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")


def _db_path() -> str:
    prefix = "sqlite:///"
    if not DATABASE_URL.startswith(prefix):
        raise RuntimeError("DATABASE_URL must be a sqlite:/// URL")
    path = DATABASE_URL[len(prefix):]
    if path.startswith("/"):
        resolved = path
    else:
        resolved = str(Path(path).resolve())
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    return resolved


@contextmanager
def connection():
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")


def get_messages(session_id: str):
    with connection() as conn:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = {"role": row["role"], "content": row["content"]}
        if row["role"] == "assistant" and row["metadata"]:
            item["metadata"] = json.loads(row["metadata"])
        result.append(item)
    return result


def add_exchange(session_id: str, user_text: str, reply: str, metadata: dict, created_at: str):
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "user", user_text, None, created_at),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "assistant", reply, json.dumps(metadata), created_at),
        )
