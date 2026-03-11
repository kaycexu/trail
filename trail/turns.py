from __future__ import annotations

import re

from trail.redact import compact_text

PARSER_VERSION = "v0-heuristic"
CLAUDE_PARSER_VERSION = "v0-claude"
RESIDUAL_STYLE_RE = re.compile(r"\[[0-9;?]*[A-Za-z]")
ANSI_FRAGMENT_RE = re.compile(r"^\[[0-9;?;]+$")
STATUS_TOKEN_SPLIT_RE = re.compile(r"[^a-z]+")
DEBUG_LOG_LINE_RE = re.compile(r"^\[(?:log_[^\]]+|DEBUG)\b", re.IGNORECASE)
DEBUG_LOG_BLOCK_START_RE = re.compile(r"^\[log_[^\]]+\]\s+response start\s*\{", re.IGNORECASE)
DEBUG_LOG_STRUCTURED_LINE_RE = re.compile(
    r"^(?:url|status|headers|body|error|request[-_ ]id|model|usage|type|message|stop_reason)\s*:",
    re.IGNORECASE,
)
CLAUDE_FRAGMENT_STEMS = ("ima", "imag", "buro", "burrow", "vib", "hash", "swoop", "meta", "cogit", "undulat")

CLAUDE_STATUS_WORDS = {
    "thinking",
    "with",
    "high",
    "effort",
    "musing",
    "gallivanting",
    "hatching",
    "sketching",
    "precipitating",
    "pondering",
    "reasoning",
    "analyzing",
    "analysing",
    "planning",
    "searching",
    "reading",
    "writing",
    "working",
    "updating",
    "vibing",
    "metamorphosing",
    "hashing",
    "swooping",
    "imagining",
    "undulating",
    "cogitated",
    "burrowing",
    "plan",
}
CLAUDE_CORE_STATUS_WORDS = {
    "thinking",
    "musing",
    "gallivanting",
    "hatching",
    "sketching",
    "precipitating",
    "pondering",
    "reasoning",
    "analyzing",
    "analysing",
    "planning",
    "searching",
    "reading",
    "writing",
    "working",
    "updating",
    "vibing",
    "metamorphosing",
    "hashing",
    "swooping",
    "imagining",
    "undulating",
    "cogitated",
    "burrowing",
}


def _normalize_output(text: str) -> str:
    normalized = text.replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.splitlines()]
    collapsed = "\n".join(line for line in lines if line)
    return collapsed.strip()


def _collapse_inline_text(text: str) -> str:
    return "".join(text.split()).lower()


def extract_turns(
    events,
    tool: str | None = None,
    initial_user_text: str | None = None,
    initial_user_started_at: str | None = None,
) -> list[dict]:
    if tool == "claude":
        return _extract_claude_turns(
            events,
            initial_user_text=initial_user_text,
            initial_user_started_at=initial_user_started_at,
        )
    return _extract_generic_turns(
        events,
        initial_user_text=initial_user_text,
        initial_user_started_at=initial_user_started_at,
    )


def _extract_generic_turns(
    events,
    initial_user_text: str | None = None,
    initial_user_started_at: str | None = None,
) -> list[dict]:
    turns: list[dict] = []
    seq = 1
    pending_user = ""
    user_started_at = None
    assistant_buffer = ""
    assistant_started_at = None
    last_user_text = None

    if initial_user_text:
        text = " ".join(initial_user_text.split()).strip()
        if text:
            last_user_text = text
            turns.append(
                {
                    "seq": seq,
                    "role": "user",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": initial_user_started_at or events[0]["ts"],
                    "ended_at": initial_user_started_at or events[0]["ts"],
                    "parser_version": "v0-argv",
                    "confidence": 0.95,
                }
            )
            seq += 1

    def flush_assistant(ended_at: str) -> None:
        nonlocal seq, assistant_buffer, assistant_started_at, last_user_text
        text = _normalize_output(assistant_buffer)
        if last_user_text and text.startswith(last_user_text):
            text = text[len(last_user_text):].lstrip(" \n\r\t:>-")
        if text:
            turns.append(
                {
                    "seq": seq,
                    "role": "assistant",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": assistant_started_at or ended_at,
                    "ended_at": ended_at,
                    "parser_version": PARSER_VERSION,
                    "confidence": 0.45,
                }
            )
            seq += 1
        assistant_buffer = ""
        assistant_started_at = None

    def flush_user(ended_at: str) -> None:
        nonlocal seq, pending_user, user_started_at, last_user_text
        text = " ".join(pending_user.split()).strip()
        if text:
            last_user_text = text
            turns.append(
                {
                    "seq": seq,
                    "role": "user",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": user_started_at or ended_at,
                    "ended_at": ended_at,
                    "parser_version": PARSER_VERSION,
                    "confidence": 0.7,
                }
            )
            seq += 1
        pending_user = ""
        user_started_at = None

    for event in events:
        if event["event_type"] != "text":
            continue
        payload = event["payload_text_redacted"] or ""
        if not payload:
            continue

        if event["stream"] == "stdin":
            for char in payload:
                if char in ("\r", "\n"):
                    if assistant_buffer.strip():
                        flush_assistant(event["ts"])
                    if pending_user.strip():
                        flush_user(event["ts"])
                elif char in ("\x7f", "\b"):
                    pending_user = pending_user[:-1]
                elif char.isprintable() or char == "\t":
                    if not pending_user:
                        user_started_at = event["ts"]
                    pending_user += char
        elif event["stream"] == "stdout":
            if payload.strip():
                if assistant_started_at is None:
                    assistant_started_at = event["ts"]
                assistant_buffer += payload

    if assistant_buffer.strip():
        flush_assistant(events[-1]["ts"])
    if pending_user.strip():
        flush_user(events[-1]["ts"])
    return turns


