from __future__ import annotations

import shlex
from typing import Optional

from trail.adapters import extract_prompt_from_argv, postprocess_turns
from trail.db import TrailDB
from trail.markdown import write_session_markdown
from trail.turns import extract_turns


def extract_prompt_from_session(tool: str, argv_redacted: str) -> Optional[str]:
    try:
        argv = shlex.split(argv_redacted)
    except ValueError:
        return None
    if not argv:
        return None
    return extract_prompt_from_argv(tool, argv[1:])


def build_turns_for_session(session, events) -> list[dict]:
    initial_prompt = extract_prompt_from_session(session["tool"], session["argv_redacted"])
    turns = extract_turns(
        events,
        tool=session["tool"],
        initial_user_text=initial_prompt,
        initial_user_started_at=session["started_at"],
    )
    return postprocess_turns(session["tool"], turns)


def rebuild_session_turns(db: TrailDB, session_id: str) -> list[dict]:
    session = db.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    turns = build_turns_for_session(session, db.get_session_events(session_id))
    db.replace_turns(session_id, turns)
    write_session_markdown(session, turns)
    return turns
