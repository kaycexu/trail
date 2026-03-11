from __future__ import annotations

from datetime import datetime

from trail.redact import compact_text


def _format_session_duration(started_at: str, ended_at: str | None) -> str:
    if not ended_at:
        return "-"
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError:
        return "-"
    seconds = max(0, int((end - start).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{rem:02d}s"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h{rem_minutes:02d}m"


def _format_turn_label(role: str, tool: str) -> str:
    if role == "user":
        return "You"
    if tool == "claude":
        return "Claude"
    if tool == "codex":
        return "Codex"
    return role.capitalize()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


now_iso = _now_iso


def _session_preview(turns) -> str:
    if not turns:
        return ""
    for turn in turns:
        text = compact_text(turn["text_redacted"], 120)
        if text:
            return text
    return ""
