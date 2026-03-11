from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from trail.config import config_path, load_config
from trail.paths import db_path, sessions_dir, trail_home


@dataclass
class DoctorCheck:
    name: str
    status: str
    detail: str
    fix: Optional[str] = None


def run_doctor(*, shell: str = "zsh") -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    checks.append(_check_trail_home())
    checks.append(_check_config_file())
    checks.append(_check_db_directory())
    checks.append(_check_command_on_path("trail"))
    checks.append(_check_command_on_path("claude"))
    checks.append(_check_shell_wrapper(shell))
    return checks


def format_doctor_report(checks: list[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        icon = {"ok": "OK", "warn": "WARN", "error": "ERR"}.get(check.status, "INFO")
        lines.append(f"[{icon}] {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"      fix: {check.fix}")
    return "\n".join(lines)


def _check_trail_home() -> DoctorCheck:
    home = trail_home()
    env_override = os.environ.get("TRAIL_HOME")
    detail = str(home)
    if env_override:
        detail = f"{detail} (from TRAIL_HOME)"
    if home.exists():
        return DoctorCheck("trail-home", "ok", detail)
    return DoctorCheck("trail-home", "warn", detail, fix="Run any Trail command once or create the directory manually.")


def _check_config_file() -> DoctorCheck:
    path = config_path()
    if path.exists():
        config = load_config()
        mode = config.get("watch", {}).get("mode", "turns")
        return DoctorCheck("config", "ok", f"{path} (watch.mode={mode})")
    return DoctorCheck("config", "warn", str(path), fix="Run `trail config init` to create a default config file.")


def _check_db_directory() -> DoctorCheck:
    directory = db_path().parent
    if directory.exists() and os.access(directory, os.W_OK):
        return DoctorCheck("storage", "ok", f"database dir writable: {directory}")
    if directory.exists():
        return DoctorCheck(
            "storage",
            "warn",
            f"could not verify write access to {directory}",
            fix="Run a write command like `trail config init` in your normal shell to confirm access.",
        )
    return DoctorCheck("storage", "warn", f"database dir missing: {directory}", fix="Run any Trail command once or create Trail home manually.")


def _check_command_on_path(command: str) -> DoctorCheck:
    resolved = shutil.which(command)
    if resolved:
        return DoctorCheck(f"{command}-command", "ok", resolved)
    fix = None
    if command == "trail":
        fix = "Put `bin/trail` on your PATH or run `python3 -m trail ...` from the repo root."
    elif command == "claude":
        fix = "Install Claude Code and ensure the `claude` binary is on PATH."
    return DoctorCheck(f"{command}-command", "warn", "not found on PATH", fix=fix)


def _check_shell_wrapper(shell: str) -> DoctorCheck:
    if shell != "zsh":
        return DoctorCheck("shell-wrapper", "warn", f"shell {shell} is not checked", fix="Use `trail init zsh` manually.")

    rc_path = Path.home() / ".zshrc"
    if not rc_path.exists():
        return DoctorCheck("shell-wrapper", "warn", f"{rc_path} not found", fix="Create ~/.zshrc and add `trail init zsh` output.")

    try:
        content = rc_path.read_text(encoding="utf-8")
    except OSError:
        return DoctorCheck("shell-wrapper", "warn", f"could not read {rc_path}", fix="Open ~/.zshrc and add Trail aliases manually.")

    if 'trail wrap claude "$@"' in content:
        return DoctorCheck("shell-wrapper", "ok", f"{rc_path} contains Trail aliases")
    return DoctorCheck("shell-wrapper", "warn", f"{rc_path} is missing Trail aliases", fix="Run `trail init zsh` and paste the output into ~/.zshrc.")
