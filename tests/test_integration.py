from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from trail.db import TrailDB


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_fake_claude_session_stores_only_final_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["TRAIL_HOME"] = tmpdir
            env["PATH"] = f"{ROOT / 'tests' / 'bin'}:{env['PATH']}"

            result = subprocess.run(
                [sys.executable, "-m", "trail", "claude"],
                input=b"abc\x1b[D\x1b[DX\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode())

            db = TrailDB(path=f"{tmpdir}/trail.db")
            session = db.list_sessions(limit=1, tool="claude")[0]
            stdin_events = [
                row["payload_text_redacted"]
                for row in db.get_session_events(session["id"])
                if row["stream"] == "stdin"
            ]
            turns = [(turn["role"], turn["text_redacted"]) for turn in db.get_session_turns(session["id"])]
            db.close()
            markdown_paths = list(Path(tmpdir).glob("transcripts/**/*.md"))

        self.assertEqual(stdin_events, ["aXbc\n"])
        self.assertEqual(turns[0], ("user", "aXbc"))
        self.assertEqual(len(markdown_paths), 1)

    def test_symlinked_bin_trail_runs_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "trail"
            target.symlink_to(ROOT / "bin" / "trail")
            result = subprocess.run(
                [str(target), "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("watch", result.stdout.decode())

    def test_fake_claude_session_keeps_raw_stdout_and_derives_clean_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["TRAIL_HOME"] = tmpdir
            env["PATH"] = f"{ROOT / 'tests' / 'bin'}:{env['PATH']}"
            env["TRAIL_TEST_SCENARIO"] = "streaming"

            result = subprocess.run(
                [sys.executable, "-m", "trail", "claude"],
                input=b"Test\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr.decode())

            db = TrailDB(path=f"{tmpdir}/trail.db")
            session = db.list_sessions(limit=1, tool="claude")[0]
            stdout_events = [
                row["payload_text_redacted"]
                for row in db.get_session_events(session["id"])
                if row["stream"] == "stdout"
            ]
            turns = [(turn["role"], turn["text_redacted"]) for turn in db.get_session_turns(session["id"])]
            db.close()
            markdown_paths = list(Path(tmpdir).glob("transcripts/**/*.md"))

        self.assertTrue(stdout_events)
        raw_stdout = "".join(stdout_events)
        self.assertIn("Musing", raw_stdout)
        self.assertIn("thinking with high effort", raw_stdout)
        self.assertIn("ANSWER:Hello world", raw_stdout)
        self.assertEqual(turns, [("user", "Test"), ("assistant", "ANSWER:Hello world")])
        self.assertEqual(len(markdown_paths), 1)

    def test_active_session_updates_markdown_before_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["TRAIL_HOME"] = tmpdir
            env["PATH"] = f"{ROOT / 'tests' / 'bin'}:{env['PATH']}"
            env["TRAIL_TEST_SCENARIO"] = "streaming_hold"
            Path(tmpdir, "config.json").write_text(
                '{"markdown": {"sync_interval_seconds": 0.0}}\n',
                encoding="utf-8",
            )

            proc = subprocess.Popen(
                [sys.executable, "-m", "trail", "claude"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                env=env,
            )
            transcript_file: Path | None = None
            saw_partial_answer = False
            partial_snapshot = ""
            try:
                assert proc.stdin is not None
                proc.stdin.write(b"Test\n")
                proc.stdin.flush()
                proc.stdin.close()

                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and proc.poll() is None:
                    paths = list(Path(tmpdir).glob("transcripts/**/*.md"))
                    if paths:
                        transcript_file = paths[0]
                        content = transcript_file.read_text(encoding="utf-8")
                        if 'status: "active"' in content:
                            self.assertIn('started_at: "', content)
                            self.assertIn('last_synced_at: "', content)
                        if "ANSWER:He" in content and "ANSWER:Hello world" not in content:
                            saw_partial_answer = True
                            partial_snapshot = content
                            break
                    time.sleep(0.05)

                proc.wait(timeout=5)
                stdout = proc.stdout.read().decode() if proc.stdout is not None else ""
                stderr = proc.stderr.read().decode() if proc.stderr is not None else ""
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.stderr is not None:
                    proc.stderr.close()

            self.assertEqual(proc.returncode, 0, stderr or stdout)
            self.assertIsNotNone(transcript_file)
            assert transcript_file is not None
            self.assertTrue(saw_partial_answer, partial_snapshot or transcript_file.read_text(encoding="utf-8"))

            final_markdown = transcript_file.read_text(encoding="utf-8")
            self.assertIn('status: "completed"', final_markdown)
            self.assertIn('ended_at: "', final_markdown)
            self.assertIn("### You", final_markdown)
            self.assertIn("### Claude", final_markdown)
            self.assertIn("- Started: 2026-", final_markdown)
            self.assertIn("- Ended: 2026-", final_markdown)
            self.assertIn("ANSWER:Hello world", final_markdown)


if __name__ == "__main__":
    unittest.main()
