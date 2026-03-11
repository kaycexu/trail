from __future__ import annotations

import unittest

from trail.turns import extract_turns


class TurnExtractionTests(unittest.TestCase):
    def test_generic_turns_track_user_and_assistant(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "hel",
                "ts": "2026-03-10T15:00:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "lo\n",
                "ts": "2026-03-10T15:00:01+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "world\n",
                "ts": "2026-03-10T15:00:02+08:00",
            },
        ]
        turns = extract_turns(events)
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "hello"), ("assistant", "world")],
        )

    def test_generic_turns_apply_backspace(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "abd\x7fc\n",
                "ts": "2026-03-10T15:00:00+08:00",
            }
        ]
        turns = extract_turns(events)
        self.assertEqual([(turn["role"], turn["text_redacted"]) for turn in turns], [("user", "abc")])

    def test_claude_argv_prompt_keeps_assistant_reply(self) -> None:
        events = [
            {
                "event_type": "meta",
                "stream": "meta",
                "payload_text_redacted": None,
                "ts": "2026-03-10T15:39:03+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "OK\n",
                "ts": "2026-03-10T15:39:11+08:00",
            },
        ]

        turns = extract_turns(
            events,
            tool="claude",
            initial_user_text="Reply with exactly OK.",
            initial_user_started_at="2026-03-10T15:39:03+08:00",
        )

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "Reply with exactly OK."),
                ("assistant", "OK"),
            ],
        )

    def test_claude_drops_exit_noise_after_user_prompt(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Reply with exactly OK.\n",
                "ts": "2026-03-10T15:41:49+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "\nPress Ctrl-C again to exit\n\n",
                "ts": "2026-03-10T15:42:35+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "\nResume this session with:\nclaude --resume abc\n",
                "ts": "2026-03-10T15:44:21+08:00",
            },
        ]

        turns = extract_turns(events, tool="claude")

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Reply with exactly OK.")],
        )

    def test_claude_turns_deduplicate_repeated_output_chunks(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Reply with exactly OK.\n",
                "ts": "2026-03-10T15:41:49+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "⏺ OK\n",
                "ts": "2026-03-10T15:41:50+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "⏺ OK\n",
                "ts": "2026-03-10T15:41:51+08:00",
            },
        ]
        turns = extract_turns(events, tool="claude")
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Reply with exactly OK."), ("assistant", "OK")],
        )

    def test_claude_turns_replace_growing_partial_chunks(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Test\n",
                "ts": "2026-03-10T15:41:49+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "He\n",
                "ts": "2026-03-10T15:41:50+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Hello\n",
                "ts": "2026-03-10T15:41:51+08:00",
            },
        ]
        turns = extract_turns(events, tool="claude")
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Test"), ("assistant", "Hello")],
        )

    def test_claude_turns_drop_real_spinner_fragments_before_answer(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "我们现在就只是测试一个功能\n",
                "ts": "2026-03-10T16:27:33+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "✢ Sketching…\n✻chng\nethi\n",
                "ts": "2026-03-10T16:27:34+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "好的，你想测试什么功能？告诉我具体内容，我来配合。\n[38;2;136;13\n",
                "ts": "2026-03-10T16:27:38+08:00",
            },
        ]
        turns = extract_turns(events, tool="claude")
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "我们现在就只是测试一个功能"), ("assistant", "好的，你想测试什么功能？告诉我具体内容，我来配合。")],
        )

    def test_claude_turns_drop_status_only_progress_lines(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Test\n",
                "ts": "2026-03-10T16:27:33+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "✢Musing…\nMusing…8\nGallivanting…\n(thinking with high effort)\n",
                "ts": "2026-03-10T16:27:34+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "ANSWER:Hello world\n",
                "ts": "2026-03-10T16:27:38+08:00",
            },
        ]
        turns = extract_turns(events, tool="claude")
        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Test"), ("assistant", "ANSWER:Hello world")],
        )

    def test_claude_turns_split_multi_turn_session_when_new_user_prompt_arrives(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "First question\n",
                "ts": "2026-03-11T10:00:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "First answer\n",
                "ts": "2026-03-11T10:00:05+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Second question\n",
                "ts": "2026-03-11T10:01:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Second answer\n",
                "ts": "2026-03-11T10:01:10+08:00",
            },
        ]

        turns = extract_turns(events, tool="claude")

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "First question"),
                ("assistant", "First answer"),
                ("user", "Second question"),
                ("assistant", "Second answer"),
            ],
        )


    def test_claude_turns_drop_burrowing_thought_and_btw_tip_noise(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Test\n",
                "ts": "2026-03-11T11:00:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Burrowing…\n(thought for 1s)\nTip: Use /btw to ask a quick side question without interrupting Claude's current work\nReal answer\n",
                "ts": "2026-03-11T11:00:05+08:00",
            },
        ]

        turns = extract_turns(events, tool="claude")

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [("user", "Test"), ("assistant", "Real answer")],
        )

    def test_claude_turns_strip_stdout_echo_of_next_user_prompt(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "First question\n",
                "ts": "2026-03-11T12:00:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "First answer\n",
                "ts": "2026-03-11T12:00:05+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "the next prompt text\n",
                "ts": "2026-03-11T12:00:09+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "the next prompt text\n",
                "ts": "2026-03-11T12:00:10+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Second answer\n",
                "ts": "2026-03-11T12:00:12+08:00",
            },
        ]

        turns = extract_turns(events, tool="claude")

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "First question"),
                ("assistant", "First answer"),
                ("user", "the next prompt text"),
                ("assistant", "Second answer"),
            ],
        )

    def test_claude_turns_drop_replayed_previous_answer_after_follow_up(self) -> None:
        events = [
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "First question\n",
                "ts": "2026-03-11T12:10:00+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "First answer line one\nFirst answer line two\n",
                "ts": "2026-03-11T12:10:05+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdin",
                "payload_text_redacted": "Second question\n",
                "ts": "2026-03-11T12:10:10+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Burrowing…\n",
                "ts": "2026-03-11T12:10:11+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Fresh answer intro\n",
                "ts": "2026-03-11T12:10:12+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Fetch(https://example.com)\n",
                "ts": "2026-03-11T12:10:13+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "First answer line one\nFirst answer line two\n",
                "ts": "2026-03-11T12:10:14+08:00",
            },
            {
                "event_type": "text",
                "stream": "stdout",
                "payload_text_redacted": "Fresh answer outro\n",
                "ts": "2026-03-11T12:10:15+08:00",
            },
        ]

        turns = extract_turns(events, tool="claude")

        self.assertEqual(
            [(turn["role"], turn["text_redacted"]) for turn in turns],
            [
                ("user", "First question"),
                ("assistant", "First answer line one First answer line two"),
                ("user", "Second question"),
                ("assistant", "Fresh answer intro Fresh answer outro"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
