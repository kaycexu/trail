from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from trail.config import (
    config_path,
    get_config_value,
    init_config,
    load_config,
    parse_config_value,
    save_config,
    set_config_value,
    unset_config_value,
)
from trail.db import TrailDB
from trail.doctor import format_doctor_report, run_doctor
from trail.paths import transcript_path
from trail.parser import rebuild_session_turns
from trail.pty_runner import run_wrapped
from trail.redact import compact_text
from trail.watch import watch_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trail")
    subparsers = parser.add_subparsers(dest="command", required=True)

    wrap_parser = subparsers.add_parser("wrap", help="Wrap a supported AI CLI in a PTY session.")
    wrap_parser.add_argument("tool")

    subparsers.add_parser("codex", help="Shortcut for `trail wrap codex`.")

    subparsers.add_parser("claude", help="Shortcut for `trail wrap claude`.")

    sessions_parser = subparsers.add_parser("sessions", help="List recorded sessions.")
    sessions_parser.add_argument("--limit", type=int, default=20)
    sessions_parser.add_argument("--tool")
    sessions_parser.add_argument("--repo")

    search_parser = subparsers.add_parser("search", help="Search extracted turns.")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--role", choices=["user", "assistant", "all"], default="all")
    search_parser.add_argument("--tool")
    search_parser.add_argument("--repo")
    search_parser.add_argument("--since")

    show_parser = subparsers.add_parser("show", help="Show one recorded session.")
    show_parser.add_argument("session_id")
    show_parser.add_argument("--raw", action="store_true", help="Also print raw session events.")
    show_parser.add_argument("--raw-limit", type=int, help="Only print the last N raw events.")

    watch_parser = subparsers.add_parser("watch", help="Watch a live session.")
    watch_parser.add_argument("session_id", nargs="?")
    watch_parser.add_argument("--tool")
    watch_parser.add_argument("--repo")
    watch_parser.add_argument("--mode", choices=["events", "turns"])
    watch_parser.add_argument("--poll-interval", type=float)
    watch_parser.add_argument("--settle-seconds", type=float)

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild parsed turns for one session.")
    rebuild_parser.add_argument("session_id")

    reindex_parser = subparsers.add_parser("reindex", help="Rebuild parsed turns for multiple sessions.")
    reindex_parser.add_argument("--tool")
    reindex_parser.add_argument("--repo")

    day_parser = subparsers.add_parser("day", help="Summarize one day's sessions.")
    day_parser.add_argument("--date", help="YYYY-MM-DD, defaults to today")

    init_parser = subparsers.add_parser("init", help="Print shell wrapper functions.")
    init_parser.add_argument("shell", nargs="?", default="zsh")

    doctor_parser = subparsers.add_parser("doctor", help="Check local installation and runtime setup.")
    doctor_parser.add_argument("--shell", default="zsh")

    config_parser = subparsers.add_parser("config", help="Manage Trail config.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show", help="Print the merged config.")
    config_init = config_subparsers.add_parser("init", help="Create a default config file.")
    config_init.add_argument("--force", action="store_true")
    config_set = config_subparsers.add_parser("set", help="Set a config value.")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_unset = config_subparsers.add_parser("unset", help="Unset a config value.")
    config_unset.add_argument("key")
    config_subparsers.add_parser("path", help="Print the config path.")
    return parser


def parse_argv(argv: list[str] | None = None) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)

    if args.command in {"wrap", "codex", "claude"}:
        args.args = extra
        return parser, args

    if extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    return parser, args


def print_init(shell: str) -> int:
    if shell != "zsh":
        print(f"Unsupported shell for now: {shell}", file=sys.stderr)
        return 1
    print(
        """# Add these lines to your ~/.zshrc
codex() { command trail wrap codex "$@"; }
claude() { command trail wrap claude "$@"; }
"""
    )
    return 0


