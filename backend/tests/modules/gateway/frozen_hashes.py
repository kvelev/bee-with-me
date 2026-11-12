"""Hash pin of the frame decode, the duplicate filter and the ACK of the hardware reader.

The hash is taken over normalised source TEXT, not over ``ast.dump`` (which differs between Python
versions, so a literal made on one interpreter would be red on another). ``ast`` only finds the
first and last line of a definition. The file imports nothing from ``backend``, so it works before
and after the move into ``backend/modules/gateway`` and on any interpreter.

Never edit ``FROZEN`` by hand. After a deliberate change of a pinned function (a hardware PR),
run ``python backend/tests/modules/gateway/frozen_hashes.py`` and paste the printed dictionary.
"""

from __future__ import annotations

import ast
import hashlib
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

# first existing path wins; an alias file (it contains ``sys.modules[__name__]``) is skipped
SOURCES: dict[str, tuple[str, ...]] = {
    'parser': ('backend/modules/gateway/domain/parser.py', 'backend/hardware_reader/parser.py'),
    'hid_reader': ('backend/modules/gateway/infrastructure/hid_reader.py', 'backend/hardware_reader/hid_reader.py'),
}

PINNED: tuple[str, ...] = (
    'parser.crc16',
    'parser._strip_and_verify',
    'parser._parse_bee',
    'parser._parse_repeater',
    'parser.make_confirm',
    'parser.parse_frame',
    'parser.RLCommands',
    'parser.BeeFrame',
    'parser.RepeaterFrame',
    'hid_reader._process_frame',
    'hid_reader._send_data',
    'hid_reader.run',
    'hid_reader.EVENT_TIMEOUT',
    'hid_reader.HID_BUFFER_SIZE',
    'hid_reader.READ_INTERVAL',
    'hid_reader.RECONNECT_DELAY',
)

FROZEN: dict[str, str] = {
    'parser.crc16': 'f84087c268dab78c9da4f9ff2753d8fc6c46c9b014422def57b6cb06b56b26ef',
    'parser._strip_and_verify': 'a115331bdaa463d7a95222b50f005d7489dbe2b0c68808553379eb66c413fe4c',
    'parser._parse_bee': 'b0617f044c3027093462241dcc0494f6a01c781669cb246d02edaa2c5897107e',
    'parser._parse_repeater': '858d53d6734ddfe3195d592f501f3543c5f99432eaa9d58d8c3b71347062b654',
    'parser.make_confirm': 'cf1d8c5c3e694172e18725e1c2006660d8c5dddef7d9bea04632235405985c4f',
    'parser.parse_frame': 'cc64e56f4a5c8b8ef5f692b572935d237d03a8fe0390037ec0587419bceadd3a',
    'parser.RLCommands': '34d6245ddc86548e3b781e7f6d00421059ccdc19c5fac6787441ef13bd5b60c3',
    'parser.BeeFrame': '1b7d9316000717ca8da701fd0ed78123508cd794843d1d71dd9c6c30a0e17858',
    'parser.RepeaterFrame': '4ce30be8ba99eaeaf3668d04ecb74732a7afe8b9581037d0507d211550a202f6',
    'hid_reader._process_frame': 'ab8c8bdcb4fd217aa2ea7c8a30e9f9fd133648548ded5c0cc1e5bddf09276075',
    'hid_reader._send_data': 'ddfccd55789be7883cac17c6effe2408463a43957f38ceb93a702d55e34dcefa',
    'hid_reader.run': '80d891cad5dcf93a8af1a424a01808cd93ffaac490d0497858f66e73f14db6ed',
    'hid_reader.EVENT_TIMEOUT': '420c497c41724be35878b49bfd125fe8cf7e88e2cf513b93999b95a2b4b93bb7',
    'hid_reader.HID_BUFFER_SIZE': '0ca7f5cc8622ee6d16aea425e5e1b8608f768768be28225d9657957f51e9d3b0',
    'hid_reader.READ_INTERVAL': '0e7937a6062ed296c804e2608e5b6a5d15d43d07b3ef8f90a513df6b516c5d66',
    'hid_reader.RECONNECT_DELAY': '22088f0eaca9597645a0d9d014ff1ae32d3ebfb8a453b09137d3388e88e70774',
}

_RELATIVE_IMPORT = re.compile(r'^(\s*)from \.+')


def read_pinned_source(module: str) -> str:
    for relative in SOURCES[module]:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if 'sys.modules[__name__]' in text:
            continue
        return text
    raise FileNotFoundError('no source file for %s among %s' % (module, SOURCES[module]))


def _span(node: ast.AST) -> tuple[int, int]:
    start = node.lineno
    for decorator in getattr(node, 'decorator_list', ()):
        start = min(start, decorator.lineno)
    return start, node.end_lineno


def _find(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
    raise LookupError('%s is not defined at module level' % name)


def normalised_text(source: str, node: ast.AST) -> str:
    """The node's lines: dedented, blank and comment-only lines dropped, trailing whitespace
    stripped, the dots of a relative ``from . import`` collapsed to one. Nothing else."""
    start, end = _span(node)
    lines = textwrap.dedent('\n'.join(source.splitlines()[start - 1:end])).splitlines()
    kept = []
    for line in lines:
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        line = _RELATIVE_IMPORT.sub(r'\1from .', line)
        kept.append(line)
    return '\n'.join(kept)


def definition_hash(source: str, name: str) -> str:
    node = _find(ast.parse(source), name)
    return hashlib.sha256(normalised_text(source, node).encode('utf-8')).hexdigest()


def current_hashes() -> dict[str, str]:
    sources = {module: read_pinned_source(module) for module in SOURCES}
    result = {}
    for pinned in PINNED:
        module, name = pinned.split('.', 1)
        result[pinned] = definition_hash(sources[module], name)
    return result


if __name__ == '__main__':
    print('FROZEN: dict[str, str] = {')
    for key, value in current_hashes().items():
        print("    '%s': '%s'," % (key, value))
    print('}')
