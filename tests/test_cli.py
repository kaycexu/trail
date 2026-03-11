from __future__ import annotations

import os
import tempfile
import unittest
import io
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


    def test_watch_uses_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                config = set_config_value(init_and_load(), "watch.mode", "events")
                config = set_config_value(config, "watch.poll_interval", 0.25)
                save_config(config)
                with mock.patch("trail.cli.watch_session", return_value=0) as watch_session:
                    exit_code = main(["watch", "--tool", "claude"])
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(exit_code, 0)
        args = watch_session.call_args.args[1]
        self.assertEqual(args.mode, "events")
        self.assertEqual(args.poll_interval, 0.25)

    def test_rebuild_and_reindex_commands_recompute_turns(self) -> None:
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
                    payload_text_redacted="✢Musing…\nANSWER:Hello world\n",
                    payload_meta=None,
                )
                db.close()

                with mock.patch("sys.stdout", new=io.StringIO()):
                    rebuild_exit = main(["rebuild", session_id])
                    reindex_exit = main(["reindex", "--tool", "claude"])

                db = TrailDB(path=f"{tmpdir}/trail.db")
                turns = [(turn["role"], turn["text_redacted"]) for turn in db.get_session_turns(session_id)]
                db.close()
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(rebuild_exit, 0)
        self.assertEqual(reindex_exit, 0)
        self.assertEqual(turns, [("user", "Test"), ("assistant", "ANSWER:Hello world")])

    def test_show_renders_transcript_style_output(self) -> None:
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
                    started_at="2026-03-10T15:39:03+08:00",
                    raw_log_path=f"{tmpdir}/session-2.jsonl",
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
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(exit_code, 0)
        self.assertIn("Transcript", output)
        self.assertIn("Markdown ", output)
        self.assertIn("Preview  First line Second line", output)
        self.assertIn("[15:39:10] You", output)
        self.assertIn("  First line", output)
        self.assertIn("  Second line", output)
        self.assertIn("[15:39:11] Claude", output)
        self.assertIn("  ANSWER:Hello world", output)
        self.assertIn("  Another line", output)
        self.assertNotIn("parser=", output)

    def test_show_raw_includes_event_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                db = TrailDB(path=f"{tmpdir}/trail.db")
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
                    raw_log_path=f"{tmpdir}/session-3.jsonl",
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
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(exit_code, 0)
        self.assertIn("Raw Events", output)
        self.assertIn("[15:39:03] meta/start", output)
        self.assertIn("[15:39:10] stdin/text Question", output)
        self.assertIn("[15:39:11] stdout/text Answer", output)
        self.assertIn("                   More", output)

    def test_show_raw_limit_keeps_only_latest_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                db = TrailDB(path=f"{tmpdir}/trail.db")
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
                    raw_log_path=f"{tmpdir}/session-4.jsonl",
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
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

        self.assertEqual(exit_code, 0)
        self.assertNotIn("stdout/text one", output)
        self.assertIn("stdout/text two", output)
        self.assertIn("stdout/text three", output)




def init_and_load():
    init_config(force=True)
    from trail.config import load_config

    return load_config()


if __name__ == "__main__":
    unittest.main()
