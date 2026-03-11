#!/usr/bin/env bash

set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "${SOURCE}" ]]; do
  DIR="$(cd -P "$(dirname "${SOURCE}")" >/dev/null 2>&1 && pwd)"
  TARGET="$(readlink "${SOURCE}")"
  if [[ "${TARGET}" != /* ]]; then
    SOURCE="${DIR}/${TARGET}"
  else
    SOURCE="${TARGET}"
  fi
done
ROOT="$(cd -P "$(dirname "${SOURCE}")" >/dev/null 2>&1 && pwd)"

SHELL_NAME="${SHELL##*/}"
RUN_DOCTOR=1

usage() {
  cat <<'EOF'
Usage: ./install.sh [--shell zsh] [--skip-doctor]

Installs the local `trail` launcher into ~/.local/bin, adds Claude/Codex wrappers
to your shell rc, initializes Trail config, and prints next steps.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --shell)
      if [[ $# -lt 2 ]]; then
        echo "install.sh: missing value for --shell" >&2
        exit 1
      fi
      SHELL_NAME="$2"
      shift 2
      ;;
    --skip-doctor)
      RUN_DOCTOR=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${SHELL_NAME}" != "zsh" ]]; then
  echo "install.sh currently supports zsh only." >&2
  exit 1
fi

BIN_DIR="${HOME}/.local/bin"
TRAIL_BIN="${BIN_DIR}/trail"
RC_FILE="${ZDOTDIR:-$HOME}/.zshrc"

mkdir -p "${BIN_DIR}"
chmod +x "${ROOT}/bin/trail"
ln -sfn "${ROOT}/bin/trail" "${TRAIL_BIN}"
export PATH="${BIN_DIR}:${PATH}"

mkdir -p "$(dirname "${RC_FILE}")"
touch "${RC_FILE}"

python3 - "${RC_FILE}" <<'PY'
from pathlib import Path
import sys

rc_path = Path(sys.argv[1])
text = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""


def replace_or_append(text: str, start: str, end: str, block: str) -> str:
    if start in text and end in text:
        before, remainder = text.split(start, 1)
        _, after = remainder.split(end, 1)
        text = before.rstrip() + "\n\n" + block.rstrip() + "\n" + after.lstrip("\n")
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text.strip():
            text += "\n"
        text += block.rstrip() + "\n"
    return text


path_block = """# >>> trail path >>>
export PATH="$HOME/.local/bin:$PATH"
# <<< trail path <<<"""

wrapper_block = """# >>> trail wrappers >>>
claude() { command trail wrap claude "$@"; }
# <<< trail wrappers <<<"""

text = replace_or_append(text, "# >>> trail path >>>", "# <<< trail path <<<", path_block)
text = replace_or_append(text, "# >>> trail wrappers >>>", "# <<< trail wrappers <<<", wrapper_block)

rc_path.write_text(text, encoding="utf-8")
PY

"${TRAIL_BIN}" config init >/dev/null
CONFIG_PATH="$("${TRAIL_BIN}" config path)"

if [[ "${RUN_DOCTOR}" == "1" ]]; then
  "${TRAIL_BIN}" doctor || true
fi

cat <<EOF

Trail installed.

- Launcher: ${TRAIL_BIN}
- Shell rc: ${RC_FILE}
- Config: ${CONFIG_PATH}

Next:
1. Run: source "${RC_FILE}"
2. Start Claude normally: claude
3. Read transcripts in: ~/.trail/transcripts/

EOF
