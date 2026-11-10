"""Static scan of the production SQL: which file writes into which table, and SQL outside `infrastructure/`.

Text based on purpose: the backend uses raw SQL strings (asyncpg, no ORM), so a regex over the source finds every
statement, multi-line and lower-case included, without importing the code.
"""
from __future__ import annotations

import re
from pathlib import Path

_FLAGS = re.IGNORECASE
# (verb, pattern); `\s` also matches newlines, so a statement split over lines is found
_WRITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ('INSERT', re.compile(r'\binsert\s+into\s+(\w+)', _FLAGS)),
    ('UPDATE', re.compile(r'\bupdate\s+(\w+)(?:\s+(?:as\s+)?\w+)?\s+set\b', _FLAGS)),
    ('DELETE', re.compile(r'\bdelete\s+from\s+(\w+)', _FLAGS)),
)
_CONN_CALL = re.compile(r'\b\w*(?:conn|pool)\w*\.(execute|executemany|fetch|fetchrow|fetchval)\s*\(')


def production_files(root: Path) -> list[Path]:
    """Every `.py` below `root` that is not a test, sorted."""
    return sorted(p for p in root.rglob('*.py') if 'tests' not in p.relative_to(root).parts)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def scan_writes(root: Path) -> set[tuple[str, str, str]]:
    """`(path relative to root, table, verb)` for every INSERT / UPDATE / DELETE found in production code."""
    found: set[tuple[str, str, str]] = set()
    for path in production_files(root):
        text = path.read_text(encoding='utf-8')
        for verb, pattern in _WRITE_PATTERNS:
            for match in pattern.finditer(text):
                found.add((_rel(root, path), match.group(1).lower(), verb))
    return found


def scan_sql_outside_infrastructure(root: Path) -> set[tuple[str, str]]:
    """`(path, method)` of connection calls under `modules/` that are not in an `infrastructure/` folder."""
    found: set[tuple[str, str]] = set()
    for path in production_files(root):
        parts = path.relative_to(root).parts
        if parts[0] != 'modules' or 'infrastructure' in parts[:-1]:
            continue
        for match in _CONN_CALL.finditer(path.read_text(encoding='utf-8')):
            found.add((_rel(root, path), match.group(1)))
    return found
