from __future__ import annotations

import json
import os
import tempfile
import unittest

from trail.config import (
    config_path,
    get_config_value,
    init_config,
    load_config,
    parse_config_value,
    set_config_value,
    unset_config_value,
)


class ConfigTests(unittest.TestCase):
    def test_load_config_returns_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                config = load_config()
                self.assertEqual(get_config_value(config, "watch.mode"), "turns")
                self.assertEqual(get_config_value(config, "capture.submitted_input_only.claude"), True)
                self.assertEqual(get_config_value(config, "markdown.sync_interval_seconds"), 2.0)
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

    def test_init_and_reload_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("TRAIL_HOME")
            os.environ["TRAIL_HOME"] = tmpdir
            try:
                path = init_config()
                self.assertEqual(path, config_path())
                self.assertTrue(path.exists())
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(raw["watch"]["mode"], "turns")
            finally:
                if old is None:
                    os.environ.pop("TRAIL_HOME", None)
                else:
                    os.environ["TRAIL_HOME"] = old

    def test_set_and_unset_config_value(self) -> None:
        config = load_config()
        updated = set_config_value(config, "watch.settle_seconds", 2.5)
        self.assertEqual(get_config_value(updated, "watch.settle_seconds"), 2.5)
        cleaned = unset_config_value(updated, "watch.settle_seconds")
        self.assertIsNone(get_config_value(cleaned, "watch.settle_seconds"))

    def test_parse_config_value(self) -> None:
        self.assertEqual(parse_config_value("true"), True)
        self.assertEqual(parse_config_value("3"), 3)
        self.assertEqual(parse_config_value("2.5"), 2.5)
        self.assertEqual(parse_config_value('{"mode":"events"}'), {"mode": "events"})
        self.assertEqual(parse_config_value("plain-text"), "plain-text")


if __name__ == "__main__":
    unittest.main()
