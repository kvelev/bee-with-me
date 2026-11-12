"""Pin of the decode, duplicate-filter and ACK code by hash of its normalised source text.

A failure here is not a test to fix: it means a line of the hardware path changed, and that change
must be validated on a real gateway. See the hardware plan, section 2."""

import pytest

from backend.tests.modules.gateway import frozen_hashes
from backend.tests.modules.gateway.frozen_hashes import FROZEN, PINNED, current_hashes, definition_hash

HARDWARE_PLAN = 'docs/superpowers/plans/2026-11-11-vs-step3-hardware-path.md'


@pytest.mark.Trait("Task", "T601")
def test_decode_duplicate_filter_and_ack_are_unchanged():
    now = current_hashes()
    differ = sorted(name for name in set(now) | set(FROZEN) if now.get(name) != FROZEN.get(name))
    assert not differ, (
        'decode, duplicate filter or ACK changed: ' + ', '.join(differ)
        + '. A change here must be validated on a real gateway: see ' + HARDWARE_PLAN + ' section 2')


@pytest.mark.Trait("Task", "T601")
def test_normalising_ignores_an_import_level_blank_lines_and_comment_lines_and_nothing_else():
    base = (
        'def f(x):\n'
        '    from ..x import y\n'
        '    if x:\n'
        '        x = y(x)\n'
        '    return x + 1\n'
    )
    same = (
        'def f(x):\n'
        '\n'
        '    # a comment line\n'
        '    from ....x import y\n'
        '    if x:\n'
        '\n'
        '        x = y(x)   \n'
        '    return x + 1\n'
    )
    assert definition_hash(base, 'f') == definition_hash(same, 'f')
    # inside a nested block the import is indented; the dots are still normalised
    nested = 'def f(x):\n    if x:\n        from ..x import y\n    return 1\n'
    nested_deeper = 'def f(x):\n    if x:\n        from .... x import y\n    return 1\n'.replace('.... x', '....x')
    assert definition_hash(nested, 'f') == definition_hash(nested_deeper, 'f')

    operand = base.replace('x + 1', 'x + 2')
    imported = base.replace('import y', 'import z').replace('y(x)', 'z(x)')
    indentation = base.replace('    return x + 1', '        return x + 1')
    inline_comment = base.replace('x = y(x)', 'x = y(x)  # note')
    other_module = base.replace('..x', '..w')
    for changed in (operand, imported, indentation, inline_comment, other_module):
        assert definition_hash(base, 'f') != definition_hash(changed, 'f')


@pytest.mark.Trait("Task", "T601")
def test_every_pinned_name_exists_and_is_frozen():
    assert set(FROZEN) == set(PINNED)
    assert len(PINNED) == len(set(PINNED))
    now = current_hashes()  # raises when a pinned name is missing from its source
    assert set(now) == set(PINNED)
    for name in ('parser.parse_frame', 'parser.make_confirm', 'parser.RLCommands', 'parser.BeeFrame',
                 'parser.RepeaterFrame', 'hid_reader._process_frame', 'hid_reader._send_data',
                 'hid_reader.run', 'hid_reader.EVENT_TIMEOUT'):
        assert name in PINNED


@pytest.mark.Trait("Task", "T601")
def test_a_missing_name_is_an_error_not_a_silent_drop():
    with pytest.raises(LookupError):
        definition_hash('def g():\n    return 1\n', 'f')


@pytest.mark.Trait("Task", "T601")
def test_a_changed_ack_command_number_is_seen():
    source = frozen_hashes.read_pinned_source('parser')
    assert 'CONFIRM = 1' in source
    changed = source.replace('CONFIRM = 1', 'CONFIRM = 2')
    assert definition_hash(source, 'RLCommands') != definition_hash(changed, 'RLCommands')
    assert definition_hash(source, 'RLCommands') == FROZEN['parser.RLCommands']
