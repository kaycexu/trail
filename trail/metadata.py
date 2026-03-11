from __future__ import annotations

import json
import re
from typing import Any

from trail.adapters import CODEX_INLINE_BREAK_RE, INLINE_BREAK_RE
from trail.formatting import _now_iso
from trail.paths import metadata_path, transcript_path
from trail.types import EventRow, SessionRow

METADATA_SCHEMA_VERSION = "trail_session_metadata/v1"
METADATA_REVISION = 1

URL_RE = re.compile(r"https?://[^\s)\]>]+")
ACTION_PATTERNS = (
    ("search", re.compile(r"^(?:MM\s*•\s*)?Searched\b\s*(.+)$", re.IGNORECASE), "query"),
    ("search", re.compile(r"^Search\((.+)\)$", re.IGNORECASE), "query"),
    ("command", re.compile(r"^(?:•\s*)?Ran\s+(.+)$", re.IGNORECASE), "command"),
    ("command", re.compile(r"^Bash\((.+)\)$", re.IGNORECASE), "command"),
    ("fetch", re.compile(r"^Fetch\((.+)\)$", re.IGNORECASE), "target"),
    ("read", re.compile(r"^Read\((.+)\)$", re.IGNORECASE), "target"),
    ("write", re.compile(r"^Write\((.+)\)$", re.IGNORECASE), "target"),
    ("edit", re.compile(r"^(?:Update|Edit)\((.+)\)$", re.IGNORECASE), "target"),
    ("grep", re.compile(r"^Grep\((.+)\)$", re.IGNORECASE), "target"),
    ("glob", re.compile(r"^Glob\((.+)\)$", re.IGNORECASE), "target"),
)


def write_session_metadata(session: SessionRow, events: list[EventRow], turns: list[dict]) -> str:
    path = metadata_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_session_metadata(session, events, turns)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def build_session_metadata(session: SessionRow, events: list[EventRow], turns: list[dict]) -> dict[str, Any]:
    status = "completed" if session["ended_at"] else "active"
    event_counts: dict[str, int] = {}
    stream_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    meta_events: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []
    urls: list[dict[str, str]] = []
    seen_activity_keys: set[tuple[str, str, str]] = set()
    seen_urls: set[str] = set()

    for event in events:
        stream = event["stream"]
        event_type = event["event_type"]
        event_counts[f"{stream}/{event_type}"] = event_counts.get(f"{stream}/{event_type}", 0) + 1
        stream_counts[stream] = stream_counts.get(stream, 0) + 1
        type_counts[event_type] = type_counts.get(event_type, 0) + 1

        if stream == "meta":
            meta_events.append(
                {
                    "seq": event["seq"],
                    "ts": event["ts"],
                    "event_type": event_type,
                    "payload": _load_payload_meta(event),
                }
            )
            continue

        payload = (event["payload_text_redacted"] or "").strip()
        if not payload:
            continue

        for url in URL_RE.findall(payload):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            urls.append({"first_seen_at": event["ts"], "stream": stream, "url": url})

        for line in _split_activity_lines(session["tool"], payload):
            action = _extract_action(line)
            if action is None:
                continue
            key = (action["kind"], action["text"], event["ts"])
            if key in seen_activity_keys:
                continue
            seen_activity_keys.add(key)
            activities.append(
                {
                    "seq": event["seq"],
                    "ts": event["ts"],
                    "stream": stream,
                    **action,
                }
            )

    turn_counts: dict[str, int] = {}
    for turn in turns:
        turn_counts[turn["role"]] = turn_counts.get(turn["role"], 0) + 1

    return {
        "kind": "trail_session_metadata",
        "schema_version": METADATA_SCHEMA_VERSION,
        "metadata_revision": METADATA_REVISION,
        "session_id": session["id"],
        "tool": session["tool"],
        "status": status,
        "started_at": session["started_at"],
        "ended_at": session["ended_at"],
        "last_synced_at": _now_iso(),
        "artifacts": {
            "raw_log_path": session["raw_log_path"],
            "transcript_path": str(transcript_path(session)),
            "metadata_path": str(metadata_path(session)),
        },
        "counts": {
            "events": len(events),
            "turns": len(turns),
            "streams": stream_counts,
            "event_types": type_counts,
            "events_by_channel": event_counts,
            "turns_by_role": turn_counts,
            "meta_events": len(meta_events),
            "activities": len(activities),
            "urls": len(urls),
        },
        "meta_events": meta_events,
        "activities": activities,
        "urls": urls,
    }


def _split_activity_lines(tool: str, payload: str) -> list[str]:
    normalized = payload.replace("\r", "\n")
    if tool == "claude":
        normalized = INLINE_BREAK_RE.sub("\n", normalized)
    elif tool == "codex":
        normalized = CODEX_INLINE_BREAK_RE.sub("\n", normalized)
    return [" ".join(line.split()).strip() for line in normalized.splitlines() if line.strip()]


def _extract_action(line: str) -> dict[str, str] | None:
    for kind, pattern, field in ACTION_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        value = _normalize_action_value(kind, match.group(1).strip())
        action = {"kind": kind, "text": line}
        if value:
            action[field] = value
        return action
    return None


def _load_payload_meta(event: EventRow) -> dict[str, Any] | None:
    raw = event["payload_meta_json"]
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _normalize_action_value(kind: str, value: str) -> str:
    if kind == "search":
        url_match = URL_RE.search(value)
        if url_match:
            return url_match.group(0)
        value = re.split(r"\s+[•·]\s+|\s{2,}", value, maxsplit=1)[0].strip()
        return value
    if kind == "command":
        return re.split(r"\s+[•·]\s+", value, maxsplit=1)[0].strip()
    return value
