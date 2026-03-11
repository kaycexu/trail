"""Comprehensive tests for trail.db (TrailDB)."""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from trail.db import TrailDB, _build_literal_fts_query, _quote_fts_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_id() -> str:
    return str(uuid.uuid4())


def _insert_session(
    db: TrailDB,
    *,
    session_id: str | None = None,
    tool: str = "claude",
    cwd: str = "/tmp/work",
    repo_root: str | None = "/tmp/work",
    git_branch: str | None = "main",
    started_at: str = "2026-03-10T10:00:00+08:00",
    ended_at: str | None = None,
    exit_code: int | None = None,
    bytes_in: int = 0,
    bytes_out: int = 0,
) -> str:
    """Insert a session and optionally finish it. Returns the session id."""
    sid = session_id or _make_session_id()
    db.create_session(
        session_id=sid,
        tool=tool,
        argv_redacted=f"{tool} --yes",
        cwd=cwd,
        repo_root=repo_root,
        git_branch=git_branch,
        hostname="test-host",
        terminal_program="iTerm2",
        started_at=started_at,
        raw_log_path=f"/tmp/logs/{sid}.jsonl",
    )
    if ended_at is not None:
        db.finish_session(sid, ended_at=ended_at, exit_code=exit_code or 0,
                          bytes_in=bytes_in, bytes_out=bytes_out)
    return sid


def _insert_event(
    db: TrailDB,
    session_id: str,
    seq: int,
    *,
    stream: str = "stdout",
    event_type: str = "text",
    ts: str = "2026-03-10T10:00:01+08:00",
    text: str | None = "hello world",
    meta: dict | None = None,
) -> str:
    return db.add_event(
        session_id=session_id,
        seq=seq,
        stream=stream,
        event_type=event_type,
        ts=ts,
        payload_text_redacted=text,
        payload_meta=meta,
    )


def _insert_turns(db: TrailDB, session_id: str, turns: list[dict]) -> None:
    """Convenience wrapper around replace_turns with sane defaults."""
    full_turns = []
    for i, t in enumerate(turns):
        full_turns.append({
            "seq": t.get("seq", i),
            "role": t["role"],
            "text_redacted": t["text"],
            "started_at": t.get("started_at", f"2026-03-10T10:{i:02d}:00+08:00"),
            "ended_at": t.get("ended_at", f"2026-03-10T10:{i:02d}:30+08:00"),
            "parser_version": t.get("parser_version", "generic-v1"),
            "confidence": t.get("confidence", 1.0),
        })
    db.replace_turns(session_id, full_turns)


@pytest.fixture
def db(trail_home):
    """Yield a TrailDB backed by the trail_home tmp directory."""
    with TrailDB() as database:
        yield database


# ===========================================================================
# 1. Basic CRUD
# ===========================================================================

class TestCreateSession:
    def test_creates_and_retrieves_session(self, db):
        sid = _insert_session(db)
        row = db.get_session(sid)
        assert row is not None
        assert row["id"] == sid
        assert row["tool"] == "claude"
        assert row["hostname"] == "test-host"

    def test_session_defaults_bytes_zero(self, db):
        sid = _insert_session(db)
        row = db.get_session(sid)
        assert row["bytes_in"] == 0
        assert row["bytes_out"] == 0


class TestAddEvent:
    def test_stores_event_and_returns_id(self, db):
        sid = _insert_session(db)
        eid = _insert_event(db, sid, seq=1, text="some text")
        assert eid  # non-empty uuid string
        events = db.get_session_events(sid)
        assert len(events) == 1
        assert events[0]["payload_text_redacted"] == "some text"

    def test_indexes_text_in_fts(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text="unique_fts_token_xyz")
        db.flush()
        rows = db.conn.execute(
            "SELECT * FROM session_events_fts WHERE session_events_fts MATCH ?",
            ('"unique_fts_token_xyz"',),
        ).fetchall()
        assert len(rows) == 1

    def test_blank_text_not_indexed_in_fts(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text="   ")
        db.flush()
        rows = db.conn.execute(
            "SELECT count(*) as c FROM session_events_fts",
        ).fetchone()
        assert rows["c"] == 0

    def test_none_text_not_indexed_in_fts(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text=None)
        db.flush()
        rows = db.conn.execute(
            "SELECT count(*) as c FROM session_events_fts",
        ).fetchone()
        assert rows["c"] == 0

    def test_event_updates_last_event_at(self, db):
        sid = _insert_session(db)
        ts = "2026-03-10T11:22:33+08:00"
        _insert_event(db, sid, seq=1, ts=ts)
        db.flush()
        row = db.get_session(sid)
        assert row["last_event_at"] == ts


