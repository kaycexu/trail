from __future__ import annotations

import re
from typing import Optional

from trail.redact import redact_sensitive_text
from trail.turns import extract_claude_output_chunks, is_claude_noise_line

DEBUG_LOG_LINE_RE = re.compile(r"^\[(?:log_[^\]]+|DEBUG)\b", re.IGNORECASE)
DEBUG_LOG_BLOCK_START_RE = re.compile(r"^\[log_[^\]]+\]\s+response start\s*\{", re.IGNORECASE)
DEBUG_LOG_STRUCTURED_LINE_RE = re.compile(
    r"^(?:url|status|headers|body|error|request[-_ ]id|model|usage|type|message|stop_reason)\s*:",
    re.IGNORECASE,
)
INLINE_STATUS_WORDS = (
    "Hatching",
    "Sketching",
    "Musing",
    "Gallivanting",
    "Precipitating",
    "Pondering",
    "Reasoning",
    "Analyzing",
    "Analysing",
    "Planning",
    "Searching",
    "Reading",
    "Writing",
    "Working",
    "Updating",
    "Vibing",
    "Metamorphosing",
    "Hashing",
    "Swooping",
    "Imagining",
    "Undulating",
    "Cogitated",
    "Burrowing",
)
INLINE_STATUS_PATTERN = "|".join(INLINE_STATUS_WORDS)
INLINE_BREAK_RE = re.compile(
    rf"\s+(?=(?:"
    rf"⎿|Plugin updated:|Tip:|Fetch\(|Read\(|Write\(|Edit\(|Search\(|Grep\(|Glob\(|Bash\(|"
    rf"Create file|Do you want to|Yes, allow|Wrote\s+\d+|Received\s*\d|"
    rf"Fetching(?:…|\.\.\.)?|Pasting text(?:…|\.\.\.)?|esctointerrupt|esc to interrupt|"
    rf"(?:ls|cat|find|rg|grep|git|python3?|bash|sed|awk|head|tail|pwd|cd|mkdir|cp|mv|rm)\s+[/~.-]|"
    rf"(?:[✢✳✶✻·*]+\s*)?(?:{INLINE_STATUS_PATTERN})(?:\s+with\s+high\s+effort)?(?:…|\.\.\.)?(?:\d+)?|"
    rf"\(?thought\s+for\s+\d+[smh]"
    rf"))"
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
COMMAND_NOISE_RE = re.compile(
    r"(?:^|[\s;])(?:ls|cat|find|rg|grep|git|python3?|bash|sed|awk|head|tail|pwd|cd|mkdir|cp|mv|rm)\b|"
    r"/Users/|2>/dev/null",
    re.IGNORECASE,
)
LEADING_ANSI_PROMPT_RE = re.compile(r"^(?:\[?(?:\d{1,3};){2,}\d{1,3}m)?❯\s*", re.IGNORECASE)
LEADING_STATUS_SEGMENT_RE = re.compile(
    rf"^(?:main\s+)?(?:[✢✳✶✻·*]+\s*)?"
    rf"(?:{INLINE_STATUS_PATTERN})(?:\s+with\s+high\s+effort)?(?:…|\.\.\.)?(?:\d+)?\s*",
    re.IGNORECASE,
)
LEADING_ACTION_SEGMENT_RE = re.compile(
    r"^(?:(?:Fetch|Read|Write|Edit|Search|Grep|Glob|Bash)\([^)]*\)|"
    r"Create file\b[^\u4e00-\u9fff]*|"
    r"Do you want to\b[^\u4e00-\u9fff]*|"
    r"Yes, allow all edits[^\u4e00-\u9fff]*|"
    r"Wrote\s+\d+\s+lines?\s+to\s+\S+|"
    r"Received\s*[\d.]+(?:KB|MB|B)?(?:\s*\(\d+\s*OK\))?|"
    r"Fetching(?:…|\.\.\.)?|"
    r"Pasting text(?:…|\.\.\.)?|"
    r"Restart to apply\b[^\u4e00-\u9fff]*|"
    r"Plugin updated:[^\u4e00-\u9fff]*)\s*",
    re.IGNORECASE,
)
LEADING_PROGRESS_SEGMENT_RE = re.compile(
    r"^(?:\(?thought\s+for\s+\d+(?:\.\d+)?[smh]\)?|"
    r"esctointerrupt|esc to interrupt|\?for shortcuts|\?forshortcuts)\s*",
    re.IGNORECASE,
)
TRAILING_PROGRESS_FRAGMENT_RE = re.compile(
    r"\s+(?:esctointerrupt|esctointerrup|esc to interrupt)\b.*$",
    re.IGNORECASE,
)
LEADING_TIP_SEGMENT_RE = re.compile(
    r"^(?:⎿\s*)?Tip:\s+Use\s+/btw\b.*?(?:(?=[\u4e00-\u9fff])|$)",
    re.IGNORECASE,
)
INLINE_NOISE_STEMS = ("ima", "imag", "buro", "burrow", "vib", "hash", "swoop", "meta", "cogit", "undulat", "/btw", "thought for")
INLINE_NOISE_FRAGMENTS = (
    "Plugin updated:",
    "Restart to apply",
    "Tip: Create skills",
    "Create skills by adding .md files",
    "tointerrupt",
    "Vibing",
    "Metamorphosing",
    "Hatching",
    "Sketching",
    "Musing",
    "Gallivanting",
    "thinking with high effort",
    "superpowers",
    "Imagining",
    "Undulating",
    "Cogitated",
    "Swooping",
    "Hashing",
    "Burrowing",
    "thought for",
    "Tip: Use /btw",
    "Fetch(",
    "Fetching",
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
    "Wrote",
    "Received",
    "Pasting text",
    "esctointerrupt",
    "esc to interrupt",
)


def extract_prompt_from_argv(tool: str, args: list[str]) -> Optional[str]:
    if tool == "claude":
        return _extract_claude_prompt(args)
    return None


def postprocess_turns(tool: str, turns: list[dict]) -> list[dict]:
    if tool == "claude":
        return _postprocess_claude_turns(turns)
    return _resequence(turns)


def should_capture_submitted_input_only(tool: str) -> bool:
    return tool == "claude"


def filter_output_for_storage(tool: str, payload: str, last_user_text: Optional[str]) -> Optional[str]:
    if tool != "claude":
        return payload if payload.strip() else None

    chunks = extract_claude_output_chunks(payload, last_user_text)
    if not chunks:
        return None
    return "\n".join(chunks).strip() or None


def _extract_claude_prompt(args: list[str]) -> Optional[str]:
    if "-p" not in args and "--print" not in args:
        return None
    for token in reversed(args):
        if token in {"-p", "--print"}:
            break
        if token.startswith("-"):
            continue
        return redact_sensitive_text(token.strip()) or None
    return None


def _resequence(turns: list[dict]) -> list[dict]:
    for index, turn in enumerate(turns, start=1):
        turn["seq"] = index
    return turns


def _postprocess_claude_turns(turns: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    saw_noise_prompt = False

    for turn in turns:
        text = turn["text_redacted"].strip()
        role = turn["role"]

        if not text:
            continue

        if role == "assistant":
            text = _clean_claude_assistant_text(text)
            if not text:
                continue
            turn["text_redacted"] = text

        if role == "assistant" and _is_claude_assistant_noise(text):
            saw_noise_prompt = True
            continue

        if role == "user" and text in {"1", "2"} and saw_noise_prompt:
            continue
        if role == "user" and text in {"/exit", "/help", "/clear"}:
            continue

        filtered.append(turn)

    return _resequence(filtered)


def _is_claude_assistant_noise(text: str) -> bool:
    raw_text = text.strip()
    collapsed = "".join(raw_text.split())
    if is_claude_noise_line(raw_text):
        return True
    patterns = (
        "WARNING:ClaudeCode",
        "Bypass Permissions mode",
        "Opened changes in Visual Studio Code",
        "Opened changes in Cursor",
        "Opened changes in VS Code",
        "Save file to continue",
        "Claude needs your permission to use",
        "https://code.claude.com/docs/en/security",
        "❯ 1. No, exit",
        "2. Yes, I accept",
        "Press Ctrl-C again to exit",
        "No, exit✔",
        "Enter to confirm",
        "Enterto confirm",
        "Resume this session with:",
        "Claude in Chrome requires a claude.ai subscription",
        "MCP servers failed",
        "MCP servers need auth",
        "MCP server needs auth",
        "Hatching…",
        "Sketching…",
        "Musing…",
        "Gallivanting…",
        "thinking with high effort",
        "thought for",
        "Tip: Use /btw",
        "Burrowing…",
        "Burrowing",
        "chng",
        "ethi",
        "?for",
        "shortcuts",
    )
    return any(pattern in raw_text or "".join(pattern.split()) in collapsed for pattern in patterns)


def _clean_claude_assistant_text(text: str) -> str:
    normalized = INLINE_BREAK_RE.sub("\n", text.replace("\r", "\n"))
    cleaned_lines: list[str] = []
    debug_block_depth = 0
    for raw_line in normalized.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if debug_block_depth:
            debug_block_depth = _advance_debug_block_depth(debug_block_depth, line)
            continue
        if _is_debug_log_line(line):
            debug_block_depth = _start_debug_block_depth(line)
            continue
        line = _strip_inline_noise_segments(line)
        if not line:
            continue
        if any(fragment in line for fragment in INLINE_NOISE_FRAGMENTS):
            if _contains_cjk(line):
                line = _strip_noise_prefix_before_cjk(line)
            else:
                continue
        line = _strip_inline_noise_segments(line)
        if not line:
            continue
        line = _strip_noise_prefix_before_cjk(line)
        line = TRAILING_PROGRESS_FRAGMENT_RE.sub("", line).strip()
        line = re.sub(r"^(?:[✢✳✶✻·*]+\s*)+", "", line).strip()
        if not line:
            continue
        if _is_claude_action_line(line):
            continue
        if _is_claude_fragment_line(line):
            continue
        if is_claude_noise_line(line):
            continue
        if cleaned_lines and cleaned_lines[-1] == line:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _is_debug_log_line(line: str) -> bool:
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


def _strip_inline_noise_segments(line: str) -> str:
    cleaned = line.strip()
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = LEADING_ANSI_PROMPT_RE.sub("", cleaned).strip()
        cleaned = LEADING_STATUS_SEGMENT_RE.sub("", cleaned).strip()
        cleaned = LEADING_ACTION_SEGMENT_RE.sub("", cleaned).strip()
        cleaned = LEADING_PROGRESS_SEGMENT_RE.sub("", cleaned).strip()
        cleaned = LEADING_TIP_SEGMENT_RE.sub("", cleaned).strip()
        cleaned = cleaned.lstrip("⎿").strip()
        cleaned = re.sub(r"^(?:[✢✳✶✻·*]+\s*)+", "", cleaned).strip()
    return cleaned


def _strip_noise_prefix_before_cjk(line: str) -> str:
    match = CJK_RE.search(line)
    if not match:
        return line
    prefix = line[:match.start()]
    if _looks_like_inline_noise(prefix):
        return line[match.start():].strip()
    return line


def _contains_cjk(text: str) -> bool:
    return CJK_RE.search(text) is not None


def _looks_like_inline_noise(text: str) -> bool:
    collapsed = " ".join(text.split()).strip().lower()
    if not collapsed:
        return False
    if COMMAND_NOISE_RE.search(text):
        return True
    if any(fragment.lower() in collapsed for fragment in INLINE_NOISE_FRAGMENTS):
        return True
    if any(stem in collapsed for stem in INLINE_NOISE_STEMS):
        return True
    words = re.findall(r"[a-z]+", collapsed)
    if words and len(words) <= 6 and len("".join(words)) <= 24:
        return True
    return False


def _is_claude_action_line(line: str) -> bool:
    stripped = " ".join(line.split()).strip()
    if not stripped:
        return True
    if stripped.startswith("⎿"):
        return True
    if re.match(
        r"^(?:ls|cat|find|rg|grep|git|python3?|bash|sed|awk|head|tail|pwd|cd|mkdir|cp|mv|rm)\b.*(?:/|~/|2>/|;\s*| -[A-Za-z])",
        stripped,
    ):
        return True
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
        "No, exit",
        "Esc to cancel",
        "Tab to amend",
        "Received",
        "Fetching",
        "Wrote ",
        "Tip: Use /btw",
    )
    if stripped.startswith(prefixes):
        return True
    if re.match(r"^Wrote\s+\d+\s+lines\s+to\s+", stripped):
        return True
    if re.match(r"^\(?thought\s+for\s+\d+[sm]", stripped, flags=re.IGNORECASE):
        return True
    if re.match(r"^(?:1|2|3)\.\s+(?:Yes|No)", stripped):
        return True
    if re.match(r"^\d+\.$", stripped):
        return True
    if "(shift+tab)" in stripped or "shift+tab" in stripped.lower():
        return True
    if stripped.startswith("[38;2;") or "[38;2;" in stripped:
        return True
    if stripped.startswith("38;2;"):
        return True
    return False


def _is_claude_fragment_line(line: str) -> bool:
    stripped = " ".join(line.split()).strip()
    if not stripped or _contains_cjk(stripped):
        return False
    lowered = stripped.lower()
    if lowered == "main":
        return True
    if "/btw" in lowered:
        return True
    if re.search(r"thought\s+for\s+\d+[sm]", lowered):
        return True
    if "thinking with high efort" in lowered or "thinking with high effort" in lowered:
        return True
    if any(stem in lowered for stem in INLINE_NOISE_STEMS):
        if "…" in stripped or len(lowered) <= 40:
            return True
    if lowered.startswith("main ") and ("ima" in lowered or "imag" in lowered):
        return True
    return False
