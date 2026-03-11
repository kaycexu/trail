from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trail.types import SessionRow


def trail_home() -> Path:
    configured = os.environ.get("TRAIL_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".trail").resolve()


def sessions_dir() -> Path:
    return trail_home() / "sessions"


def transcripts_dir() -> Path:
    return trail_home() / "transcripts"


def _session_artifact_stem(session: SessionRow) -> tuple[Path, str]:
    day = (session["started_at"] or "unknown-date")[:10]
    clock = "unknown-time"
    if session["started_at"] and len(session["started_at"]) >= 19:
        clock = session["started_at"][11:19].replace(":", "")
    stem = f"{clock}--{session['tool']}--{session['id']}"
    return transcripts_dir() / day, stem


def transcript_path(session: SessionRow) -> Path:
    parent, stem = _session_artifact_stem(session)
    return parent / f"{stem}.md"


def metadata_path(session: SessionRow) -> Path:
    parent, stem = _session_artifact_stem(session)
    return parent / f"{stem}.metadata.json"


def db_path() -> Path:
    return trail_home() / "trail.db"


def ensure_trail_home() -> Path:
    home = trail_home()
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    sd = sessions_dir()
    sd.mkdir(parents=True, exist_ok=True)
    sd.chmod(0o700)
    td = transcripts_dir()
    td.mkdir(parents=True, exist_ok=True)
    td.chmod(0o700)
    return home
