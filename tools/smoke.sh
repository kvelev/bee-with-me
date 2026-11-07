#!/usr/bin/env bash
# Thin wrapper: runs tools/smoke.py with the project's Python and passes arguments and exit code through.
# See docs/SMOKE.md. Container engine: CONTAINER_ENGINE, else Podman, else Docker (chosen by smoke.py).
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python=python3
elif command -v python >/dev/null 2>&1; then
    python=python
else
    echo "FAIL  python  - Python 3.11+ not found (create .venv or install Python)"
    exit 2
fi

exec "$python" "$here/smoke.py" "$@"
