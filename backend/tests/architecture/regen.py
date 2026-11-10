"""Allowlist tooling for importlinter.toml.

    python backend/tests/architecture/regen.py --print-violations   # what the contracts find with empty ignore lists
    python backend/tests/architecture/regen.py --remove-stale       # delete allowlist lines that no longer match

Run from the repo root with the project venv. Nothing here adds a line to the allowlist: printing is read-only and the
only write is a deletion. A justified new entry is a deliberate, reviewed edit of the TOML and of the ratchet test.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOML = Path(__file__).with_name('importlinter.toml')

_LINE = re.compile(r'^\s*"([^"]+ -> [^"]+)"\s*,?')


def _edges(node, out: set[tuple[str, str]]) -> None:
    """Collect every (importer, imported) pair found anywhere in a contract check's metadata."""
    if isinstance(node, dict):
        if 'importer' in node and 'imported' in node:
            out.add((node['importer'], node['imported']))
        for value in node.values():
            _edges(value, out)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _edges(value, out)


def violations(config: Path = TOML) -> dict[str, list[tuple[str, str]]]:
    """Direct import edges that break each contract when its ignore_imports is empty, keyed by contract id."""
    sys.path.insert(0, str(REPO))
    import importlinter.cli  # noqa: F401  (configures importlinter's settings as a side effect)
    from importlinter.application import use_cases

    options = use_cases.read_user_options(config_filename=str(config))
    for contract in options.contracts_options:
        contract['ignore_imports'] = []
    use_cases._register_contract_types(options)   # no public hook for this; lint_imports() does the same
    report = use_cases.create_report(options, cache_dir=None)   # None = no cache
    found: dict[str, list[tuple[str, str]]] = {}
    for contract, check in report.get_contracts_and_checks():
        edges: set[tuple[str, str]] = set()
        _edges(check.metadata, edges)
        found[contract.name] = sorted(edges)
    return found


def _step_comment(importer: str, imported: str) -> str:
    from backend.tests.architecture.module_map import step_of
    return f'# until step {step_of(importer, imported)}'


def print_violations(config: Path = TOML) -> int:
    for contract_id, edges in violations(config).items():
        print(f'[{contract_id}] {len(edges)}')
        for importer, imported in edges:
            print(f'    "{importer} -> {imported}",  {_step_comment(importer, imported)}')
    return 0


def remove_stale(config: Path = TOML) -> int:
    """Delete ignore_imports lines whose edge no longer exists; returns 0 and prints what it removed."""
    live = {cid: {f'{a} -> {b}' for a, b in edges} for cid, edges in violations(config).items()}
    kept: list[str] = []
    removed: list[str] = []
    current_id = None
    in_block = False
    for line in config.read_text(encoding='utf-8').splitlines(keepends=True):
        m = re.match(r'^name\s*=\s*"([^"]+)"', line)
        if m:
            current_id = m.group(1)
        if line.strip().startswith('ignore_imports') and line.rstrip().endswith('['):
            in_block = True
        elif in_block and line.strip() == ']':
            in_block = False
        elif in_block:
            edge = _LINE.match(line)
            if edge and edge.group(1) not in live.get(current_id, set()):
                removed.append(f'[{current_id}] {edge.group(1)}')
                continue
        kept.append(line)
    if removed:
        config.write_text(''.join(kept), encoding='utf-8')
    for item in removed:
        print('removed stale:', item)
    print(f'{len(removed)} stale line(s) removed')
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--print-violations', action='store_true')
    group.add_argument('--remove-stale', action='store_true')
    args = parser.parse_args(argv)
    return print_violations() if args.print_violations else remove_stale()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
