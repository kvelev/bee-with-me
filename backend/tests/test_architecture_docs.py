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
# Files in Architecture/decisions/ that are not ADRs. Anything else must be named NNNN-<slug>.md.
NON_ADR_FILES = ('0000-README.md',)
ADR_NAME_RE = re.compile(r'^\d{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$')
# "GWIS" glued to a letter is the corruption ("DecisionGWIS"); "EFFIS/GWIS" or "GWIS" alone is legitimate.
GLUED_GWIS_RE = re.compile(r'[A-Za-z]GWIS')


def _headings(text: str) -> list[str]:
    """Level-2 headings outside fenced code blocks (``` or ~~~), trailing whitespace removed."""
    result, fence = [], None
    for line in text.splitlines():
        marker = line.lstrip()[:3]
        if marker in ('```', '~~~'):
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is None and line.startswith('## '):
            result.append(line.rstrip())
    return result


def _misnamed(names: list[str]) -> list[str]:
    return sorted(n for n in names if n not in NON_ADR_FILES and not ADR_NAME_RE.match(n))


def _adr_files() -> list[Path]:
    files = sorted(p for p in ADR_DIR.glob('*.md') if p.name not in NON_ADR_FILES)
    assert files, 'no ADR files found'
    return files


def test_adr_directory_has_only_adr_named_markdown_files():
    names = [p.name for p in ADR_DIR.iterdir() if p.is_file()]
    assert _misnamed(names) == [], 'rename to NNNN-slug.md or list in NON_ADR_FILES'


def test_misnamed_file_detector_catches_odd_names():
    names = ['0000-README.md', '0021-tile-server.md', '21-foo.md', '0022_bar.md', 'notes.md', '0023-Upper.md']
    assert _misnamed(names) == ['0022_bar.md', '0023-Upper.md', '21-foo.md', 'notes.md']


@pytest.mark.parametrize('path', _adr_files(), ids=lambda p: p.name)
def test_adr_has_required_sections_without_glued_text(path):
    headings = _headings(path.read_text(encoding='utf-8'))
    missing = [h for h in REQUIRED_SECTIONS if h not in headings]
    unknown = [h for h in headings if h not in ALLOWED_SECTIONS]
    assert missing == [], f'{path.name}: missing section(s) {missing}'
    assert unknown == [], f'{path.name}: unknown or corrupted heading(s) {unknown}'


def test_headings_ignore_lines_inside_code_fences():
    lines = ['## Status', '', '```sql', '## not a heading', '```', '', '~~~', '## nor this', '~~~', '', '## Decision  ']
    assert _headings(chr(10).join(lines)) == ['## Status', '## Decision']


@pytest.mark.parametrize('path', _adr_files(), ids=lambda p: p.name)
def test_adr_has_no_stray_tokens(path):
    match = GLUED_GWIS_RE.search(path.read_text(encoding='utf-8'))
    assert match is None, f'{path.name}: stray token glued to text: {match.group(0)!r}'


def test_gwis_token_rule_flags_only_the_glued_form():
    assert GLUED_GWIS_RE.search('## DecisionGWIS')
    assert not GLUED_GWIS_RE.search('EFFIS/GWIS feeds, and GWIS alone, (GWIS)')