def _extract_claude_turns(
    events,
    initial_user_text: str | None = None,
    initial_user_started_at: str | None = None,
) -> list[dict]:
    turns: list[dict] = []
    seq = 1
    pending_user = ""
    user_started_at = None
    last_user_text = None
    assistant_lines: list[str] = []
    assistant_started_at = None
    previous_assistant_lines: set[str] = set()
    previous_assistant_flat = ""
    assistant_redraw_mode = False

    if initial_user_text:
        text = " ".join(initial_user_text.split()).strip()
        if text:
            last_user_text = text
            turns.append(
                {
                    "seq": seq,
                    "role": "user",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": initial_user_started_at or events[0]["ts"],
                    "ended_at": initial_user_started_at or events[0]["ts"],
                    "parser_version": "v0-argv",
                    "confidence": 0.95,
                }
            )
            seq += 1

    def flush_user(ended_at: str) -> None:
        nonlocal seq, pending_user, user_started_at, last_user_text
        text = " ".join(pending_user.split()).strip()
        if text:
            last_user_text = text
            turns.append(
                {
                    "seq": seq,
                    "role": "user",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": user_started_at or ended_at,
                    "ended_at": ended_at,
                    "parser_version": CLAUDE_PARSER_VERSION,
                    "confidence": 0.8,
                }
            )
            seq += 1
        pending_user = ""
        user_started_at = None

    def flush_assistant(ended_at: str) -> None:
        nonlocal seq, assistant_lines, assistant_started_at
        nonlocal previous_assistant_lines, previous_assistant_flat, assistant_redraw_mode
        text = "\n".join(line for line in assistant_lines if line).strip()
        text = _normalize_output(text)
        text = re.sub(r"^[\s�─·✢✳✶✻*]+", "", text).strip()
        if text:
            turns.append(
                {
                    "seq": seq,
                    "role": "assistant",
                    "text_redacted": compact_text(text, limit=4000),
                    "started_at": assistant_started_at or ended_at,
                    "ended_at": ended_at,
                    "parser_version": CLAUDE_PARSER_VERSION,
                    "confidence": 0.6,
                }
            )
            previous_assistant_lines, previous_assistant_flat = _build_assistant_replay_cache(text)
            seq += 1
        assistant_lines = []
        assistant_started_at = None
        assistant_redraw_mode = False

    for event in events:
        if event["event_type"] != "text":
            continue
        payload = event["payload_text_redacted"] or ""
        if not payload:
            continue

        if event["stream"] == "stdin":
            for char in payload:
                if char in ("\r", "\n"):
                    if pending_user.strip():
                        if assistant_lines:
                            assistant_lines = _strip_user_echo_tail(assistant_lines, pending_user)
                            flush_assistant(event["ts"])
                        flush_user(event["ts"])
                elif char in ("\x7f", "\b"):
                    pending_user = pending_user[:-1]
                elif char.isprintable() or char == "\t":
                    if not pending_user:
                        user_started_at = event["ts"]
                    pending_user += char
            continue

        if event["stream"] != "stdout":
            continue

        if last_user_text is None:
            continue

        chunks = extract_claude_output_chunks(payload, last_user_text)
        if not chunks:
            if payload.strip():
                assistant_redraw_mode = True
            continue
        if assistant_started_at is None:
            assistant_started_at = event["ts"]
        accepted_chunk = False
        for chunk in chunks:
            if _is_replayed_assistant_chunk(
                chunk,
                previous_assistant_lines=previous_assistant_lines,
                previous_assistant_flat=previous_assistant_flat,
                current_assistant_lines=assistant_lines,
                redraw_mode=assistant_redraw_mode,
            ):
                continue
            merge_progressive_chunk(assistant_lines, chunk)
            accepted_chunk = True
        if accepted_chunk:
            assistant_redraw_mode = False

    if pending_user.strip():
        flush_user(events[-1]["ts"])
    if assistant_lines:
        flush_assistant(events[-1]["ts"])
    return turns


