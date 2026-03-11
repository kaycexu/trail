from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trail.doctor import format_doctor_report, run_doctor


class DoctorTests(unittest.TestCase):
    def test_run_doctor_reports_expected_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rc_path = Path(tmpdir) / ".zshrc"
            rc_path.write_text('claude() { command trail wrap claude "$@"; }\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"TRAIL_HOME": tmpdir}, clear=False):
                with mock.patch("trail.doctor.Path.home", return_value=Path(tmpdir)):
                    with mock.patch("trail.doctor.shutil.which", side_effect=lambda cmd: f"/usr/local/bin/{cmd}"):
                        checks = run_doctor()
        names = [check.name for check in checks]
        self.assertIn("trail-home", names)
        self.assertIn("trail-command", names)
        self.assertIn("claude-command", names)
        self.assertIn("shell-wrapper", names)

    def test_format_doctor_report_includes_fix_lines(self) -> None:
        report = format_doctor_report(run_doctor(shell="fish"))
        self.assertIn("shell-wrapper", report)


if __name__ == "__main__":
    unittest.main()