class TestGetSession:
    def test_exact_id(self, db):
        sid = _insert_session(db)
        assert db.get_session(sid) is not None

    def test_prefix_matching(self, db):
        sid = _insert_session(db)
        prefix = sid[:8]
        row = db.get_session(prefix)
        assert row is not None
        assert row["id"] == sid

    def test_ambiguous_prefix_returns_none(self, db):
        """When two sessions share a prefix, get_session returns None."""
        shared = "aaaaaaaa"
        _insert_session(db, session_id=f"{shared}-1111-1111-1111-111111111111")
        _insert_session(db, session_id=f"{shared}-2222-2222-2222-222222222222",
                        started_at="2026-03-10T11:00:00+08:00")
        assert db.get_session(shared) is None

    def test_nonexistent_returns_none(self, db):
        assert db.get_session("does-not-exist-at-all") is None


class TestListSessions:
    def test_limit(self, db):
        for i in range(5):
            _insert_session(db, started_at=f"2026-03-10T1{i}:00:00+08:00")
        rows = db.list_sessions(limit=3)
        assert len(rows) == 3

    def test_tool_filter(self, db):
        _insert_session(db, tool="claude")
        _insert_session(db, tool="codex", started_at="2026-03-10T11:00:00+08:00")
        rows = db.list_sessions(tool="codex")
        assert len(rows) == 1
        assert rows[0]["tool"] == "codex"

    def test_repo_filter(self, db):
        _insert_session(db, repo_root="/home/user/proj-a")
        _insert_session(db, repo_root="/home/user/proj-b",
                        started_at="2026-03-10T11:00:00+08:00")
        rows = db.list_sessions(repo="proj-a")
        assert len(rows) == 1
        assert "proj-a" in rows[0]["repo_root"]

    def test_ordered_desc_by_started_at(self, db):
        _insert_session(db, started_at="2026-03-01T10:00:00+08:00")
        _insert_session(db, started_at="2026-03-05T10:00:00+08:00")
        rows = db.list_sessions()
        assert rows[0]["started_at"] > rows[1]["started_at"]


class TestGetSessionEvents:
    def test_returns_events_in_order(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=3, text="third")
        _insert_event(db, sid, seq=1, text="first")
        _insert_event(db, sid, seq=2, text="second")
        db.flush()
        events = db.get_session_events(sid)
        assert [e["seq"] for e in events] == [1, 2, 3]
        assert [e["payload_text_redacted"] for e in events] == ["first", "second", "third"]


# ===========================================================================
# 2. FTS Search (turns)
# ===========================================================================

