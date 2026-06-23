"""
Human-OS Engine - 会话持久化存储

使用 SQLite 做单会话级别的持久化，避免每次更新都重写整份 JSON 文件。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from typing import Any

from schemas.context import Context


class SessionStore:
    """SQLite 会话存储。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_initialized()

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            with closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        context_json TEXT NOT NULL,
                        history_count INTEGER NOT NULL DEFAULT 0,
                        last_input TEXT NOT NULL DEFAULT '',
                        last_access REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_last_access
                    ON sessions(last_access DESC)
                    """
                )
                conn.commit()

            self._initialized = True

    def save_session(self, session_id: str, context: Context, last_access: float | None = None) -> None:
        self._ensure_initialized()
        now = time.time()
        access_time = float(last_access if last_access is not None else now)
        payload = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
        history_count = len(context.history)
        last_input = self._extract_last_user_input(context)

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, context_json, history_count, last_input, last_access, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    context_json = excluded.context_json,
                    history_count = excluded.history_count,
                    last_input = excluded.last_input,
                    last_access = excluded.last_access,
                    updated_at = excluded.updated_at
                """,
                (session_id, payload, history_count, last_input, access_time, now),
            )
            conn.commit()

    def load_session(self, session_id: str) -> Context | None:
        self._ensure_initialized()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT context_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if not row:
            return None

        data = json.loads(row["context_json"])
        return Context.model_validate(data)

    def delete_session(self, session_id: str) -> bool:
        self._ensure_initialized()
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_sessions(self, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT session_id, history_count, last_input, last_access, updated_at
                FROM sessions
                ORDER BY last_access DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "session_id": row["session_id"],
                "history_count": row["history_count"],
                "last_input": row["last_input"],
                "last_access": row["last_access"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def count_sessions(self) -> int:
        self._ensure_initialized()
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
        return int(row["count"]) if row else 0

    def cleanup_expired(self, ttl_seconds: float) -> int:
        self._ensure_initialized()
        cutoff = time.time() - ttl_seconds
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE last_access < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def _extract_last_user_input(context: Context) -> str:
        for item in reversed(context.history):
            if item.role == "user":
                return item.content
        return ""
