from __future__ import annotations

import codecs
import json
import os
import pty
import select
import shlex
import signal
import socket
import struct
import sys
import termios
import time
import tty
import uuid
from dataclasses import dataclass
import fcntl
from pathlib import Path
from typing import Optional

from trail.adapters import (
    should_capture_submitted_input_only,
)
from trail.config import get_config_value, load_config
from trail.db import TrailDB, now_iso
from trail.line_buffer import EditableLineBuffer
from trail.parser import rebuild_session_turns
from trail.paths import sessions_dir
from trail.redact import clean_text_for_storage, redact_sensitive_text


@dataclass
class SessionContext:
    session_id: str
    tool: str
    argv: list[str]
    cwd: str
    repo_root: Optional[str]
    git_branch: Optional[str]
    hostname: str
    terminal_program: Optional[str]
    started_at: str
    raw_log_path: str


def _git_value(cwd: str, args: list[str]) -> Optional[str]:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _build_context(tool: str, argv: list[str]) -> SessionContext:
    cwd = os.getcwd()
    session_id = str(uuid.uuid4())
    repo_root = _git_value(cwd, ["rev-parse", "--show-toplevel"])
    git_branch = _git_value(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    hostname = socket.gethostname()
    terminal_program = os.environ.get("TERM_PROGRAM") or os.environ.get("TERM")
    started_at = now_iso()
    raw_log_path = str((sessions_dir() / f"{session_id}.jsonl").resolve())
    return SessionContext(
        session_id=session_id,
        tool=tool,
        argv=argv,
        cwd=cwd,
        repo_root=repo_root,
        git_branch=git_branch,
        hostname=hostname,
        terminal_program=terminal_program,
        started_at=started_at,
        raw_log_path=raw_log_path,
    )


class SessionLogger:
    def __init__(self, db: TrailDB, context: SessionContext) -> None:
        self.db = db
        self.context = context
        self.seq = 0
        self.path = Path(context.raw_log_path)
        self.handle = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        self.handle.close()

    def log_event(self, *, stream: str, event_type: str, payload_text: Optional[str] = None,
                  payload_meta: Optional[dict] = None, ts: Optional[str] = None) -> None:
        event_ts = ts or now_iso()
        self.seq += 1
        entry = {
            "session_id": self.context.session_id,
            "seq": self.seq,
            "stream": stream,
            "event_type": event_type,
            "ts": event_ts,
            "payload_text_redacted": payload_text,
            "payload_meta": payload_meta,
        }
        self.handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.handle.flush()
        self.db.add_event(
            session_id=self.context.session_id,
            seq=self.seq,
            stream=stream,
            event_type=event_type,
            ts=event_ts,
            payload_text_redacted=payload_text,
            payload_meta=payload_meta,
        )


def _get_tty_winsize(fd: int) -> Optional[tuple[int, int]]:
    try:
        data = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
        rows, cols, _, _ = struct.unpack("HHHH", data)
        return rows, cols
    except Exception:
        return None


def _set_pty_winsize(fd: int, rows: int, cols: int) -> None:
    size = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
    except Exception:
        pass


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def run_wrapped(db: TrailDB, tool: str, tool_args: list[str]) -> int:
    config = load_config()
    context = _build_context(tool, [tool, *tool_args])
    argv_redacted = redact_sensitive_text(shlex.join(context.argv))
    submitted_input_only = bool(
        get_config_value(config, f"capture.submitted_input_only.{context.tool}", should_capture_submitted_input_only(context.tool))
    )
    markdown_sync_interval = float(get_config_value(config, "markdown.sync_interval_seconds", 2.0))
    db.create_session(
        session_id=context.session_id,
        tool=context.tool,
        argv_redacted=argv_redacted,
        cwd=context.cwd,
        repo_root=context.repo_root,
        git_branch=context.git_branch,
        hostname=context.hostname,
        terminal_program=context.terminal_program,
        started_at=context.started_at,
        raw_log_path=context.raw_log_path,
    )

    logger = SessionLogger(db, context)
    logger.log_event(
        stream="meta",
        event_type="start",
        payload_meta={"tool": tool, "argv_redacted": argv_redacted},
        ts=context.started_at,
    )

    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    interactive = os.isatty(stdin_fd) and os.isatty(stdout_fd)
    original_tty_state = None

    pid, master_fd = pty.fork()
    if pid == 0:
        try:
            os.execvp(tool, [tool, *tool_args])
        except FileNotFoundError:
            os.write(2, f"trail: command not found: {tool}\n".encode())
            os._exit(127)
    db.set_session_process(context.session_id, child_pid=pid)

    bytes_in = 0
    bytes_out = 0
    exit_code = 1
    waited = False
    stdin_open = True
    resize_pending = False
    input_decoder = codecs.getincrementaldecoder("utf-8")("replace")
    line_buffer = EditableLineBuffer()
    previous_sigwinch = None
    previous_sigint = None
    previous_sigterm = None
    terminate_requested = False
    transcript_dirty = False
    last_transcript_sync = 0.0

    def on_sigwinch(_signum, _frame) -> None:
        nonlocal resize_pending
        resize_pending = True

    def on_terminate(signum, _frame) -> None:
        nonlocal terminate_requested
        terminate_requested = True
        try:
            os.kill(pid, signum)
        except OSError:
            pass

    def sync_transcript(*, force: bool = False) -> None:
        nonlocal transcript_dirty, last_transcript_sync
        now = time.monotonic()
        if not force and not transcript_dirty:
            return
        if not force and markdown_sync_interval > 0 and now - last_transcript_sync < markdown_sync_interval:
            return
        rebuild_session_turns(db, context.session_id)
        transcript_dirty = False
        last_transcript_sync = now

    try:
        sync_transcript(force=True)
        if interactive:
            original_tty_state = termios.tcgetattr(stdin_fd)
            tty.setraw(stdin_fd)
            size = _get_tty_winsize(stdin_fd)
            if size:
                _set_pty_winsize(master_fd, size[0], size[1])
            previous_sigwinch = signal.signal(signal.SIGWINCH, on_sigwinch)
        previous_sigint = signal.signal(signal.SIGINT, on_terminate)
        previous_sigterm = signal.signal(signal.SIGTERM, on_terminate)

        while True:
            if terminate_requested:
                done_pid, status = os.waitpid(pid, os.WNOHANG)
                if done_pid == pid:
                    waited = True
                    exit_code = os.waitstatus_to_exitcode(status)
                    break
            if resize_pending and interactive:
                resize_pending = False
                size = _get_tty_winsize(stdin_fd)
                if size:
                    _set_pty_winsize(master_fd, size[0], size[1])
                    logger.log_event(
                        stream="meta",
                        event_type="resize",
                        payload_meta={"rows": size[0], "cols": size[1]},
                    )

            read_fds = [master_fd]
            if stdin_open:
                read_fds.append(stdin_fd)

            ready, _, _ = select.select(read_fds, [], [], 0.1)
            if stdin_fd in ready and stdin_open:
                data = os.read(stdin_fd, 4096)
                if data:
                    _write_all(master_fd, data)
                    bytes_in += len(data)
                    if submitted_input_only:
                        decoded = input_decoder.decode(data)
                        if decoded:
                            submissions = line_buffer.feed(decoded)
                            for submitted in submissions:
                                stored_text = redact_sensitive_text(submitted)
                                logger.log_event(
                                    stream="stdin",
                                    event_type="text",
                                    payload_text=f"{stored_text}\n",
                                )
                                transcript_dirty = True
                    else:
                        cleaned = clean_text_for_storage(data.decode("utf-8", errors="replace"), "stdin")
                        if cleaned:
                            logger.log_event(stream="stdin", event_type="text", payload_text=cleaned)
                            transcript_dirty = True
                else:
                    stdin_open = False

            if master_fd in ready:
                try:
                    output = os.read(master_fd, 4096)
                except OSError:
                    output = b""
                if output:
                    _write_all(stdout_fd, output)
                    bytes_out += len(output)
                    cleaned = clean_text_for_storage(output.decode("utf-8", errors="replace"), "stdout")
                    if cleaned and cleaned.strip():
                        logger.log_event(
                            stream="stdout",
                            event_type="text",
                            payload_text=cleaned,
                        )
                        transcript_dirty = True
                else:
                    _, status = os.waitpid(pid, 0)
                    waited = True
                    exit_code = os.waitstatus_to_exitcode(status)
                    break

            done_pid, status = os.waitpid(pid, os.WNOHANG)
            if done_pid == pid:
                waited = True
                exit_code = os.waitstatus_to_exitcode(status)
                if master_fd not in ready:
                    break
            sync_transcript(force=False)
    finally:
        if not waited:
            _, status = os.waitpid(pid, 0)
            exit_code = os.waitstatus_to_exitcode(status)
        if interactive and original_tty_state is not None:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, original_tty_state)
        if previous_sigwinch is not None:
            signal.signal(signal.SIGWINCH, previous_sigwinch)
        if previous_sigint is not None:
            signal.signal(signal.SIGINT, previous_sigint)
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        os.close(master_fd)
        ended_at = now_iso()
        logger.log_event(
            stream="meta",
            event_type="end",
            payload_meta={"exit_code": exit_code},
            ts=ended_at,
        )
        db.finish_session(
            context.session_id,
            ended_at=ended_at,
            exit_code=exit_code,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
        )
        transcript_dirty = True
        sync_transcript(force=True)
        logger.close()
    return exit_code
