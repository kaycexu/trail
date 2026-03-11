from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from trail.db import TrailDB
from trail.markdown import write_session_markdown
from trail.parser import rebuild_session_turns


class ParserTests(unittest.TestCase):
    def test_rebuild_session_turns_derives_clean_transcript_from_raw_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                db = TrailDB(path=f"{tmpdir}/trail.db")
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
                    raw_log_path=f"{tmpdir}/session-1.jsonl",
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
                    payload_text_redacted="✢Musing…\n(thinking with high effort)\nANSWER:He\n",
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
                transcript_paths = list(Path(tmpdir).glob("transcripts/**/*.md"))
                markdown = transcript_paths[0].read_text(encoding="utf-8")
                db.close()
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Test"), ("assistant", "ANSWER:Hello world")],
        )
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in stored_turns],
            [("user", "Test"), ("assistant", "ANSWER:Hello world")],
        )
        self.assertEqual(len(transcript_paths), 1)
        self.assertIn('kind: "trail_session"', markdown)
        self.assertIn('schema_version: "trail_session/v1"', markdown)
        self.assertIn('parser_revision: 2', markdown)
        self.assertIn('session_id: "session-1"', markdown)
        self.assertIn('status: "active"', markdown)
        self.assertIn('date: "2026-03-10"', markdown)
        self.assertIn('week: "2026-W11"', markdown)
        self.assertIn('started_at: "2026-03-10T15:39:03+08:00"', markdown)
        self.assertIn('turn_count: 2', markdown)
        self.assertIn("last_synced_at:", markdown)
        self.assertIn("# Trail Session session-1", markdown)
        self.assertIn("## Transcript", markdown)
        self.assertIn("### You", markdown)
        self.assertIn("### Claude", markdown)
        self.assertIn("- Started: 2026-03-10T15:39:10+08:00", markdown)
        self.assertIn("- Ended: 2026-03-10T15:39:12+08:00", markdown)
        self.assertIn("ANSWER:Hello world", markdown)


    def test_rebuild_session_turns_splits_multi_turn_and_drops_tool_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                db = TrailDB(path=f"{tmpdir}/trail.db")
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
                    raw_log_path=f"{tmpdir}/session-2.jsonl",
                )
                db.add_event(
                    session_id=session_id,
                    seq=1,
                    stream="stdin",
                    event_type="text",
                    ts="2026-03-11T10:42:46+08:00",
                    payload_text_redacted="第一个问题\n",
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
                        "第一个回答\n"
                    ),
                    payload_meta=None,
                )
                db.add_event(
                    session_id=session_id,
                    seq=3,
                    stream="stdin",
                    event_type="text",
                    ts="2026-03-11T10:43:53+08:00",
                    payload_text_redacted="第二个问题\n",
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
                        "第二个回答\n"
                    ),
                    payload_meta=None,
                )

                turns = rebuild_session_turns(db, session_id)
                db.close()
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "第一个问题"),
                ("assistant", "第一个回答"),
                ("user", "第二个问题"),
                ("assistant", "第二个回答"),
            ],
        )


class MarkdownWriteGuardTests(unittest.TestCase):
    def test_write_session_markdown_does_not_downgrade_newer_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                session = {
                    "id": "session-guard",
                    "tool": "claude",
                    "cwd": "/tmp/project",
                    "repo_root": "/tmp/project",
                    "git_branch": "main",
                    "started_at": "2026-03-11T10:00:00+08:00",
                    "ended_at": "2026-03-11T10:05:00+08:00",
                    "exit_code": 0,
                    "raw_log_path": f"{tmpdir}/session-guard.jsonl",
                }
                turns = [
                    {
                        "role": "user",
                        "text_redacted": "hello",
                        "started_at": "2026-03-11T10:00:00+08:00",
                        "ended_at": "2026-03-11T10:00:00+08:00",
                    }
                ]
                path = Path(tmpdir) / "transcripts" / "2026-03-11" / "100000--claude--session-guard.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("---\nparser_revision: 99\n---\nnewer\n", encoding="utf-8")
                write_session_markdown(session, turns, parser_revision=2)
                markdown = path.read_text(encoding="utf-8")
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(markdown, "---\nparser_revision: 99\n---\nnewer\n")


if __name__ == "__main__":
    unittest.main()
