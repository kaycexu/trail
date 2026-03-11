from __future__ import annotations

from datetime import datetime

from trail.paths import transcript_path
from trail.redact import compact_text

TRANSCRIPT_SCHEMA_VERSION = "trail_session/v1"
TRANSCRIPT_PARSER_REVISION = 2


def write_session_markdown(session, turns, *, parser_revision: int = TRANSCRIPT_PARSER_REVISION) -> str:
    path = transcript_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_revision = _read_parser_revision(path)
    if existing_revision is not None and existing_revision > parser_revision:
        return str(path)
    path.write_text(render_session_markdown(session, turns, parser_revision=parser_revision), encoding="utf-8")
    return str(path)


def render_session_markdown(session, turns, *, parser_revision: int = TRANSCRIPT_PARSER_REVISION) -> str:
    synced_at = _now_iso()
    status = "completed" if session["ended_at"] else "active"
    session_date = _session_date(session["started_at"])
    session_week = _session_week(session["started_at"])
    lines: list[str] = []
    lines.append("---")
    lines.append('kind: "trail_session"')
    lines.append(f'schema_version: "{TRANSCRIPT_SCHEMA_VERSION}"')
    lines.append(f"parser_revision: {parser_revision}")
    lines.append(f"session_id: {_yaml_string(session['id'])}")
    lines.append(f"tool: {_yaml_string(session['tool'])}")
    lines.append(f"status: {_yaml_string(status)}")
    lines.append(f"date: {_yaml_string(session_date)}")
    lines.append(f"week: {_yaml_string(session_week)}")
    lines.append(f"started_at: {_yaml_string(session['started_at'])}")
    lines.append(f"ended_at: {_yaml_string(session['ended_at'])}")
    lines.append(f"last_synced_at: {_yaml_string(synced_at)}")
    lines.append(f"duration: {_format_session_duration(session['started_at'], session['ended_at'])}")
    lines.append(f"exit_code: {session['exit_code'] if session['exit_code'] is not None else ''}")
    lines.append(f"turn_count: {len(turns)}")
    lines.append(f"repo: {_yaml_string(session['repo_root'])}")
    lines.append(f"cwd: {_yaml_string(session['cwd'])}")
    lines.append(f"branch: {_yaml_string(session['git_branch'])}")
    lines.append(f"raw_log_path: {_yaml_string(session['raw_log_path'])}")
    preview = _session_preview(turns)
    lines.append(f"preview: {_yaml_string(preview)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Trail Session {session['id']}")
    lines.append("")
    lines.append(f"- Tool: {session['tool']}")
    lines.append(f"- Started: {session['started_at']}")
    lines.append(f"- Ended: {session['ended_at'] or '-'}")
    lines.append(f"- Duration: {_format_session_duration(session['started_at'], session['ended_at'])}")
    lines.append(f"- Exit: {session['exit_code'] if session['exit_code'] is not None else '-'}")
    lines.append(f"- Turns: {len(turns)}")
    lines.append(f"- Repo: {session['repo_root'] or '-'}")
    lines.append(f"- CWD: {session['cwd']}")
    lines.append(f"- Branch: {session['git_branch'] or '-'}")
    lines.append(f"- Raw Log: {session['raw_log_path']}")

    if preview:
        lines.append(f"- Preview: {preview}")

    lines.append("")
    lines.append("## Transcript")
    lines.append("")

    if not turns:
        lines.append("No transcript turns extracted yet.")
        lines.append("")
        return "\n".join(lines)

    for turn in turns:
        label = _format_turn_label(turn["role"], session["tool"])
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- Started: {_format_turn_time(turn['started_at'])}")
        lines.append(f"- Ended: {_format_turn_time(turn['ended_at'])}")
        lines.append("")
        text = turn["text_redacted"].rstrip("\n")
        if text:
            lines.append(text)
        else:
            lines.append("_Empty_")
        lines.append("")

    return "\n".join(lines)


def _format_turn_label(role: str, tool: str) -> str:
    if role == "user":
        return "You"
    if tool == "claude":
        return "Claude"
    return role.capitalize()


def _format_turn_time(ts: str) -> str:
    return ts


def _session_preview(turns) -> str:
    if not turns:
        return ""
    for turn in turns:
        text = compact_text(turn["text_redacted"], 120)
        if text:
            return text
    return ""


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


def _session_date(ts: str | None) -> str:
    if not ts:
        return ""
    return ts[:10]


def _session_week(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return ""
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _yaml_string(text: str | None) -> str:
    import json

    return json.dumps(text or "", ensure_ascii=False)


def _read_parser_revision(path) -> int | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = __import__("re").search(r"^parser_revision:\s*(\d+)\s*$", text, flags=__import__("re").MULTILINE)
    if not match:
        return None
    return int(match.group(1))
