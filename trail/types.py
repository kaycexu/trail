from __future__ import annotations

from typing import Optional, TypedDict


class SessionRow(TypedDict):
    id: str
    tool: str
    argv_redacted: str
    cwd: str
    repo_root: Optional[str]
    git_branch: Optional[str]
    hostname: str
    terminal_program: Optional[str]
    started_at: str
    ended_at: Optional[str]
    exit_code: Optional[int]
    raw_log_path: str
    bytes_in: int
    bytes_out: int
    child_pid: Optional[int]
    last_event_at: Optional[str]


class EventRow(TypedDict):
    id: str
    session_id: str
    seq: int
    stream: str
    event_type: str
    ts: str
    payload_text_redacted: Optional[str]
    payload_meta_json: Optional[str]


class TurnRow(TypedDict):
    id: str
    session_id: str
    seq: int
    role: str
    text_redacted: str
    started_at: str
    ended_at: str
    parser_version: str
    confidence: float
