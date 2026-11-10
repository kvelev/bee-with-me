"""T460: what wave 1 reached, pinned as lower bounds and membership.

Later steps only extend this (step 2 adds `fire` to MODULES and removes allowlist lines), so nothing here asserts an
exact list or a count. The size of the import allowlist is deliberately not asserted: the ratchet guards its growth.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
ALLOWLIST = REPO / 'backend' / 'tests' / 'architecture' / 'allowlist.json'
MAIN = REPO / 'backend' / 'main.py'


@pytest.mark.Trait("Task", "T460")
def test_settings_is_a_module_and_step_1_is_recorded():
    import backend.modules
    assert 'settings' in [m.name for m in backend.modules.MODULES]
    assert json.loads(ALLOWLIST.read_text(encoding='utf-8'))['completed_step'] >= 1


@pytest.mark.Trait("Task", "T460")
def test_main_names_no_module_router():
    # comments are cut first: a note saying "settings_router moved" must not fail the test
    code = re.sub(r'#.*', '', MAIN.read_text(encoding='utf-8'))
    assert 'settings_router' not in code
