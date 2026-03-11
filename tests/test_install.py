from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallScriptTests(unittest.TestCase):
    def test_install_script_sets_up_launcher_and_zsh_wrappers_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            rc_path = home / ".zshrc"
            rc_path.write_text("# existing config\nexport FOO=1\n", encoding="utf-8")

            env = os.environ.copy()
            env["HOME"] = tmpdir
            env["SHELL"] = "/bin/zsh"

            for _ in range(2):
                result = subprocess.run(
                    ["bash", str(ROOT / "install.sh"), "--skip-doctor"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=ROOT,
                    env=env,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode())

            launcher = home / ".local" / "bin" / "trail"
            self.assertTrue(launcher.is_symlink())
            self.assertEqual(launcher.resolve(), (ROOT / "bin" / "trail").resolve())

            rc_text = rc_path.read_text(encoding="utf-8")
            self.assertEqual(rc_text.count("# >>> trail path >>>"), 1)
            self.assertEqual(rc_text.count("# >>> trail wrappers >>>"), 1)
            self.assertIn('export PATH="$HOME/.local/bin:$PATH"', rc_text)
            self.assertIn('claude() { command trail wrap claude "$@"; }', rc_text)
            self.assertNotIn('codex', rc_text)

            config_path = home / ".trail" / "config.json"
            self.assertTrue(config_path.exists())

            help_result = subprocess.run(
                [str(launcher), "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr.decode())
            self.assertIn("watch", help_result.stdout.decode())


if __name__ == "__main__":
    unittest.main()
