from __future__ import annotations

import re

REDACTED = "[REDACTED]"

ANSI_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ANSI_OSC_RE = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)")

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b((?:token|password|cookie|authorization|api[_-]?key)\s*=\s*)([^\s\"']+)"),
    re.compile(r"(?i)(--(?:token|password|cookie|authorization|api-key)\s+)([^\s]+)"),
    re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9._\-+/=]+)"),
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
    redacted = redact_sensitive_text(text)
    cleaned = strip_ansi(redacted)

    if stream != "stdin":
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    allowed = []
    for char in cleaned:
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