def extract_claude_output_chunks(payload: str, last_user_text: str | None) -> list[str]:
    chunks: list[str] = []
    normalized = payload.replace("\r", "\n")
    debug_block_depth = 0
    for raw_line in normalized.splitlines():
        raw_compact = " ".join(raw_line.split()).strip()
        if not raw_compact:
            continue

        if debug_block_depth:
            debug_block_depth = _advance_debug_block_depth(debug_block_depth, raw_compact)
            continue

        if _is_claude_debug_log_line(raw_compact):
            debug_block_depth = _start_debug_block_depth(raw_compact)
            continue

        line = RESIDUAL_STYLE_RE.sub("", raw_line)
        line = " ".join(line.split()).strip()
        if not line:
            continue

        if "⏺" in line:
            line = line.split("⏺", 1)[1].strip()
        elif "⏸" in line:
            line = line.split("⏸", 1)[0].strip()

        if not line:
            continue
        if last_user_text and _matches_prompt_echo(line, last_user_text):
            continue
        if _is_claude_action_line(line):
            continue
        if is_claude_noise_line(line):
            continue

        if not line or is_claude_noise_line(line):
            continue

        if len(line) <= 3 and line not in {"OK", "Yes", "No"}:
            continue

        chunks.append(line)
    return chunks


def merge_progressive_chunk(assistant_lines: list[str], chunk: str) -> None:
    if not chunk:
        return
    if not assistant_lines:
        assistant_lines.append(chunk)
        return

    last = assistant_lines[-1]
    if last == chunk:
        return

    last_flat = " ".join(last.split())
    chunk_flat = " ".join(chunk.split())
    if last_flat and chunk_flat.startswith(last_flat):
        assistant_lines[-1] = chunk
        return
    if chunk_flat and last_flat.startswith(chunk_flat):
        return

    assistant_lines.append(chunk)


def _build_assistant_replay_cache(text: str) -> tuple[set[str], str]:
    line_cache = {
        flat
        for flat in (_collapse_inline_text(line) for line in text.splitlines())
        if len(flat) >= 12
    }
    return line_cache, _collapse_inline_text(text)


def _strip_user_echo_tail(assistant_lines: list[str], pending_user: str) -> list[str]:
    prompt_flat = _collapse_inline_text(pending_user)
    if not prompt_flat:
        return assistant_lines

    assistant_flats = [_collapse_inline_text(line) for line in assistant_lines]
    candidate = ""
    cut_index: int | None = None
    for index in range(len(assistant_flats) - 1, -1, -1):
        flat = assistant_flats[index]
        if not flat:
            continue
        candidate = flat + candidate
        if len(candidate) > len(prompt_flat):
            break
        if prompt_flat.endswith(candidate):
            if len(candidate) >= 8:
                cut_index = index
            continue
        if candidate not in prompt_flat:
            break

    if cut_index is None:
        return assistant_lines
    return assistant_lines[:cut_index]


def _is_replayed_assistant_chunk(
    chunk: str,
    *,
    previous_assistant_lines: set[str],
    previous_assistant_flat: str,
    current_assistant_lines: list[str],
    redraw_mode: bool,
) -> bool:
    if not previous_assistant_flat:
        return False

    flat = _collapse_inline_text(chunk)
    if len(flat) < 12:
        return False
    if not redraw_mode and not current_assistant_lines:
        return False
    if flat in previous_assistant_lines:
        return True
    if len(flat) >= 32 and flat in previous_assistant_flat:
        return True
    return False


def _matches_prompt_echo(line: str, prompt: str) -> bool:
    left = "".join(line.split())
    right = "".join(prompt.split())
    return bool(right) and right in left


def _is_claude_action_line(line: str) -> bool:
    stripped = " ".join(line.split()).strip()
    if not stripped:
        return False
    prefixes = (
        "Fetch(",
        "Read(",
        "Write(",
        "Edit(",
        "Search(",
        "Grep(",
        "Glob(",
        "Bash(",
        "Create file",
        "Do you want to",
        "Yes, allow all edits",
        "Opened changes in Visual Studio Code",
        "Opened changes in Cursor",
        "Opened changes in VS Code",
        "Save file to continue",
        "Claude needs your permission to use",
        "Received",
        "Fetching",
        "Wrote ",
    )
    if stripped.startswith(prefixes):
        return True
    if re.match(r"^Wrote\s+\d+\s+lines?\s+to\s+", stripped):
        return True
    if re.match(r"^(?:1|2|3)\.\s+(?:Yes|No)", stripped):
        return True
    return False


