from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from trail.paths import db_path, ensure_trail_home


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class SessionRecord:
    id: str
    tool: str
    argv_redacted: str
    cwd: str
    repo_root: Optional[str]
    git_branch: Optional[str]
    hostname: str
    terminal_program: Optional[str]
    started_at: str
    ended_at: Optional[str]
    exit_code: Optional[int]
    raw_log_path: str
    bytes_in: int
    bytes_out: int


class TrailDB:
    _FLUSH_INTERVAL = 0.5  # seconds between auto-commits

    def __init__(self, path=None) -> None:
        if path is None:
            ensure_trail_home()
            self.path = str(db_path())
        else:
            self.path = str(path)
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._last_commit_time: float = time.monotonic()
        self._init_schema()

    def flush(self) -> None:
        """Force a commit of any pending writes and reset the flush timer."""
        self.conn.commit()
        self._last_commit_time = time.monotonic()

    def __enter__(self) -> "TrailDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    def close(self) -> None:
        self.flush()
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                tool TEXT NOT NULL,
                argv_redacted TEXT NOT NULL,
                cwd TEXT NOT NULL,
                repo_root TEXT,
                git_branch TEXT,
                hostname TEXT NOT NULL,
                terminal_program TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                exit_code INTEGER,
                raw_log_path TEXT NOT NULL,
                bytes_in INTEGER NOT NULL DEFAULT 0,
                bytes_out INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS session_events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                stream TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts TEXT NOT NULL,
                payload_text_redacted TEXT,
                payload_meta_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_session_events_session_seq
            ON session_events(session_id, seq);

            CREATE VIRTUAL TABLE IF NOT EXISTS session_events_fts USING fts5(
                session_event_id UNINDEXED,
                session_id UNINDEXED,
                stream UNINDEXED,
                payload_text_redacted
            );

            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                text_redacted TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                confidence REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session_seq
            ON turns(session_id, seq);

            CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                turn_id UNINDEXED,
                session_id UNINDEXED,
                role UNINDEXED,
                text_redacted
            );
            """
        )
        self._ensure_column("sessions", "child_pid", "INTEGER")
        self._ensure_column("sessions", "last_event_at", "TEXT")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row[1]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_session(self, *, session_id: str, tool: str, argv_redacted: str, cwd: str,
                       repo_root: Optional[str], git_branch: Optional[str], hostname: str,
                       terminal_program: Optional[str], started_at: str, raw_log_path: str) -> None:
        self.conn.execute(
            """
            INSERT INTO sessions (
                id, tool, argv_redacted, cwd, repo_root, git_branch,
                hostname, terminal_program, started_at, raw_log_path,
                last_event_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                tool,
                argv_redacted,
                cwd,
                repo_root,
                git_branch,
                hostname,
                terminal_program,
                started_at,
                raw_log_path,
                started_at,
            ),
        )
        self.conn.commit()

    def set_session_process(self, session_id: str, *, child_pid: int) -> None:
        self.conn.execute(
            """
            UPDATE sessions
            SET child_pid = ?
            WHERE id = ?
            """,
            (child_pid, session_id),
        )
        self.conn.commit()

    def finish_session(self, session_id: str, *, ended_at: str, exit_code: int,
                       bytes_in: int, bytes_out: int) -> None:
        self.conn.execute(
            """
            UPDATE sessions
            SET ended_at = ?, exit_code = ?, bytes_in = ?, bytes_out = ?, last_event_at = ?
            WHERE id = ?
            """,
            (ended_at, exit_code, bytes_in, bytes_out, ended_at, session_id),
        )
        self.conn.commit()

    def add_event(self, *, session_id: str, seq: int, stream: str, event_type: str, ts: str,
                  payload_text_redacted: Optional[str], payload_meta: Optional[dict]) -> str:
        event_id = str(uuid.uuid4())
        payload_meta_json = json.dumps(payload_meta, ensure_ascii=False) if payload_meta else None
        self.conn.execute(
            """
            INSERT INTO session_events (
                id, session_id, seq, stream, event_type, ts,
                payload_text_redacted, payload_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                seq,
                stream,
                event_type,
                ts,
                payload_text_redacted,
                payload_meta_json,
            ),
        )
        if payload_text_redacted and payload_text_redacted.strip():
            self.conn.execute(
                """
                INSERT INTO session_events_fts (
                    session_event_id, session_id, stream, payload_text_redacted
                ) VALUES (?, ?, ?, ?)
                """,
                (event_id, session_id, stream, payload_text_redacted),
            )
        self.conn.execute(
            "UPDATE sessions SET last_event_at = ? WHERE id = ?",
            (ts, session_id),
        )
        if time.monotonic() - self._last_commit_time >= self._FLUSH_INTERVAL:
            self.flush()
        return event_id

    def get_session_events(self, session_id: str) -> list[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM session_events
            WHERE session_id = ?
            ORDER BY seq ASC
            """,
            (session_id,),
        )
        return cursor.fetchall()

    def replace_turns(self, session_id: str, turns: Iterable[dict]) -> None:
        existing_ids = [
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM turns WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        ]
        if existing_ids:
            self.conn.executemany(
                "DELETE FROM turns_fts WHERE turn_id = ?",
                [(turn_id,) for turn_id in existing_ids],
            )
            self.conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))

        for turn in turns:
            turn_id = str(uuid.uuid4())
            self.conn.execute(
                """
                INSERT INTO turns (
                    id, session_id, seq, role, text_redacted,
                    started_at, ended_at, parser_version, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    session_id,
                    turn["seq"],
                    turn["role"],
                    turn["text_redacted"],
                    turn["started_at"],
                    turn["ended_at"],
                    turn["parser_version"],
                    turn["confidence"],
                ),
            )
            self.conn.execute(
                """
                INSERT INTO turns_fts (turn_id, session_id, role, text_redacted)
                VALUES (?, ?, ?, ?)
                """,
                (turn_id, session_id, turn["role"], turn["text_redacted"]),
            )
        self.conn.commit()

    def list_sessions(self, *, limit: int = 20, tool: Optional[str] = None,
                      repo: Optional[str] = None) -> list[sqlite3.Row]:
        query, params = self._session_query(tool=tool, repo=repo)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(query, params).fetchall()

    def iter_sessions(self, *, tool: Optional[str] = None, repo: Optional[str] = None) -> list[sqlite3.Row]:
        query, params = self._session_query(tool=tool, repo=repo)
        query += " ORDER BY started_at ASC"
        return self.conn.execute(query, params).fetchall()

    def get_session(self, session_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    def get_latest_session(
        self,
        *,
        tool: Optional[str] = None,
        repo: Optional[str] = None,
        active_only: bool = False,
    ) -> Optional[sqlite3.Row]:
        query, params = self._session_query(tool=tool, repo=repo)
        if active_only:
            query += " AND ended_at IS NULL"
        query += " ORDER BY COALESCE(last_event_at, started_at) DESC, started_at DESC LIMIT 1"
        return self.conn.execute(query, params).fetchone()

    def list_active_sessions(
        self,
        *,
        limit: int = 20,
        tool: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        query, params = self._session_query(tool=tool, repo=repo)
        query += " AND ended_at IS NULL"
        query += " ORDER BY COALESCE(last_event_at, started_at) DESC, started_at DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(query, params).fetchall()

    def get_session_events_after(self, session_id: str, after_seq: int = 0) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM session_events
            WHERE session_id = ? AND seq > ?
            ORDER BY seq ASC
            """,
            (session_id, after_seq),
        ).fetchall()

    def get_session_turns(self, session_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM turns
            WHERE session_id = ?
            ORDER BY seq ASC
            """,
            (session_id,),
        ).fetchall()

    def search_turns(self, query_text: str, *, limit: int = 20, role: Optional[str] = None,
                     tool: Optional[str] = None, repo: Optional[str] = None,
                     since: Optional[str] = None) -> list[sqlite3.Row]:
        query = """
            SELECT
                turns.session_id,
                turns.role,
                turns.text_redacted,
                turns.started_at,
                sessions.tool,
                sessions.repo_root,
                sessions.cwd
            FROM turns_fts
            JOIN turns ON turns.id = turns_fts.turn_id
            JOIN sessions ON sessions.id = turns.session_id
            WHERE turns_fts MATCH ?
        """
        params: list[object] = [query_text]
        if role and role != "all":
            query += " AND turns.role = ?"
            params.append(role)
        if tool:
            query += " AND sessions.tool = ?"
            params.append(tool)
        if repo:
            like = f"%{repo}%"
            query += " AND (sessions.repo_root LIKE ? OR sessions.cwd LIKE ?)"
            params.extend([like, like])
        if since:
            query += " AND turns.started_at >= ?"
            params.append(since)
        query += " ORDER BY turns.started_at DESC LIMIT ?"
        params.append(limit)
        return self.conn.execute(query, params).fetchall()

    def day_summary(self, date_prefix: str) -> dict:
        rows = self.conn.execute(
            """
            SELECT tool, repo_root, COUNT(*) AS count
            FROM sessions
            WHERE started_at LIKE ?
            GROUP BY tool, repo_root
            ORDER BY count DESC
            """,
            (f"{date_prefix}%",),
        ).fetchall()
        total_sessions = sum(row["count"] for row in rows)
        tools: dict[str, int] = {}
        repos: list[tuple[str, int]] = []
        for row in rows:
            tools[row["tool"]] = tools.get(row["tool"], 0) + row["count"]
            if row["repo_root"]:
                repos.append((row["repo_root"], row["count"]))
        recent_turns = self.conn.execute(
            """
            SELECT role, text_redacted
            FROM turns
            WHERE started_at LIKE ?
            ORDER BY started_at DESC
            LIMIT 10
            """,
            (f"{date_prefix}%",),
        ).fetchall()
        return {
            "date": date_prefix,
            "total_sessions": total_sessions,
            "tools": tools,
            "repos": repos[:5],
            "recent_turns": recent_turns,
        }

    def _session_query(self, *, tool: Optional[str], repo: Optional[str]) -> tuple[str, list[object]]:
        query = """
            SELECT *
            FROM sessions
            WHERE 1 = 1
        """
        params: list[object] = []
        if tool:
            query += " AND tool = ?"
            params.append(tool)
        if repo:
            like = f"%{repo}%"
            query += " AND (repo_root LIKE ? OR cwd LIKE ?)"
            params.extend([like, like])
        return query, params
