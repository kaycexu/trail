from __future__ import annotations

import re

REDACTED = "[REDACTED]"

ANSI_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_RE = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)")

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b((?:token|password|cookie|authorization|api[_-]?key)\s*=\s*)([^\s\"']+)"),
    re.compile(r"(?i)(--(?:token|password|cookie|authorization|api-key)\s+)([^\s]+)"),
    re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9._\-+/=]+)"),
    re.compile(r"()(sk-(?:proj-)?[a-zA-Z0-9_-]{20,})"),
    re.compile(r"()(sk-ant-[a-zA-Z0-9_-]{20,})"),
    re.compile(r"()(AKIA[0-9A-Z]{16})"),
    re.compile(r"()(ghp_[a-zA-Z0-9]{36,})"),
    re.compile(r"()(gho_[a-zA-Z0-9]{36,})"),
    re.compile(r"()(ghs_[a-zA-Z0-9]{36,})"),
    re.compile(r"()(github_pat_[a-zA-Z0-9_]{20,})"),
    re.compile(r"()(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})"),
    re.compile(r"()(xoxb-[a-zA-Z0-9-]+)"),
    re.compile(r"()(xoxp-[a-zA-Z0-9-]+)"),
    re.compile(r"()(xapp-[a-zA-Z0-9-]+)"),
]


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
    return redacted


def strip_ansi(text: str) -> str:
    cleaned = ANSI_OSC_RE.sub("", text)
    return ANSI_CSI_RE.sub("", cleaned)


def clean_text_for_storage(text: str, stream: str) -> str:
    cleaned = strip_ansi(text)
    redacted = redact_sensitive_text(cleaned)

    redacted = redacted.replace("\r\n", "\n").replace("\r", "\n")

    allowed = []
    for char in redacted:
        if char in ("\n", "\t"):
            allowed.append(char)
            continue
        if stream == "stdin" and char in ("\b", "\x7f"):
            allowed.append(char)
            continue
        if char.isprintable():
            allowed.append(char)
    return "".join(allowed)


def compact_text(text: str, limit: int = 200) -> str:
    squashed = " ".join(text.split())
    if len(squashed) <= limit:
        return squashed
    return f"{squashed[:limit - 3]}..."