class TestSearchTurns:
    def _seed_turns(self, db):
        sid = _insert_session(db, tool="claude", repo_root="/code/myrepo")
        _insert_turns(db, sid, [
            {"role": "user", "text": "please refactor the database layer"},
            {"role": "assistant", "text": "I will refactor the database module now"},
        ])
        return sid

    def test_finds_matching_text(self, db):
        self._seed_turns(db)
        results = db.search_turns("refactor")
        assert len(results) >= 1

    def test_respects_role_filter_user(self, db):
        self._seed_turns(db)
        results = db.search_turns("refactor", role="user")
        assert all(r["role"] == "user" for r in results)

    def test_respects_role_filter_assistant(self, db):
        self._seed_turns(db)
        results = db.search_turns("refactor", role="assistant")
        assert all(r["role"] == "assistant" for r in results)

    def test_role_all_returns_both(self, db):
        self._seed_turns(db)
        results = db.search_turns("refactor", role="all")
        roles = {r["role"] for r in results}
        assert "user" in roles
        assert "assistant" in roles

    def test_respects_tool_filter(self, db):
        self._seed_turns(db)
        # searching for a tool that doesn't match
        results = db.search_turns("refactor", tool="codex")
        assert results == []

    def test_respects_repo_filter(self, db):
        self._seed_turns(db)
        results = db.search_turns("refactor", repo="myrepo")
        assert len(results) >= 1
        results_no = db.search_turns("refactor", repo="nonexistent")
        assert results_no == []

    def test_special_characters_in_query(self, db):
        sid = _insert_session(db)
        _insert_turns(db, sid, [
            {"role": "user", "text": 'run SELECT * FROM "users" WHERE id=1'},
        ])
        # Should not raise even with quotes and special chars
        results = db.search_turns('SELECT * FROM "users"')
        assert isinstance(results, list)

    def test_empty_query_returns_empty(self, db):
        self._seed_turns(db)
        assert db.search_turns("") == []
        assert db.search_turns("   ") == []

    def test_since_filter(self, db):
        sid = _insert_session(db)
        _insert_turns(db, sid, [
            {"role": "user", "text": "old message",
             "started_at": "2026-01-01T10:00:00+08:00",
             "ended_at": "2026-01-01T10:00:30+08:00"},
            {"role": "user", "text": "new message",
             "started_at": "2026-06-01T10:00:00+08:00",
             "ended_at": "2026-06-01T10:00:30+08:00"},
        ])
        results = db.search_turns("message", since="2026-03-01")
        assert len(results) == 1
        assert "new" in results[0]["text_redacted"]


# ===========================================================================
# 3. Schema migration
# ===========================================================================

class TestEnsureColumn:
    def test_adds_column_if_missing(self, db):
        db._ensure_column("sessions", "custom_col", "TEXT")
        cols = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        assert "custom_col" in cols

    def test_idempotent_no_error(self, db):
        db._ensure_column("sessions", "custom_col", "TEXT")
        # Call again -- should be a no-op, not raise
        db._ensure_column("sessions", "custom_col", "TEXT")

    def test_rejects_invalid_table_name(self, db):
        with pytest.raises(ValueError, match="Invalid table name"):
            db._ensure_column("sessions; DROP TABLE sessions", "col", "TEXT")

    def test_rejects_invalid_column_name(self, db):
        with pytest.raises(ValueError, match="Invalid column name"):
            db._ensure_column("sessions", "col; --", "TEXT")


# ===========================================================================
# 4. Turns
# ===========================================================================

class TestReplaceTurns:
    def test_replaces_existing_turns_atomically(self, db):
        sid = _insert_session(db)
        _insert_turns(db, sid, [
            {"role": "user", "text": "original question"},
            {"role": "assistant", "text": "original answer"},
        ])
        assert len(db.get_session_turns(sid)) == 2

        # Replace with different content
        _insert_turns(db, sid, [
            {"role": "user", "text": "revised question"},
            {"role": "assistant", "text": "revised answer"},
            {"role": "user", "text": "follow-up"},
        ])
        turns = db.get_session_turns(sid)
        assert len(turns) == 3
        assert turns[0]["text_redacted"] == "revised question"

    def test_fts_updated_after_replace(self, db):
        sid = _insert_session(db)
        _insert_turns(db, sid, [
            {"role": "user", "text": "alpha_unique_word"},
        ])
        assert len(db.search_turns("alpha_unique_word")) == 1

        _insert_turns(db, sid, [
            {"role": "user", "text": "beta_unique_word"},
        ])
        # Old FTS entry should be gone
        assert db.search_turns("alpha_unique_word") == []
        assert len(db.search_turns("beta_unique_word")) == 1


class TestGetSessionTurns:
    def test_returns_turns_in_sequence_order(self, db):
        sid = _insert_session(db)
        _insert_turns(db, sid, [
            {"seq": 2, "role": "assistant", "text": "answer"},
            {"seq": 0, "role": "user", "text": "question"},
            {"seq": 1, "role": "assistant", "text": "thinking"},
        ])
        turns = db.get_session_turns(sid)
        assert [t["seq"] for t in turns] == [0, 1, 2]


