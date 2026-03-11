from __future__ import annotations

import unittest

from trail.adapters import filter_output_for_storage, postprocess_turns
from trail.line_buffer import EditableLineBuffer


class AdapterTests(unittest.TestCase):
    def test_line_buffer_supports_mid_line_editing(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("abc\x1b[D\x1b[DX\n")
        self.assertEqual(submissions, ["aXbc"])

    def test_line_buffer_supports_delete_key(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("abdc\x1b[D\x1b[D\x1b[3~\n")
        self.assertEqual(submissions, ["abc"])

    def test_line_buffer_handles_partial_escape_sequences(self) -> None:
        buffer = EditableLineBuffer()
        self.assertEqual(buffer.feed("abc\x1b["), [])
        submissions = buffer.feed("DX\n")
        self.assertEqual(submissions, ["abXc"])

    def test_line_buffer_supports_home_and_end_shortcuts(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("abc\x01X\x05Y\n")
        self.assertEqual(submissions, ["XabcY"])

    def test_line_buffer_supports_ctrl_u_ctrl_k_and_ctrl_w(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("one two three\x17\n")
        self.assertEqual(submissions, ["one two"])

        submissions = buffer.feed("abcdef\x01\x1b[C\x15Z\n")
        self.assertEqual(submissions, ["Zbcdef"])

        submissions = buffer.feed("abcdef\x01\x1b[C\x0bZ\n")
        self.assertEqual(submissions, ["aZ"])

    def test_line_buffer_supports_word_motion_and_deletion(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("one two three\x1bbX\n")
        self.assertEqual(submissions, ["one two Xthree"])

        submissions = buffer.feed("one two three\x1bb\x1bd\n")
        self.assertEqual(submissions, ["one two"])

        submissions = buffer.feed("one two three\x1b\x7f\n")
        self.assertEqual(submissions, ["one two"])

    def test_line_buffer_ignores_blank_submissions(self) -> None:
        buffer = EditableLineBuffer()
        submissions = buffer.feed("   \n")
        self.assertEqual(submissions, [])

    def test_claude_output_filter_keeps_answer_and_drops_tui_noise(self) -> None:
        payload = (
            " ▐▛███▜▌ClaudeCodev2.1.72\n"
            "❯ 这个目录下面当前有多少agent\n"
            "⏺Searchedfor2patterns,read2files(ctrl+otoexpand)\n"
            "⏺当前目录下有1个主agent和1个子agent。\n"
            "另外还有4个skill目录，但它们没有独立的AGENTS.md。\n"
            "────────────────────────────────────────\n"
            "? for shortcuts\n"
        )
        filtered = filter_output_for_storage(
            "claude",
            payload,
            "这个目录下面当前有多少agent",
        )
        self.assertEqual(
            filtered,
            "当前目录下有1个主agent和1个子agent。\n另外还有4个skill目录，但它们没有独立的AGENTS.md。",
        )

    def test_claude_output_filter_drops_subscription_and_exit_noise(self) -> None:
        payload = (
            "───────�\n"
            "ClaudeinChromerequiresaclaude.aisubscription\n"
            "PressCtrl-Cagaintoexit\n"
            "8MCPserversfailed·/mcp\n"
        )
        filtered = filter_output_for_storage("claude", payload, "Reply with exactly OK.")
        self.assertIsNone(filtered)

    def test_claude_output_filter_drops_real_spinner_fragments(self) -> None:
        payload = (
            "?for\n"
            "shortcuts\n"
            "1 MCP server needs auth\n"
            "✢ Sketching…\n"
            "✻chng\n"
            "ethi\n"
            "好的，你想测试什么功能？告诉我具体内容，我来配合。\n"
            "[38;2;136;13\n"
        )
        filtered = filter_output_for_storage("claude", payload, "我们现在就只是测试一个功能")
        self.assertEqual(filtered, "好的，你想测试什么功能？告诉我具体内容，我来配合。")

    def test_claude_output_filter_drops_status_only_lines(self) -> None:
        payload = (
            "✢Musing…\n"
            "Musing…8\n"
            "Gallivanting…\n"
            "(thinking with high effort)\n"
            "ANSWER:Hello world\n"
        )
        filtered = filter_output_for_storage("claude", payload, "Test")
        self.assertEqual(filtered, "ANSWER:Hello world")

    def test_claude_output_filter_strips_prompt_echo_and_marker(self) -> None:
        payload = (
            "❯ Reply with exactly OK.\n"
            "⏺ OK\n"
        )
        filtered = filter_output_for_storage("claude", payload, "Reply with exactly OK.")
        self.assertEqual(filtered, "OK")

    def test_claude_output_filter_drops_vscode_edit_prompt_from_public_issue(self) -> None:
        payload = (
            "Opened changes in Visual Studio Code - Insiders ⧉\n"
            "Save file to continue…\n"
            "Do you want to make this edit to Capacity.ps1?\n"
            "1. Yes\n"
            "2. Yes, allow all edits during this session (shift+tab)\n"
            "3. No, and tell Claude what to do differently (esc)\n"
            "Updated the file.\n"
        )
        filtered = filter_output_for_storage("claude", payload, "do thing")
        self.assertEqual(filtered, "Updated the file.")

    def test_claude_output_filter_drops_debug_log_block_from_public_issue(self) -> None:
        payload = (
            '[log_bf3ee7, request-id: "req_123"] post https://api.anthropic.com/v1/messages?beta=true succeeded with status 200 in 2647ms\n'
            "[log_bf3ee7] response start {\n"
            "url: 'https://api.anthropic.com/v1/messages?beta=true',\n"
            "status: 200,\n"
            "headers: {\n"
            "content-type: 'application/json'\n"
            "}\n"
            "}\n"
            "Actual answer\n"
        )
        filtered = filter_output_for_storage("claude", payload, "test")
        self.assertEqual(filtered, "Actual answer")

    def test_claude_output_filter_drops_permission_notification_from_public_docs(self) -> None:
        payload = (
            "Claude needs your permission to use Bash\n"
            "Actual answer\n"
        )
        filtered = filter_output_for_storage("claude", payload, "test")
        self.assertEqual(filtered, "Actual answer")

    def test_generic_output_filter_passes_through_text(self) -> None:
        payload = "plain output\nwith two lines\n"
        filtered = filter_output_for_storage("python3", payload, None)
        self.assertEqual(filtered, payload)

    def test_claude_postprocess_strips_inline_ui_noise_from_assistant_turn(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "我打算用这个目录管理我日常的AI相关的学习和积累，配合Obsidian的仓库，你觉得怎么样",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    '先看看目录现状。 ⎿ ls -la /Users/xujian/ai Plugin updated: superpowers · Restart to apply "**/*" '
                    "✶Hach hig… athi hig… 挺好的思路，用Obsidian管理AI学习笔记很合适。 "
                    "✢ Vibing… ⎿ Tip: Create skills by adding .md files tointerrupt "
                    "明白，偏实用和工具向。"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        assistant_text = processed[1]["text_redacted"]
        self.assertIn("先看看目录现状。", assistant_text)
        self.assertIn("挺好的思路，用Obsidian管理AI学习笔记很合适。", assistant_text)
        self.assertIn("明白，偏实用和工具向。", assistant_text)
        self.assertNotIn("Plugin updated", assistant_text)
        self.assertNotIn("Tip:", assistant_text)
        self.assertNotIn("Vibing", assistant_text)
        self.assertNotIn("tointerrupt", assistant_text)


    def test_claude_postprocess_drops_tool_actions_and_permission_noise(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "前期我们多沟通、你尽可能多得了解我的需求和现状，之后就可以越用越顺",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "好的，我先把原则整理到 CLAUDE.md。 Fetch(https://example.com) Received 316.3KB (200 OK) "
                    "Create file CLAUDE.md Do you want to create CLAUDE.md? Yes, allow all edits during this session "
                    "Wrote 17 lines to CLAUDE.md 现在已经写好了，你后面可以继续边用边调整。"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        assistant_text = processed[1]["text_redacted"]
        self.assertIn("好的，我先把原则整理到 CLAUDE.md。", assistant_text)
        self.assertIn("现在已经写好了，你后面可以继续边用边调整。", assistant_text)
        self.assertNotIn("Fetch(", assistant_text)
        self.assertNotIn("Received", assistant_text)
        self.assertNotIn("Create file", assistant_text)
        self.assertNotIn("Do you want to create", assistant_text)
        self.assertNotIn("Yes, allow all edits", assistant_text)
        self.assertNotIn("Wrote 17 lines", assistant_text)


    def test_claude_postprocess_drops_burrowing_thought_and_btw_tip(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "帮我看看这个项目",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "Burrowing… (thought for 1s) Tip: Use /btw to ask a quick side question without interrupting Claude's current work "
                    "这个项目的核心是用多 agent 编排任务。"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        assistant_text = processed[1]["text_redacted"]
        self.assertEqual(assistant_text, "这个项目的核心是用多 agent 编排任务。")

    def test_claude_postprocess_drops_fragmented_status_lines(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "详细看看这个是怎么做到的",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": "main Ima…\nwig… rrwi Buro\n(thought for 1s)\nTip: Use /btw to ask a quick side question without interrupting Claude's current work\n真正的回答。",
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(processed[1]["text_redacted"], "真正的回答。")

    def test_claude_postprocess_strips_mixed_inline_status_and_tool_fragments(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "详细看看这个是怎么做到的",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "Imagining… ✶Imagining… (thought for 1s) main 这是一个很有意思的帖子。让我再去看看他实际的项目页面，了解技术实现细节。 "
                    "✳Imagining… Imagining… Fetch(https://howisfelix.today/) ⎿Fetching… "
                    "⎿Tip: Use /btw to ask a quick side question without interrupting Claude's current work "
                    "这个项目非常有意思！让我再看看他的开源代码仓库，了解更多实现细节。 "
                    "⎿Tip: Use /btw to ask a quick side question without interrupting Claude's current work "
                    "Received138KB(200OK)"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(
            processed[1]["text_redacted"],
            "这是一个很有意思的帖子。让我再去看看他实际的项目页面，了解技术实现细节。\n这个项目非常有意思！让我再看看他的开源代码仓库，了解更多实现细节。",
        )

    def test_claude_postprocess_strips_inline_shell_command_prefix(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "帮我整理一下",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "先看看现有的目录结构。 ls /Users/xujian/ai/ -R 2>/dev/null; ls /Users/xujian/ai/ "
                    "仓库刚起步，只有一个 ai/欢迎.md。"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(
            processed[1]["text_redacted"],
            "先看看现有的目录结构。\n仓库刚起步，只有一个 ai/欢迎.md。",
        )

    def test_claude_postprocess_drops_vscode_edit_prompt_from_public_issue(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "edit it",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "Opened changes in Visual Studio Code - Insiders ⧉\n"
                    "Save file to continue…\n"
                    "Do you want to make this edit to Capacity.ps1?\n"
                    "1. Yes\n"
                    "2. Yes, allow all edits during this session (shift+tab)\n"
                    "3. No, and tell Claude what to do differently (esc)\n"
                    "Updated the file."
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(processed[1]["text_redacted"], "Updated the file.")

    def test_claude_postprocess_drops_debug_log_block_from_public_issue(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "debug it",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    '[log_bf3ee7, request-id: "req_123"] post https://api.anthropic.com/v1/messages?beta=true succeeded with status 200 in 2647ms\n'
                    "[log_bf3ee7] response start {\n"
                    "url: 'https://api.anthropic.com/v1/messages?beta=true',\n"
                    "status: 200,\n"
                    "headers: {\n"
                    "content-type: 'application/json'\n"
                    "}\n"
                    "}\n"
                    "Actual answer"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(processed[1]["text_redacted"], "Actual answer")

    def test_claude_postprocess_drops_mode_banner_from_public_docs(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "hi",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": (
                    "? for shortcuts\n"
                    "⏵⏵ accept edits on (shift+tab to cycle)\n"
                    "⏸ plan mode on (shift+tab to cycle)\n"
                    "⏵⏵ bypass permissions on (shift+tab to cycle)\n"
                    "Real answer"
                ),
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(processed[1]["text_redacted"], "Real answer")

    def test_claude_postprocess_drops_permission_notification_from_public_docs(self) -> None:
        turns = [
            {
                "seq": 1,
                "role": "user",
                "text_redacted": "hi",
            },
            {
                "seq": 2,
                "role": "assistant",
                "text_redacted": "Claude needs your permission to use Bash\nActual answer",
            },
        ]

        processed = postprocess_turns("claude", turns)

        self.assertEqual(len(processed), 2)
        self.assertEqual(processed[1]["text_redacted"], "Actual answer")


if __name__ == "__main__":
    unittest.main()