def is_claude_noise_line(line: str) -> bool:
    raw_line = line.strip()
    collapsed = "".join(raw_line.split())
    if _is_claude_debug_log_line(raw_line):
        return True
    patterns = (
        "ClaudeCodev",
        "Tips for getting",
        "Welcome back",
        "Run /init to create",
        "Recent activity",
        "/resume for more",
        "Reply with ex",
        "plan mode on",
        "plan mode on",
        "shift+tabtocycle",
        "shift+tab to cycle",
        "esc to interrupt",
        "esctointerrupt",
        "ctrl+g to edit",
        "Checking for updates",
        "Checking for updates",
        "Claude in Chrome requires",
        "MCP servers failed",
        "MCP servers need auth",
        "MCP server needs auth",
        "/mcp",
        "Precipitating",
        "running stop hook",
        "/exit Exit the REPL",
        "Resume this session with:",
        "/data-context-extractor",
        "/interface-design:extract",
        "APIUsageBilling",
        "TapTapPteLtd",
        "Exit the REPL",
        "Press Ctrl-C again to exit",
        "Resume this session with:",
        "Opened changes in Visual Studio Code",
        "Opened changes in Cursor",
        "Opened changes in VS Code",
        "Save file to continue",
        "Claude needs your permission to use",
        "accept edits on",
        "bypass permissions on",
        "ctrl+o to expand",
        "ctrl+o to expand",
        "?forshortcuts",
        "? for shortcuts",
        "?for",
        "shortcuts",
        "No recent activity",
        "Hatching…",
        "Hatching",
        "Sketching…",
        "Sketching",
        "Musing…",
        "Musing",
        "Gallivanting…",
        "Gallivanting",
        "thinking with high effort",
        "thought for",
        "Tip: Use /btw",
        "Burrowing…",
        "Burrowing",
        "(thinking with high effort)",
        "chng",
        "ethi",
        "⎿Done(",
        "tooluses",
    )
    if any(pattern in raw_line or "".join(pattern.split()) in collapsed for pattern in patterns):
        return True
    if _is_claude_status_line(raw_line):
        return True
    if _is_claude_fragment_noise_line(raw_line):
        return True
    if ANSI_FRAGMENT_RE.match(raw_line):
        return True
    if raw_line.startswith("❯"):
        return True
    if raw_line.startswith("claude --resume "):
        return True
    if re.match(r"^\d+\.\s+(?:Yes|No)\b", raw_line):
        return True
    if "────────────────" in raw_line:
        return True
    if any(char in raw_line for char in "╭╰│▐▛▜▘▝"):
        return True
    if raw_line.startswith("/"):
        return True
    if set(raw_line) <= {"·", "✢", "✳", "✶", "✻", "*", "P", "r", "e", "c", "i", "p", "t", "a", "n", "g", "…"}:
        return True
    if set(raw_line) <= {"─", "�", "-", "_", " "}:
        return True
    return False


def _is_claude_status_line(line: str) -> bool:
    normalized = line.lower().replace("…", " ")
    normalized = re.sub(r"\d+", " ", normalized)
    tokens = [token for token in STATUS_TOKEN_SPLIT_RE.split(normalized) if token]
    if not tokens:
        return False
    if not any(token in CLAUDE_CORE_STATUS_WORDS for token in tokens):
        return False
    return all(token in CLAUDE_STATUS_WORDS for token in tokens)


def _is_claude_fragment_noise_line(line: str) -> bool:
    raw_line = line.strip()
    if not raw_line or re.search(r"[\u4e00-\u9fff]", raw_line):
        return False
    collapsed = " ".join(raw_line.split()).lower()
    if "/btw" in collapsed:
        return True
    if re.search(r"thought\s+for\s+\d+[sm]", collapsed):
        return True
    if "thinking with high efort" in collapsed or "thinking with high effort" in collapsed:
        return True
    if any(stem in collapsed for stem in CLAUDE_FRAGMENT_STEMS):
        if "…" in raw_line or len(collapsed) <= 40:
            return True
    if collapsed.startswith("main ") and ("ima" in collapsed or "imag" in collapsed):
        return True
    return False


def _is_claude_debug_log_line(line: str) -> bool:
    stripped = line.strip()
    if DEBUG_LOG_LINE_RE.match(stripped):
        return True
    if DEBUG_LOG_STRUCTURED_LINE_RE.match(stripped):
        return True
    return False


def _start_debug_block_depth(line: str) -> int:
    if DEBUG_LOG_BLOCK_START_RE.match(line):
        return max(1, line.count("{") - line.count("}"))
    return 0


def _advance_debug_block_depth(depth: int, line: str) -> int:
    next_depth = depth + line.count("{") - line.count("}")
    return max(0, next_depth)
