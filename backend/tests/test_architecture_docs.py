"""Keeps the ADR index (0000-README.md) and the ADR files consistent."""
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.Trait("Task", "T101")]

ADR_DIR = Path(__file__).resolve().parents[2] / 'Architecture' / 'decisions'
ROW_RE = re.compile(r'^\| \[\d{4}\]\(([^)]+)\) \| [^|]+ \| ([^|]+) \|')


def _file_status(path: Path) -> str:
    """First non-empty line after '## Status', reduced to its leading word.

    Several ADRs append a note after the status word ("Proposed (records the
    baseline 1.7.1)"); the index row carries the bare word.
    """
    lines = path.read_text(encoding='utf-8').splitlines()
    start = lines.index('## Status') + 1
    first = next(line.strip() for line in lines[start:] if line.strip())
    return re.match(r'[A-Za-z]+', first).group(0)


def test_adr_index_status_matches_each_adr_file():
    rows = []
    for line in (ADR_DIR / '0000-README.md').read_text(encoding='utf-8').splitlines():
        m = ROW_RE.match(line)
        if m:
            rows.append((m.group(1), m.group(2).strip()))
    assert rows, 'no ADR rows found in the index'
    mismatches = [
        (name, status, _file_status(ADR_DIR / name))
        for name, status in rows
        if _file_status(ADR_DIR / name) != status
    ]
    assert mismatches == []


def test_adr_18_has_no_stray_tokens():
    text = (ADR_DIR / '0018-transactional-outbox.md').read_text(encoding='utf-8')
    assert 'GWIS' not in text
    assert '## Decision\n' in text


# --- all ADRs: structure and stray text (T101) -------------------------------------------------------------------

REQUIRED_SECTIONS = ('## Status', '## Context', '## Decision', '## Consequences')
ALLOWED_SECTIONS = set(REQUIRED_SECTIONS) | {'## Considered options', '## Related', '## Risks'}


def _adr_files() -> list[Path]:
    files = sorted(p for p in ADR_DIR.glob('[0-9][0-9][0-9][0-9]-*.md') if not p.name.startswith('0000-'))
    assert files, 'no ADR files found'
    return files


@pytest.mark.parametrize('path', _adr_files(), ids=lambda p: p.name)
def test_adr_has_required_sections_without_glued_text(path):
    headings = [line.rstrip() for line in path.read_text(encoding='utf-8').splitlines() if line.startswith('## ')]
    missing = [h for h in REQUIRED_SECTIONS if h not in headings]
    unknown = [h for h in headings if h not in ALLOWED_SECTIONS]
    assert missing == [], f'{path.name}: missing section(s) {missing}'
    assert unknown == [], f'{path.name}: unknown or corrupted heading(s) {unknown}'


@pytest.mark.parametrize('path', _adr_files(), ids=lambda p: p.name)
def test_adr_has_no_stray_tokens(path):
    assert 'GWIS' not in path.read_text(encoding='utf-8'), f'{path.name}: stray token "GWIS"'
