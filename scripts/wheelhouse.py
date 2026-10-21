"""Integrity of the offline wheel folder vendor/wheels (B62).

    python scripts/wheelhouse.py write  <folder>   record the SHA-256 of every wheel in <folder>/SHA256SUMS
    python scripts/wheelhouse.py verify <folder>   exit 0 when the folder holds exactly the recorded wheels with
                                                   the recorded hashes; exit 1 otherwise (reason on stderr)

scripts/prepare-offline writes the list right after downloading; start.ps1 / start.sh install from the folder
only when it verifies, so a wheel that was changed, added or copied in from elsewhere is never installed.
Only wheels are accepted: a source archive would run its own build code during the install.
"""

import hashlib
import sys
from pathlib import Path

SUMS = 'SHA256SUMS'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def write(folder: Path) -> int:
    lines = [f'{_sha256(p)}  {p.name}' for p in sorted(folder.glob('*.whl'))]
    (folder / SUMS).write_text(''.join(line + '\n' for line in lines), encoding='utf-8', newline='\n')
    return 0


def verify(folder: Path) -> list[str]:
    """Problems found, empty when the folder is intact."""
    sums_path = folder / SUMS
    if not sums_path.is_file():
        return [f'{SUMS} is missing']
    recorded: dict[str, str] = {}
    for line in sums_path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            digest, _, name = line.partition('  ')
            recorded[name.strip()] = digest.strip()
    problems = []
    for name in sorted(recorded):
        if not name.endswith('.whl') or '/' in name or '\\' in name or name.startswith('.'):
            problems.append(f'{name!r} in {SUMS} is not a wheel file name')
    if problems:
        return problems
    present = {p.name for p in folder.iterdir() if p.is_file() and p.name != SUMS}
    for name in sorted(present - set(recorded)):
        problems.append(f'{name} is not in {SUMS}')
    for name, digest in sorted(recorded.items()):
        if name not in present:
            problems.append(f'{name} is listed but missing')
        elif _sha256(folder / name) != digest:
            problems.append(f'{name} does not match its recorded hash')
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ('write', 'verify'):
        print(__doc__, file=sys.stderr)
        return 2
    folder = Path(argv[2])
    if argv[1] == 'write':
        return write(folder)
    problems = verify(folder)
    for problem in problems:
        print(f'vendor/wheels: {problem}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