# ===========================================================================
# 5. day_summary
# ===========================================================================

class TestDaySummary:
    def test_returns_sessions_for_specific_date(self, db):
        _insert_session(db, tool="claude", started_at="2026-03-10T10:00:00+08:00",
                        repo_root="/code/proj")
        _insert_session(db, tool="codex", started_at="2026-03-10T14:00:00+08:00",
                        repo_root="/code/other")
        _insert_session(db, tool="claude", started_at="2026-03-11T10:00:00+08:00")

        summary = db.day_summary("2026-03-10")
        assert summary["date"] == "2026-03-10"
        assert summary["total_sessions"] == 2
        assert "claude" in summary["tools"]
        assert "codex" in summary["tools"]

    def test_handles_empty_results(self, db):
        summary = db.day_summary("2099-01-01")
        assert summary["total_sessions"] == 0
        assert summary["tools"] == {}
        assert summary["repos"] == []
        assert summary["recent_turns"] == []


# ===========================================================================
# 6. Active sessions
# ===========================================================================

class TestActiveSessions:
    def test_list_active_sessions_filters_ended(self, db):
        _insert_session(db, started_at="2026-03-10T10:00:00+08:00",
                        ended_at="2026-03-10T11:00:00+08:00")
        sid_active = _insert_session(db, started_at="2026-03-10T12:00:00+08:00")
        rows = db.list_active_sessions()
        assert len(rows) == 1
        assert rows[0]["id"] == sid_active

    def test_list_active_sessions_limit(self, db):
        for i in range(5):
            _insert_session(db, started_at=f"2026-03-10T1{i}:00:00+08:00")
        rows = db.list_active_sessions(limit=3)
        assert len(rows) == 3

    def test_get_latest_session_active_only(self, db):
        _insert_session(db, started_at="2026-03-10T10:00:00+08:00",
                        ended_at="2026-03-10T11:00:00+08:00")
        sid_active = _insert_session(db, started_at="2026-03-10T09:00:00+08:00")
        row = db.get_latest_session(active_only=True)
        assert row is not None
        assert row["id"] == sid_active

    def test_get_latest_session_no_active(self, db):
        _insert_session(db, started_at="2026-03-10T10:00:00+08:00",
                        ended_at="2026-03-10T11:00:00+08:00")
        assert db.get_latest_session(active_only=True) is None

    def test_get_latest_session_without_active_only(self, db):
        sid = _insert_session(db, started_at="2026-03-10T10:00:00+08:00",
                              ended_at="2026-03-10T11:00:00+08:00")
        row = db.get_latest_session()
        assert row is not None
        assert row["id"] == sid


# ===========================================================================
# 7. Context manager protocol
# ===========================================================================

class TestContextManager:
    def test_enter_returns_self(self, trail_home):
        db = TrailDB()
        result = db.__enter__()
        assert result is db
        db.__exit__(None, None, None)

    def test_exit_closes_connection(self, trail_home):
        db = TrailDB()
        _insert_session(db)
        db.__exit__(None, None, None)
        # Connection should be closed, so executing should fail
        with pytest.raises(Exception):
            db.conn.execute("SELECT 1")

    def test_with_statement(self, trail_home):
        with TrailDB() as db:
            sid = _insert_session(db)
            assert db.get_session(sid) is not None
        # After exiting the context manager, the connection is closed
        with pytest.raises(Exception):
            db.conn.execute("SELECT 1")

    def test_exit_returns_false(self, trail_home):
        db = TrailDB()
        assert db.__exit__(None, None, None) is False


