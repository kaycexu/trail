from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from trail.paths import trail_home


DEFAULT_CONFIG: dict[str, Any] = {
    "watch": {
        "mode": "turns",
        "poll_interval": 0.5,
        "settle_seconds": 1.0,
    },
    "capture": {
        "submitted_input_only": {
            "claude": True,
        },
    },
    "markdown": {
        "sync_interval_seconds": 2.0,
    },
}


def config_path() -> Path:
    return trail_home() / "config.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_CONFIG)
    return _merge_dicts(deepcopy(DEFAULT_CONFIG), raw)


def save_config(config: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def init_config(force: bool = False) -> Path:
    path = config_path()
    if path.exists() and not force:
        return path
    save_config(load_config())
    return path


def get_config_value(config: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_config_value(config: dict[str, Any], dotted_key: str, value: Any) -> dict[str, Any]:
    updated = deepcopy(config)
    current: dict[str, Any] = updated
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value
    return updated


def unset_config_value(config: dict[str, Any], dotted_key: str) -> dict[str, Any]:
    updated = deepcopy(config)
    current: Any = updated
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return updated
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)
    return updated


def parse_config_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            base[key] = _merge_dicts(base[key], value)
        else:
            base[key] = value
    return base
