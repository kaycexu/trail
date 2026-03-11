from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import sys
import time
from typing import Optional

from trail.db import TrailDB
from trail.parser import build_turns_for_session, extract_prompt_from_session
from trail.redact import compact_text

LEGACY_ACTIVE_GRACE_SECONDS = 15.0


@dataclass
class PendingTurn:
    turn: dict
    updated_at: float


def watch_session(db: TrailDB, args) -> int:
    session = _resolve_session(db, args.session_id, tool=args.tool, repo=args.repo)
    if session is None:
        print("No matching active session found.", file=sys.stderr)
        return 1

    mode = args.mode
    print(
        f"Watching {session['id']}  tool={session['tool']}  "
        f"repo={compact_text(session['repo_root'] or session['cwd'], 80)}  mode={mode}"
    )
    print("Press Ctrl-C to stop.")

    if mode == "events":
        return _watch_events(db, session["id"], poll_interval=args.poll_interval)
    return _watch_turns(
        db,
        session["id"],
        poll_interval=args.poll_interval,
        settle_seconds=args.settle_seconds,
    )


def _resolve_session(
    db: TrailDB,
    session_id: Optional[str],
    *,
    tool: Optional[str],
    repo: Optional[str],
) -> Optional[object]:
    if session_id:
        return db.get_session(session_id)

    waiting = False
    while True:
        session = _find_live_session(db, tool=tool, repo=repo)
        if session is not None:
            return session
        if not waiting:
            waiting = True
            print("Waiting for a matching active session...")
        time.sleep(0.5)


def _find_live_session(
    db: TrailDB,
    *,
    tool: Optional[str],
    repo: Optional[str],
) -> Optional[object]:
    for session in db.list_active_sessions(limit=20, tool=tool, repo=repo):
        if _session_looks_live(session):
            return session
    return None


def _session_looks_live(session) -> bool:
    child_pid = session["child_pid"]
    if child_pid is not None:
        return _pid_is_running(int(child_pid))
    last_event_at = session["last_event_at"] or session["started_at"]
    return _is_recent_timestamp(last_event_at, within_seconds=LEGACY_ACTIVE_GRACE_SECONDS)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_recent_timestamp(ts: str | None, *, within_seconds: float) -> bool:
    if not ts:
        return False
    try:
        seen_at = datetime.fromisoformat(ts)
    except ValueError:
        return False
    now = datetime.now(seen_at.tzinfo or None)
    return seen_at >= now - timedelta(seconds=within_seconds)


def _watch_events(db: TrailDB, session_id: str, *, poll_interval: float) -> int:
    last_seq = 0
    saw_end = False

    while True:
        session = db.get_session(session_id)
        if session is None:
            print("Session disappeared.", file=sys.stderr)
            return 1

        new_events = db.get_session_events_after(session_id, last_seq)
        for event in new_events:
            last_seq = event["seq"]
            _print_event(event)
            if event["stream"] == "meta" and event["event_type"] == "end":
                saw_end = True

        if saw_end or session["ended_at"] is not None:
            if session["exit_code"] is not None:
                print(f"[end] exit={session['exit_code']}")
            return 0
        time.sleep(poll_interval)


def _watch_turns(db: TrailDB, session_id: str, *, poll_interval: float, settle_seconds: float) -> int:
    printed: dict[int, str] = {}
    pending: dict[int, PendingTurn] = {}

    while True:
        session = db.get_session(session_id)
        if session is None:
            print("Session disappeared.", file=sys.stderr)
            return 1

        turns = _extract_live_turns(db, session)
        emissions, printed, pending = _compute_turn_emissions(
            turns,
            printed=printed,
            pending=pending,
            now=time.monotonic(),
            settle_seconds=settle_seconds,
            force_flush=session["ended_at"] is not None,
        )
        for prefix, turn in emissions:
            _print_turn(turn, prefix=prefix)

        if session["ended_at"] is not None:
            if session["exit_code"] is not None:
                print(f"[end] exit={session['exit_code']}")
            return 0
        time.sleep(poll_interval)


def _compute_turn_emissions(
    turns: list[dict],
    *,
    printed: dict[int, str],
    pending: dict[int, PendingTurn],
    now: float,
    settle_seconds: float,
    force_flush: bool,
) -> tuple[list[tuple[str, dict]], dict[int, str], dict[int, PendingTurn]]:
    emissions: list[tuple[str, dict]] = []
    seen: set[int] = set()

    for turn in turns:
        seq = turn["seq"]
        seen.add(seq)
        text = turn["text_redacted"]
        previous = printed.get(seq)

        if previous == text:
            pending.pop(seq, None)
            continue

        if turn["role"] == "user":
            prefix = "~" if previous is not None else "-"
            printed[seq] = text
            pending.pop(seq, None)
            emissions.append((prefix, turn))
            continue

        existing = pending.get(seq)
        if existing is None or existing.turn["text_redacted"] != text:
            pending[seq] = PendingTurn(turn=dict(turn), updated_at=now)

    stale = [seq for seq in pending if seq not in seen]
    for seq in stale:
        pending.pop(seq, None)

    for seq in sorted(list(pending)):
        item = pending[seq]
        if not force_flush and now - item.updated_at < settle_seconds:
            continue
        previous = printed.get(seq)
        prefix = "~" if previous is not None else "-"
        printed[seq] = item.turn["text_redacted"]
        emissions.append((prefix, item.turn))
        pending.pop(seq, None)

    return emissions, printed, pending


def _extract_live_turns(db: TrailDB, session) -> list[dict]:
    return build_turns_for_session(session, db.get_session_events(session["id"]))


def _print_event(event) -> None:
    ts = event["ts"][11:19]
    if event["stream"] == "meta":
        if event["event_type"] == "start":
            print(f"[{ts}] meta  session started")
        elif event["event_type"] == "end":
            print(f"[{ts}] meta  session ended")
        return

    text = event["payload_text_redacted"] or ""
    if not text.strip():
        return

    prefix = f"[{ts}] {event['stream']:<6}"
    lines = text.rstrip("\n").splitlines()
    if not lines:
        return
    print(f"{prefix} {lines[0]}")
    indent = " " * (len(prefix) + 1)
    for line in lines[1:]:
        print(f"{indent}{line}")


def _print_turn(turn: dict, *, prefix: str) -> None:
    label = f"{prefix} [{turn['role']}]"
    lines = turn["text_redacted"].rstrip("\n").splitlines() or [""]
    print(f"{label} {lines[0]}")
    indent = " " * (len(label) + 1)
    for line in lines[1:]:
        print(f"{indent}{line}")
