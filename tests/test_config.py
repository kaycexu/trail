from __future__ import annotations

import json
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


def test_load_config_returns_defaults_when_missing(trail_home):
    config = load_config()
    assert get_config_value(config, "watch.mode") == "turns"
    assert get_config_value(config, "capture.submitted_input_only.claude") is True
    assert get_config_value(config, "markdown.sync_interval_seconds") == 2.0


def test_init_and_reload_config(trail_home):
    path = init_config()
    assert path == config_path()
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["watch"]["mode"] == "turns"


class ConfigTests(unittest.TestCase):
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