def cmd_doctor(args) -> int:
    checks = run_doctor(shell=args.shell)
    print(format_doctor_report(checks))
    if any(check.status == "error" for check in checks):
        return 1
    return 0


def cmd_config(args) -> int:
    if args.config_command == "path":
        print(config_path())
        return 0

    if args.config_command == "init":
        path = init_config(force=args.force)
        print(path)
        return 0

    config = load_config()

    if args.config_command == "show":
        print(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.config_command == "set":
        updated = set_config_value(config, args.key, parse_config_value(args.value))
        save_config(updated)
        print(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.config_command == "unset":
        updated = unset_config_value(config, args.key)
        save_config(updated)
        print(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    return 1


def cmd_sessions(db: TrailDB, args) -> int:
    rows = db.list_sessions(limit=args.limit, tool=args.tool, repo=args.repo)
    if not rows:
        print("No sessions recorded yet.")
        return 0

    for row in rows:
        repo = row["repo_root"] or row["cwd"]
        exit_code = "-" if row["exit_code"] is None else row["exit_code"]
        print(
            f"{row['id'][:8]}  {row['started_at']}  {row['tool']:<8}  "
            f"exit={exit_code:<3}  repo={compact_text(repo, 80)}"
        )
    return 0


def cmd_show(db: TrailDB, args) -> int:
    session = db.get_session(args.session_id)
    if session is None:
        print(f"Session not found: {args.session_id}", file=sys.stderr)
        return 1

    turns = db.get_session_turns(session["id"])
    duration = _format_session_duration(session["started_at"], session["ended_at"])
    preview = _session_preview(turns)
    print(f"Session  {session['id']}")
    print(
        f"Tool     {session['tool']}    "
        f"Exit {session['exit_code'] if session['exit_code'] is not None else '-'}    "
        f"Turns {len(turns)}    "
        f"Duration {duration}"
    )
    print(f"Start    {session['started_at']}")
    print(f"End      {session['ended_at'] or '-'}")
    print(f"CWD      {session['cwd']}")
    print(f"Repo     {session['repo_root'] or '-'}")
    print(f"Branch   {session['git_branch'] or '-'}")
    print(f"Log      {session['raw_log_path']}")
    print(f"Markdown {transcript_path(session)}")
    print(f"Bytes    in={session['bytes_in']} out={session['bytes_out']}")
    if preview:
        print(f"Preview  {preview}")
    print()

    if not turns:
        print("Transcript")
        print("No turns extracted yet. Run `trail rebuild <session_id>` to rebuild this session.")
        if args.raw:
            print()
            _print_raw_events(db, session["id"], limit=args.raw_limit)
        return 0

    print("Transcript")
    for turn in turns:
        label = _format_turn_label(turn["role"], session["tool"])
        ts = _format_turn_time(turn["started_at"])
        print(f"[{ts}] {label}")
        _print_turn_body(turn["text_redacted"])
        print()
    if args.raw:
        _print_raw_events(db, session["id"], limit=args.raw_limit)
    return 0


def cmd_search(db: TrailDB, args) -> int:
    rows = db.search_turns(
        args.query,
        limit=args.limit,
        role=args.role,
        tool=args.tool,
        repo=args.repo,
        since=args.since,
    )
    if not rows:
        print("No matching turns found.")
        return 0

    for row in rows:
        repo = row["repo_root"] or row["cwd"]
        text = compact_text(row["text_redacted"], 200)
        print(
            f"{row['started_at']}  {row['tool']:<8}  {row['role']:<9}  "
            f"{compact_text(repo, 60)}"
        )
        print(f"  {text}")
    return 0


def cmd_day(db: TrailDB, args) -> int:
    date_prefix = args.date or datetime.now().astimezone().date().isoformat()
    summary = db.day_summary(date_prefix)
    print(f"Trail day summary · {summary['date']}")
    print(f"Sessions: {summary['total_sessions']}")

    if summary["tools"]:
        print("Tools:")
        for tool, count in summary["tools"].items():
            print(f"- {tool}: {count}")

    if summary["repos"]:
        print("Top repos:")
        for repo, count in summary["repos"]:
            print(f"- {compact_text(repo, 100)}: {count}")

    if summary["recent_turns"]:
        print("Recent turns:")
        for row in summary["recent_turns"][:5]:
            print(f"- [{row['role']}] {compact_text(row['text_redacted'], 140)}")
    return 0


def cmd_rebuild(db: TrailDB, args) -> int:
    session = db.get_session(args.session_id)
    if session is None:
        print(f"Session not found: {args.session_id}", file=sys.stderr)
        return 1

    turns = rebuild_session_turns(db, args.session_id)
    print(f"Rebuilt {args.session_id}  turns={len(turns)}  tool={session['tool']}")
    return 0


def cmd_reindex(db: TrailDB, args) -> int:
    sessions = db.iter_sessions(tool=args.tool, repo=args.repo)
    if not sessions:
        print("No sessions matched.")
        return 0

    rebuilt = 0
    total_turns = 0
    for session in sessions:
        turns = rebuild_session_turns(db, session["id"])
        rebuilt += 1
        total_turns += len(turns)

    print(f"Reindexed {rebuilt} sessions  turns={total_turns}")
    return 0


def _format_turn_label(role: str, tool: str) -> str:
    if role == "user":
        return "You"
    if tool == "claude":
        return "Claude"
    if tool == "codex":
        return "Codex"
    return role.capitalize()


def _format_turn_time(ts: str) -> str:
    if "T" in ts and len(ts) >= 19:
        return ts[11:19]
    return ts


def _print_turn_body(text: str) -> None:
    lines = text.rstrip("\n").splitlines() or [""]
    for line in lines:
        print(f"  {line}")


def _print_raw_events(db: TrailDB, session_id: str, *, limit: int | None = None) -> None:
    events = db.get_session_events(session_id)
    if limit is not None and limit > 0:
        events = events[-limit:]
    print("Raw Events")
    for event in events:
        ts = _format_turn_time(event["ts"])
        if event["stream"] == "meta":
            meta = event["payload_meta_json"] or ""
            print(f"[{ts}] meta/{event['event_type']} {meta}")
            continue
        text = event["payload_text_redacted"] or ""
        lines = text.rstrip("\n").splitlines() or [""]
        prefix = f"[{ts}] {event['stream']}/{event['event_type']}"
        print(f"{prefix} {lines[0]}")
        indent = " " * (len(prefix) + 1)
        for line in lines[1:]:
            print(f"{indent}{line}")


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


def main(argv: list[str] | None = None) -> int:
    parser, args = parse_argv(argv)
    config = load_config()

    if args.command == "init":
        return print_init(args.shell)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "config":
        return cmd_config(args)

    if args.command == "watch":
        args.mode = args.mode or get_config_value(config, "watch.mode", "turns")
        args.poll_interval = (
            args.poll_interval
            if args.poll_interval is not None
            else float(get_config_value(config, "watch.poll_interval", 0.5))
        )
        args.settle_seconds = (
            args.settle_seconds
            if args.settle_seconds is not None
            else float(get_config_value(config, "watch.settle_seconds", 1.0))
        )

    with TrailDB() as db:
        if args.command == "wrap":
            return run_wrapped(db, args.tool, args.args)
        if args.command == "codex":
            return run_wrapped(db, "codex", args.args)
        if args.command == "claude":
            return run_wrapped(db, "claude", args.args)
        if args.command == "sessions":
            return cmd_sessions(db, args)
        if args.command == "show":
            return cmd_show(db, args)
        if args.command == "watch":
            return watch_session(db, args)
        if args.command == "search":
            return cmd_search(db, args)
        if args.command == "day":
            return cmd_day(db, args)
        if args.command == "rebuild":
            return cmd_rebuild(db, args)
        if args.command == "reindex":
            return cmd_reindex(db, args)
    return 0
