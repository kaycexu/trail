from __future__ import annotations

import os
import tempfile
import unittest

from trail.db import TrailDB
from trail.parser import extract_prompt_from_session
from trail.watch import PendingTurn, _compute_turn_emissions, _extract_live_turns, _resolve_session


class WatchTests(unittest.TestCase):
    def test_extract_prompt_from_redacted_argv(self) -> None:
        prompt = extract_prompt_from_session("claude", "claude -p 'Reply with exactly OK.'")
        self.assertEqual(prompt, "Reply with exactly OK.")

    def test_extract_prompt_from_invalid_argv_returns_none(self) -> None:
        prompt = extract_prompt_from_session("claude", "claude -p 'unterminated")
        self.assertIsNone(prompt)

    def test_extract_live_turns_for_claude_print_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = TrailDB(path=f"{tmpdir}/trail.db")
            session_id = "session-1"
            db.create_session(
                session_id=session_id,
                tool="claude",
                argv_redacted="claude -p 'Reply with exactly OK.'",
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
                stream="stdout",
                event_type="text",
                ts="2026-03-10T15:39:11+08:00",
                payload_text_redacted="OK\n",
                payload_meta=None,
            )
            session = db.get_session(session_id)
            turns = _extract_live_turns(db, session)
            db.close()

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "Reply with exactly OK."),
                ("assistant", "OK"),
            ],
        )

    def test_extract_live_turns_for_interactive_session_without_finished_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
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
            db.add_event(
                session_id=session_id,
                seq=1,
                stream="stdin",
                event_type="text",
                ts="2026-03-10T15:39:10+08:00",
                payload_text_redacted="What changed?\n",
                payload_meta=None,
            )
            db.add_event(
                session_id=session_id,
                seq=2,
                stream="stdout",
                event_type="text",
                ts="2026-03-10T15:39:11+08:00",
                payload_text_redacted="⏺ Updated the parser.\n",
                payload_meta=None,
            )
            session = db.get_session(session_id)
            turns = _extract_live_turns(db, session)
            db.close()

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "What changed?"), ("assistant", "Updated the parser.")],
        )

    def test_compute_turn_emissions_debounces_assistant_updates(self) -> None:
        printed: dict[int, str] = {}
        pending: dict[int, PendingTurn] = {}
        turns = [
            {"seq": 1, "role": "user", "text_redacted": "Prompt"},
            {"seq": 2, "role": "assistant", "text_redacted": "Sketching…"},
        ]
        emissions, printed, pending = _compute_turn_emissions(
            turns,
            printed=printed,
            pending=pending,
            now=0.0,
            settle_seconds=1.0,
            force_flush=False,
        )
        self.assertEqual([(prefix, turn["role"], turn["text_redacted"]) for prefix, turn in emissions], [("-", "user", "Prompt")])
        self.assertIn(2, pending)

        turns[1] = {"seq": 2, "role": "assistant", "text_redacted": "Final answer"}
        emissions, printed, pending = _compute_turn_emissions(
            turns,
            printed=printed,
            pending=pending,
            now=0.5,
            settle_seconds=1.0,
            force_flush=False,
        )
        self.assertEqual(emissions, [])
        self.assertEqual(pending[2].turn["text_redacted"], "Final answer")

        emissions, printed, pending = _compute_turn_emissions(
            turns,
            printed=printed,
            pending=pending,
            now=1.6,
            settle_seconds=1.0,
            force_flush=False,
        )
        self.assertEqual(
            [(prefix, turn["role"], turn["text_redacted"]) for prefix, turn in emissions],
            [("-", "assistant", "Final answer")],
        )

    def test_compute_turn_emissions_force_flushes_pending_assistant(self) -> None:
        printed: dict[int, str] = {}
        pending = {
            2: PendingTurn(
                turn={"seq": 2, "role": "assistant", "text_redacted": "Final answer"},
                updated_at=10.0,
            )
        }
        emissions, printed, pending = _compute_turn_emissions(
            [{"seq": 2, "role": "assistant", "text_redacted": "Final answer"}],
            printed=printed,
            pending=pending,
            now=10.1,
            settle_seconds=5.0,
            force_flush=True,
        )
        self.assertEqual(
            [(prefix, turn["role"], turn["text_redacted"]) for prefix, turn in emissions],
            [("-", "assistant", "Final answer")],
        )

    def test_resolve_session_skips_stale_active_process_and_picks_live_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = TrailDB(path=f"{tmpdir}/trail.db")
            stale_id = "stale-session"
            live_id = "live-session"

            db.create_session(
                session_id=stale_id,
                tool="claude",
                argv_redacted="claude",
                cwd="/tmp/project",
                repo_root="/tmp/project",
                git_branch="main",
                hostname="host",
                terminal_program="Apple_Terminal",
                started_at="2026-03-11T11:00:00+08:00",
                raw_log_path=f"{tmpdir}/stale.jsonl",
            )
            db.set_session_process(stale_id, child_pid=-1)

            db.create_session(
                session_id=live_id,
                tool="claude",
                argv_redacted="claude",
                cwd="/tmp/project",
                repo_root="/tmp/project",
                git_branch="main",
                hostname="host",
                terminal_program="Apple_Terminal",
                started_at="2026-03-11T10:59:00+08:00",
                raw_log_path=f"{tmpdir}/live.jsonl",
            )
            db.set_session_process(live_id, child_pid=os.getpid())

            session = _resolve_session(db, None, tool="claude", repo=None)
            db.close()

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["id"], live_id)


if __name__ == "__main__":
    unittest.main()
