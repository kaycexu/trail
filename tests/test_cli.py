from __future__ import annotations

import io
import unittest
from unittest import mock

from trail.cli import main, parse_argv
from trail.config import init_config, set_config_value, save_config
from trail.db import TrailDB
from trail.parser import rebuild_session_turns


class CliParsingTests(unittest.TestCase):
    def test_claude_shortcut_forwards_unknown_flags(self) -> None:
        _, args = parse_argv(["claude", "-p", "Reply with exactly OK."])
        self.assertEqual(args.command, "claude")
        self.assertEqual(args.args, ["-p", "Reply with exactly OK."])

    def test_wrap_forwards_tool_args(self) -> None:
        _, args = parse_argv(["wrap", "claude", "--permission-mode", "plan"])
        self.assertEqual(args.command, "wrap")
        self.assertEqual(args.tool, "claude")
        self.assertEqual(args.args, ["--permission-mode", "plan"])

    def test_watch_parses_filters(self) -> None:
        _, args = parse_argv(["watch", "--tool", "claude", "--mode", "turns", "--settle-seconds", "1.5"])
        self.assertEqual(args.command, "watch")
        self.assertEqual(args.tool, "claude")
        self.assertEqual(args.mode, "turns")
        self.assertEqual(args.settle_seconds, 1.5)

    def test_config_command_parses_set(self) -> None:
        _, args = parse_argv(["config", "set", "watch.mode", "events"])
        self.assertEqual(args.command, "config")
        self.assertEqual(args.config_command, "set")
        self.assertEqual(args.key, "watch.mode")
        self.assertEqual(args.value, "events")

    def test_doctor_command_parses_shell(self) -> None:
        _, args = parse_argv(["doctor", "--shell", "fish"])
        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.shell, "fish")

    def test_rebuild_command_parses_session_id(self) -> None:
        _, args = parse_argv(["rebuild", "session-123"])
        self.assertEqual(args.command, "rebuild")
        self.assertEqual(args.session_id, "session-123")

    def test_show_parses_raw_flag(self) -> None:
        _, args = parse_argv(["show", "session-123", "--raw", "--raw-limit", "50"])
        self.assertEqual(args.command, "show")
        self.assertEqual(args.session_id, "session-123")
        self.assertEqual(args.raw, True)
        self.assertEqual(args.raw_limit, 50)

    def test_reindex_command_parses_filters(self) -> None:
        _, args = parse_argv(["reindex", "--tool", "claude", "--repo", "trail"])
        self.assertEqual(args.command, "reindex")
        self.assertEqual(args.tool, "claude")
        self.assertEqual(args.repo, "trail")


def init_and_load():
    init_config(force=True)
    from trail.config import load_config

    return load_config()


def test_watch_uses_config_defaults(trail_home):
    config = set_config_value(init_and_load(), "watch.mode", "events")
    config = set_config_value(config, "watch.poll_interval", 0.25)
    save_config(config)
    with mock.patch("trail.cli.watch_session", return_value=0) as watch_session:
        exit_code = main(["watch", "--tool", "claude"])

    assert exit_code == 0
    args = watch_session.call_args.args[1]
    assert args.mode == "events"
    assert args.poll_interval == 0.25


def _make_session_with_events(trail_home, session_id="session-1"):
    """Helper: create a session with stdin/stdout events and return the db path."""
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)
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
        raw_log_path=str(trail_home / f"{session_id}.jsonl"),
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
        payload_text_redacted="\u2722Musing\u2026\nANSWER:Hello world\n",
        payload_meta=None,
    )
    db.close()
    return db_file


def test_rebuild_and_reindex_commands_recompute_turns(trail_home):
    db_file = _make_session_with_events(trail_home, session_id="session-1")

    with mock.patch("sys.stdout", new=io.StringIO()):
        rebuild_exit = main(["rebuild", "session-1"])
        reindex_exit = main(["reindex", "--tool", "claude"])

    db = TrailDB(path=db_file)
    turns = [(turn["role"], turn["text_redacted"]) for turn in db.get_session_turns("session-1")]
    db.close()

    assert rebuild_exit == 0
    assert reindex_exit == 0
    assert turns == [("user", "Test"), ("assistant", "ANSWER:Hello world")]


def test_show_renders_transcript_style_output(trail_home):
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)
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
        started_at="2026-03-10T15:39:03+08:00",
        raw_log_path=str(trail_home / "session-2.jsonl"),
    )
    db.replace_turns(
        session_id,
        [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "First line\nSecond line",
                "started_at": "2026-03-10T15:39:10+08:00",
                "ended_at": "2026-03-10T15:39:10+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": "ANSWER:Hello world\nAnother line",
                "started_at": "2026-03-10T15:39:11+08:00",
                "ended_at": "2026-03-10T15:39:11+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
        ],
    )
    db.close()

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["show", session_id])
        output = stdout.getvalue()

    assert exit_code == 0
    assert "Transcript" in output
    assert "Markdown " in output
    assert "Preview  First line Second line" in output
    assert "[15:39:10] You" in output
    assert "  First line" in output
    assert "  Second line" in output
    assert "[15:39:11] Claude" in output
    assert "  ANSWER:Hello world" in output
    assert "  Another line" in output
    assert "parser=" not in output