# ===========================================================================
# 8. Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_get_session_events_after(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text="first")
        _insert_event(db, sid, seq=2, text="second")
        _insert_event(db, sid, seq=3, text="third")
        db.flush()

        events = db.get_session_events_after(sid, after_seq=1)
        assert len(events) == 2
        assert events[0]["seq"] == 2
        assert events[1]["seq"] == 3

    def test_get_session_events_after_zero_returns_all(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text="first")
        _insert_event(db, sid, seq=2, text="second")
        db.flush()
        events = db.get_session_events_after(sid, after_seq=0)
        assert len(events) == 2

    def test_get_session_events_after_high_seq_returns_empty(self, db):
        sid = _insert_session(db)
        _insert_event(db, sid, seq=1, text="only")
        db.flush()
        assert db.get_session_events_after(sid, after_seq=999) == []

    def test_flush_commits_pending(self, db):
        sid = _insert_session(db)
        # Manually bypass the auto-commit by inserting directly
        db.conn.execute(
            "UPDATE sessions SET bytes_in = 42 WHERE id = ?",
            (sid,),
        )
        db.flush()
        # Open a separate connection to verify the commit reached disk
        conn2 = sqlite3.connect(db.path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute("SELECT bytes_in FROM sessions WHERE id = ?", (sid,)).fetchone()
        conn2.close()
        assert row["bytes_in"] == 42

    def test_like_prefix_with_sql_percent_wildcard(self, db):
        """A session_id that starts with '%' should not break LIKE prefix."""
        sid = _insert_session(db, session_id="%percent-id-rest")
        # Exact match should work fine
        row = db.get_session("%percent-id-rest")
        assert row is not None

    def test_like_prefix_with_sql_underscore_wildcard(self, db):
        """A partial ID containing '_' should still match via LIKE prefix."""
        sid = _insert_session(db, session_id="abc_def_12345678")
        # Prefix search: the _ in the prefix is treated as a single-char wildcard
        # by LIKE, but since we inserted a row matching that exact prefix the
        # result should still come back (it may match other rows too; we just
        # verify our row is reachable).
        row = db.get_session("abc_def_12345678")
        assert row is not None
        assert row["id"] == sid

    def test_event_meta_json_stored(self, db):
        sid = _insert_session(db)
        meta = {"key": "value", "nested": [1, 2]}
        eid = _insert_event(db, sid, seq=1, text="with meta", meta=meta)
        db.flush()
        events = db.get_session_events(sid)
        import json
        stored = json.loads(events[0]["payload_meta_json"])
        assert stored == meta

    def test_finish_session_sets_fields(self, db):
        sid = _insert_session(db)
        db.finish_session(sid, ended_at="2026-03-10T12:00:00+08:00",
                          exit_code=0, bytes_in=100, bytes_out=200)
        row = db.get_session(sid)
        assert row["ended_at"] == "2026-03-10T12:00:00+08:00"
        assert row["exit_code"] == 0
        assert row["bytes_in"] == 100
        assert row["bytes_out"] == 200

    def test_set_session_process(self, db):
        sid = _insert_session(db)
        db.set_session_process(sid, child_pid=12345)
        row = db.get_session(sid)
        assert row["child_pid"] == 12345

    def test_iter_sessions_ascending_order(self, db):
        _insert_session(db, started_at="2026-03-05T10:00:00+08:00")
        _insert_session(db, started_at="2026-03-01T10:00:00+08:00")
        rows = db.iter_sessions()
        assert rows[0]["started_at"] < rows[1]["started_at"]


# ===========================================================================
# Helper function unit tests
# ===========================================================================

class TestBuildLiteralFtsQuery:
    def test_single_token(self):
        assert _build_literal_fts_query("hello") == '"hello"'

    def test_multiple_tokens(self):
        assert _build_literal_fts_query("hello world") == '"hello" "world"'

    def test_empty_string(self):
        assert _build_literal_fts_query("") == '""'

    def test_whitespace_only(self):
        assert _build_literal_fts_query("   ") == '""'

    def test_quotes_in_token(self):
        assert _quote_fts_token('say "hi"') == '"say ""hi"""'


class TestExplicitDbPath:
    def test_creates_db_at_explicit_path(self, tmp_path):
        db_file = tmp_path / "sub" / "test.db"
        with TrailDB(path=db_file) as db:
            sid = _insert_session(db)
            assert db.get_session(sid) is not None
        assert db_file.exists()
