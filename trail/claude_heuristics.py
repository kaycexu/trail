"""Shared Claude-specific parsing heuristics.

Single source of truth for regex patterns, noise detection, debug-log
handling, action-line detection, and fragment/status classification used
by both ``trail.adapters`` and ``trail.turns``.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Debug-log patterns
# ---------------------------------------------------------------------------

DEBUG_LOG_LINE_RE = re.compile(r"^\[(?:log_[^\]]+|DEBUG)\b", re.IGNORECASE)
DEBUG_LOG_BLOCK_START_RE = re.compile(
    r"^\[log_[^\]]+\]\s+response start\s*\{", re.IGNORECASE
)
DEBUG_LOG_STRUCTURED_LINE_RE = re.compile(
    r"^(?:url|status|headers|body|error|request[-_ ]id|model|usage|type|message|stop_reason)\s*:",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Fragment stems -- partial words that indicate in-progress spinner text.
# The "core" set is shared between adapters and turns; the extended set
# adds "/btw" and "thought for" which adapters also treats as noise stems.
# ---------------------------------------------------------------------------

CLAUDE_FRAGMENT_STEMS = (
    "ima", "imag", "buro", "burrow", "vib", "hash",
    "swoop", "meta", "cogit", "undulat",
)

CLAUDE_FRAGMENT_STEMS_EXTENDED = CLAUDE_FRAGMENT_STEMS + ("/btw", "thought for")

# ---------------------------------------------------------------------------
# Status words -- the set of words that appear in Claude's spinner/status
# lines (e.g. "Musing…", "Burrowing…3").
# ---------------------------------------------------------------------------

CLAUDE_STATUS_WORDS = {
    "thinking", "with", "high", "effort",
    "musing", "gallivanting", "hatching", "sketching",
    "precipitating", "pondering", "reasoning",
    "analyzing", "analysing", "planning",
    "searching", "reading", "writing", "working", "updating",
    "vibing", "metamorphosing", "hashing", "swooping",
    "imagining", "undulating", "cogitated", "burrowing",
    "plan",
}

CLAUDE_CORE_STATUS_WORDS = {
    "thinking", "musing", "gallivanting", "hatching", "sketching",
    "precipitating", "pondering", "reasoning",
    "analyzing", "analysing", "planning",
    "searching", "reading", "writing", "working", "updating",
    "vibing", "metamorphosing", "hashing", "swooping",
    "imagining", "undulating", "cogitated", "burrowing",
}

# ---------------------------------------------------------------------------
# Noise patterns used by ``is_claude_noise_line``
# ---------------------------------------------------------------------------

CLAUDE_NOISE_PATTERNS = (
    "ClaudeCodev",
    "Tips for getting",
    "Welcome back",
    "Run /init to create",
    "Recent activity",
    "/resume for more",
    "Reply with ex",
    "plan mode on",
    "shift+tabtocycle",
    "shift+tab to cycle",
    "esc to interrupt",
    "esctointerrupt",
    "ctrl+g to edit",
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
    "Opened changes in Visual Studio Code",
    "Opened changes in Cursor",
    "Opened changes in VS Code",
    "Save file to continue",
    "Claude needs your permission to use",
    "accept edits on",
    "bypass permissions on",
    "ctrl+o to expand",
    "?forshortcuts",
    "? for shortcuts",
    "?for",
    "shortcuts",
    "No recent activity",
    "Hatching\u2026",
    "Hatching",
    "Sketching\u2026",
    "Sketching",
    "Musing\u2026",
    "Musing",
    "Gallivanting\u2026",
    "Gallivanting",
    "thinking with high effort",
    "thought for",
    "Tip: Use /btw",
    "Burrowing\u2026",
    "Burrowing",
    "(thinking with high effort)",
    "chng",
    "ethi",
    "\u23ff\ufe0fDone(",
    "tooluses",
)

# ---------------------------------------------------------------------------
# Ancillary compiled patterns used by ``is_claude_noise_line``
# ---------------------------------------------------------------------------

STATUS_TOKEN_SPLIT_RE = re.compile(r"[^a-z]+")
ANSI_FRAGMENT_RE = re.compile(r"^\[[0-9;?;]+$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# ---------------------------------------------------------------------------
# Action-line prefixes shared between the basic (turns) and extended
# (adapters) variants of ``_is_claude_action_line``.
# ---------------------------------------------------------------------------

_ACTION_PREFIXES_BASE = (
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

# Extra prefixes only used by the extended (adapters) action-line check.
_ACTION_PREFIXES_EXTENDED_EXTRA = (
    "No, exit",
    "Esc to cancel",
    "Tab to amend",
    "Tip: Use /btw",
)

# ---------------------------------------------------------------------------
# Public helpers -- debug-log detection
# ---------------------------------------------------------------------------


def is_debug_log_line(line: str) -> bool:
    """Return *True* if *line* looks like a Claude debug/log line."""
    stripped = line.strip()
    if DEBUG_LOG_LINE_RE.match(stripped):
        return True
    if DEBUG_LOG_STRUCTURED_LINE_RE.match(stripped):
        return True
    return False


def start_debug_block_depth(line: str) -> int:
    """Return initial brace depth if *line* opens a debug-log block."""
    if DEBUG_LOG_BLOCK_START_RE.match(line):
        return max(1, line.count("{") - line.count("}"))
    return 0


def advance_debug_block_depth(depth: int, line: str) -> int:
    """Advance brace depth for a line inside a debug-log block."""
    next_depth = depth + line.count("{") - line.count("}")
    return max(0, next_depth)


# ---------------------------------------------------------------------------
# Public helpers -- noise / status / fragment detection
# ---------------------------------------------------------------------------


def is_claude_noise_line(line: str) -> bool:
    """Return *True* if *line* is pure Claude TUI noise (no real content)."""
    raw_line = line.strip()
    collapsed = "".join(raw_line.split())
    if is_debug_log_line(raw_line):
        return True
    if any(
        pattern in raw_line or "".join(pattern.split()) in collapsed
        for pattern in CLAUDE_NOISE_PATTERNS
    ):
        return True
    if _is_claude_status_line(raw_line):
        return True
    if is_claude_fragment_noise_line(raw_line):
        return True
    if ANSI_FRAGMENT_RE.match(raw_line):
        return True
    if raw_line.startswith("\u276f"):
        return True
    if raw_line.startswith("claude --resume "):
        return True
    if re.match(r"^\d+\.\s+(?:Yes|No)\b", raw_line):
        return True
    if "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500" in raw_line:
        return True
    if any(char in raw_line for char in "\u256d\u2570\u2502\u2590\u259b\u259c\u2598\u259d"):
        return True
    if raw_line.startswith("/"):
        return True
    if set(raw_line) <= {
        "\u00b7", "\u2722", "\u2733", "\u2736", "\u273b",
        "*", "P", "r", "e", "c", "i", "p", "t", "a", "n", "g", "\u2026",
    }:
        return True
    if set(raw_line) <= {"\u2500", "\ufffd", "-", "_", " "}:
        return True
    return False


def _is_claude_status_line(line: str) -> bool:
    """Return *True* if *line* consists entirely of Claude status tokens."""
    normalized = line.lower().replace("\u2026", " ")
    normalized = re.sub(r"\d+", " ", normalized)
    tokens = [token for token in STATUS_TOKEN_SPLIT_RE.split(normalized) if token]
    if not tokens:
        return False
    if not any(token in CLAUDE_CORE_STATUS_WORDS for token in tokens):
        return False
    return all(token in CLAUDE_STATUS_WORDS for token in tokens)


def is_claude_fragment_noise_line(line: str) -> bool:
    """Return *True* if *line* is a partial/fragment spinner line."""
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
        if "\u2026" in raw_line or len(collapsed) <= 40:
            return True
    if collapsed.startswith("main ") and ("ima" in collapsed or "imag" in collapsed):
        return True
    return False


# ---------------------------------------------------------------------------
# Public helpers -- action-line detection
# ---------------------------------------------------------------------------


def is_claude_action_line(line: str, *, extended: bool = False) -> bool:
    """Return *True* if *line* is a Claude tool-action / TUI-chrome line.

    When *extended* is True (used by the adapters post-processing path),
    additional heuristics are applied that are too aggressive for the
    initial turn-extraction pass:
      - lines starting with ``\u23ff`` (tool-result indicator)
      - shell command patterns
      - ``(thought for …)`` lines
      - ``(shift+tab)`` lines
      - ANSI color escape fragments
      - numbered menu items (``1.``, ``2.``, ``3.``)
    """
    stripped = " ".join(line.split()).strip()
    if not stripped:
        if extended:
            return True
        return False

    if extended:
        if stripped.startswith("\u23ff"):
            return True
        if re.match(
            r"^(?:ls|cat|find|rg|grep|git|python3?|bash|sed|awk|head|tail|pwd|cd|mkdir|cp|mv|rm)\b.*(?:/|~/|2>/|;\s*| -[A-Za-z])",
            stripped,
        ):
            return True

    prefixes = _ACTION_PREFIXES_BASE
    if extended:
        prefixes = _ACTION_PREFIXES_BASE + _ACTION_PREFIXES_EXTENDED_EXTRA

    if stripped.startswith(prefixes):
        return True
    if re.match(r"^Wrote\s+\d+\s+lines?\s+to\s+", stripped):
        return True
    if re.match(r"^(?:1|2|3)\.\s+(?:Yes|No)", stripped):
        return True

    if extended:
        if re.match(r"^\d+\.$", stripped):
            return True
        if re.match(r"^\(?thought\s+for\s+\d+[sm]", stripped, flags=re.IGNORECASE):
            return True
        if "(shift+tab)" in stripped or "shift+tab" in stripped.lower():
            return True
        if stripped.startswith("[38;2;") or "[38;2;" in stripped:
            return True
        if stripped.startswith("38;2;"):
            return True

    return False