def test_show_raw_includes_event_stream(trail_home):
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)
    session_id = "session-3"
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
        raw_log_path=str(trail_home / "session-3.jsonl"),
    )
    db.add_event(
        session_id=session_id,
        seq=1,
        stream="meta",
        event_type="start",
        ts="2026-03-10T15:39:03+08:00",
        payload_text_redacted=None,
        payload_meta={"tool": "claude"},
    )
    db.add_event(
        session_id=session_id,
        seq=2,
        stream="stdin",
        event_type="text",
        ts="2026-03-10T15:39:10+08:00",
        payload_text_redacted="Question\n",
        payload_meta=None,
    )
    db.add_event(
        session_id=session_id,
        seq=3,
        stream="stdout",
        event_type="text",
        ts="2026-03-10T15:39:11+08:00",
        payload_text_redacted="Answer\nMore\n",
        payload_meta=None,
    )
    db.replace_turns(
        session_id,
        [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "Question",
                "started_at": "2026-03-10T15:39:10+08:00",
                "ended_at": "2026-03-10T15:39:10+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": "Answer",
                "started_at": "2026-03-10T15:39:11+08:00",
                "ended_at": "2026-03-10T15:39:11+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
        ],
    )
    db.close()

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["show", session_id, "--raw"])
        output = stdout.getvalue()

    assert exit_code == 0
    assert "Raw Events" in output
    assert "[15:39:03] meta/start" in output
    assert "[15:39:10] stdin/text Question" in output
    assert "[15:39:11] stdout/text Answer" in output
    assert "                   More" in output


def test_show_raw_limit_keeps_only_latest_events(trail_home):
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)
    session_id = "session-4"
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
        raw_log_path=str(trail_home / "session-4.jsonl"),
    )
    for seq, text in enumerate(["one\n", "two\n", "three\n"], start=1):
        db.add_event(
            session_id=session_id,
            seq=seq,
            stream="stdout",
            event_type="text",
            ts=f"2026-03-10T15:39:0{seq}+08:00",
            payload_text_redacted=text,
            payload_meta=None,
        )
    db.close()

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["show", session_id, "--raw", "--raw-limit", "2"])
        output = stdout.getvalue()

    assert exit_code == 0
    assert "stdout/text one" not in output
    assert "stdout/text two" in output
    assert "stdout/text three" in output


def _create_day_sessions(trail_home, date_str="2026-03-10"):
    """Helper: create sessions on a specific date for day command testing."""
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)

    db.create_session(
        session_id="day-session-1",
        tool="claude",
        argv_redacted="claude",
        cwd="/tmp/project-a",
        repo_root="/tmp/project-a",
        git_branch="main",
        hostname="host",
        terminal_program="Apple_Terminal",
        started_at=f"{date_str}T09:00:00+08:00",
        raw_log_path=str(trail_home / "day-session-1.jsonl"),
    )
    db.replace_turns(
        "day-session-1",
        [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "Morning question",
                "started_at": f"{date_str}T09:00:10+08:00",
                "ended_at": f"{date_str}T09:00:10+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": "Morning answer",
                "started_at": f"{date_str}T09:00:15+08:00",
                "ended_at": f"{date_str}T09:00:15+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
        ],
    )

    db.create_session(
        session_id="day-session-2",
        tool="codex",
        argv_redacted="codex",
        cwd="/tmp/project-b",
        repo_root="/tmp/project-b",
        git_branch="develop",
        hostname="host",
        terminal_program="Apple_Terminal",
        started_at=f"{date_str}T14:00:00+08:00",
        raw_log_path=str(trail_home / "day-session-2.jsonl"),
    )
    db.replace_turns(
        "day-session-2",
        [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "Afternoon question",
                "started_at": f"{date_str}T14:00:10+08:00",
                "ended_at": f"{date_str}T14:00:10+08:00",
                "parser_version": "v0-test",
                "confidence": 1.0,
            },
        ],
    )
    db.close()
    return db_file


def test_day_command_with_sessions(trail_home):
    _create_day_sessions(trail_home, date_str="2026-03-10")

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["day", "--date", "2026-03-10"])
        output = stdout.getvalue()

    assert exit_code == 0
    assert "2026-03-10" in output
    assert "Sessions: 2" in output
    assert "claude" in output
    assert "codex" in output
    assert "project-a" in output or "project-b" in output
    assert "Recent turns:" in output


def test_day_command_with_no_sessions(trail_home):
    # Ensure the db exists but has no sessions for the queried date
    db_file = str(trail_home / "trail.db")
    db = TrailDB(path=db_file)
    db.close()

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["day", "--date", "2026-01-01"])
        output = stdout.getvalue()

    assert exit_code == 0
    assert "2026-01-01" in output
    assert "Sessions: 0" in output


def test_day_command_date_formatting(trail_home):
    _create_day_sessions(trail_home, date_str="2026-03-10")

    with mock.patch("sys.stdout", new=io.StringIO()) as stdout:
        exit_code = main(["day", "--date", "2026-03-10"])
        output = stdout.getvalue()

    assert exit_code == 0
    # Verify the header line has the date
    lines = output.strip().splitlines()
    assert any("2026-03-10" in line for line in lines)
    # Verify tool breakdown is present
    assert "Tools:" in output


if __name__ == "__main__":
    unittest.main()
