from __future__ import annotations

from pathlib import Path

from trail.db import TrailDB
from trail.markdown import write_session_markdown
from trail.parser import rebuild_session_turns


def test_rebuild_session_turns_derives_clean_transcript_from_raw_events(trail_home):
    db = TrailDB(path=str(trail_home / "trail.db"))
    session_id = "session-1"
    db.create_session(
        session_id=session_id,
        tool="claude",
        argv_redacted="claude",
        cwd="/tmp/project",
        repo_root="/tmp/project",
        git_branch="main",
        hostname="host",
        terminal_program="Apple_Terminal",
        started_at="2026-03-10T15:39:03+08:00",
        raw_log_path=str(trail_home / "session-1.jsonl"),
    )
    db.add_event(
        session_id=session_id,
        seq=1,
        stream="stdin",
        event_type="text",
        ts="2026-03-10T15:39:10+08:00",
        payload_text_redacted="Test\n",
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=2,
        stream="stdout",
        event_type="text",
        ts="2026-03-10T15:39:11+08:00",
        payload_text_redacted="\u2722Musing\u2026\n(thinking with high effort)\nANSWER:He\n",
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=3,
        stream="stdout",
        event_type="text",
        ts="2026-03-10T15:39:12+08:00",
        payload_text_redacted="ANSWER:Hello world\n",
        payload_meta=None,
    )

    turns = rebuild_session_turns(db, session_id)
    stored_turns = db.get_session_turns(session_id)
    transcript_paths = list(trail_home.glob("transcripts/**/*.md"))
    markdown = transcript_paths[0].read_text(encoding="utf-8")
    db.close()

    assert [(turn["role"], turn["text_redacted"]) for turn in turns] == [
        ("user", "Test"),
        ("assistant", "ANSWER:Hello world"),
    ]
    assert [(turn["role"], turn["text_redacted"]) for turn in stored_turns] == [
        ("user", "Test"),
        ("assistant", "ANSWER:Hello world"),
    ]
    assert len(transcript_paths) == 1
    assert 'kind: "trail_session"' in markdown
    assert 'schema_version: "trail_session/v1"' in markdown
    assert 'parser_revision: 2' in markdown
    assert 'session_id: "session-1"' in markdown
    assert 'status: "active"' in markdown
    assert 'date: "2026-03-10"' in markdown
    assert 'week: "2026-W11"' in markdown
    assert 'started_at: "2026-03-10T15:39:03+08:00"' in markdown
    assert 'turn_count: 2' in markdown
    assert "last_synced_at:" in markdown
    assert "# Trail Session session-1" in markdown
    assert "## Transcript" in markdown
    assert "### You" in markdown
    assert "### Claude" in markdown
    assert "- Started: 2026-03-10T15:39:10+08:00" in markdown
    assert "- Ended: 2026-03-10T15:39:12+08:00" in markdown
    assert "ANSWER:Hello world" in markdown


def test_rebuild_session_turns_splits_multi_turn_and_drops_tool_noise(trail_home):
    db = TrailDB(path=str(trail_home / "trail.db"))
    session_id = "session-2"
    db.create_session(
        session_id=session_id,
        tool="claude",
        argv_redacted="claude",
        cwd="/tmp/project",
        repo_root="/tmp/project",
        git_branch="main",
        hostname="host",
        terminal_program="Apple_Terminal",
        started_at="2026-03-11T10:42:08+08:00",
        raw_log_path=str(trail_home / "session-2.jsonl"),
    )
    db.add_event(
        session_id=session_id,
        seq=1,
        stream="stdin",
        event_type="text",
        ts="2026-03-11T10:42:46+08:00",
        payload_text_redacted="\u7b2c\u4e00\u4e2a\u95ee\u9898\n",
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=2,
        stream="stdout",
        event_type="text",
        ts="2026-03-11T10:42:52+08:00",
        payload_text_redacted=(
            "Plugin updated: superpowers\n"
            "Fetch(https://example.com)\n"
            "\u7b2c\u4e00\u4e2a\u56de\u7b54\n"
        ),
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=3,
        stream="stdin",
        event_type="text",
        ts="2026-03-11T10:43:53+08:00",
        payload_text_redacted="\u7b2c\u4e8c\u4e2a\u95ee\u9898\n",
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=4,
        stream="stdout",
        event_type="text",
        ts="2026-03-11T10:44:00+08:00",
        payload_text_redacted=(
            "Do you want to create CLAUDE.md?\n"
            "Yes, allow all edits during this session\n"
            "\u7b2c\u4e8c\u4e2a\u56de\u7b54\n"
        ),
        payload_meta=None,
    )

    turns = rebuild_session_turns(db, session_id)
    db.close()

    assert [(turn["role"], turn["text_redacted"]) for turn in turns] == [
        ("user", "\u7b2c\u4e00\u4e2a\u95ee\u9898"),
        ("assistant", "\u7b2c\u4e00\u4e2a\u56de\u7b54"),
        ("user", "\u7b2c\u4e8c\u4e2a\u95ee\u9898"),
        ("assistant", "\u7b2c\u4e8c\u4e2a\u56de\u7b54"),
    ]


def test_write_session_markdown_does_not_downgrade_newer_revision(trail_home):
    session = {
        "id": "session-guard",
        "tool": "claude",
        "cwd": "/tmp/project",
        "repo_root": "/tmp/project",
        "git_branch": "main",
        "started_at": "2026-03-11T10:00:00+08:00",
        "ended_at": "2026-03-11T10:05:00+08:00",
        "exit_code": 0,
        "raw_log_path": str(trail_home / "session-guard.jsonl"),
    }
    turns = [
        {
            "role": "user",
            "text_redacted": "hello",
            "started_at": "2026-03-11T10:00:00+08:00",
            "ended_at": "2026-03-11T10:00:00+08:00",
        }
    ]
    path = trail_home / "transcripts" / "2026-03-11" / "100000--claude--session-guard.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\nparser_revision: 99\n---\nnewer\n", encoding="utf-8")
    write_session_markdown(session, turns, parser_revision=2)
    markdown = path.read_text(encoding="utf-8")

    assert markdown == "---\nparser_revision: 99\n---\nnewer\n"
