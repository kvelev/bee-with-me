"""Resolve the comparison base of the allowlist ratchet: `git merge-base HEAD <ref>`."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=str(cwd or REPO), capture_output=True, text=True, timeout=60)


def resolve_base(cwd: Path | None = None) -> str | None:
    """Merge-base commit of HEAD and ARCH_BASE_REF, else upstream/develop, else origin/develop; None if none resolves.

    A shallow clone has no merge-base, so it resolves to None (the caller skips with a reason).
    """
    refs = [os.environ.get('ARCH_BASE_REF'), 'upstream/develop', 'origin/develop']
    for ref in (r for r in refs if r):
        try:
            res = _git('merge-base', 'HEAD', ref, cwd=cwd)
        except (OSError, subprocess.SubprocessError):
            return None
        sha = res.stdout.strip()
        if res.returncode == 0 and sha:
            return sha
    return None


def file_at_base(rel: str, cwd: Path | None = None) -> str | None:
    """Content of repo-relative `rel` at the merge-base, or None (no base, or the file did not exist there)."""
    base = resolve_base(cwd)
    if base is None:
        return None
    try:
        res = _git('show', f'{base}:{rel}', cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None
