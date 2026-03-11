from __future__ import annotations

import os
from pathlib import Path


def trail_home() -> Path:
    configured = os.environ.get("TRAIL_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".trail").resolve()


def sessions_dir() -> Path:
    return trail_home() / "sessions"


def transcripts_dir() -> Path:
    return trail_home() / "transcripts"


def transcript_path(session) -> Path:
    day = (session["started_at"] or "unknown-date")[:10]
    clock = "unknown-time"
    if session["started_at"] and len(session["started_at"]) >= 19:
        clock = session["started_at"][11:19].replace(":", "")
    filename = f"{clock}--{session['tool']}--{session['id']}.md"
    return transcripts_dir() / day / filename


def db_path() -> Path:
    return trail_home() / "trail.db"


def ensure_trail_home() -> Path:
    home = trail_home()
    home.mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    transcripts_dir().mkdir(parents=True, exist_ok=True)
    return home
