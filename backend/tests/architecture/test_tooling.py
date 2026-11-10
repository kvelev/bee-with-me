"""The architecture tests need import-linter (a dev tool): skip with a hint locally, fail loudly in CI."""
from pathlib import Path

import pytest

from backend.tests.architecture import tooling

MISSING = 'importlinter_is_not_installed_for_this_test'


@pytest.mark.Trait('Task', 'T305')
@pytest.mark.parametrize('env', [{}, {'CI': ''}, {'GITHUB_ACTIONS': ''}])
def test_missing_tool_skips_with_install_hint_outside_ci(env):
    with pytest.raises(pytest.skip.Exception) as info:
        tooling.require_import_linter(module_name=MISSING, environ=env)
    assert 'pip install -r backend/requirements-dev.txt' in str(info.value)


@pytest.mark.Trait('Task', 'T305')
@pytest.mark.parametrize('var', ['CI', 'GITHUB_ACTIONS'])
def test_missing_tool_fails_loudly_in_ci(var):
    with pytest.raises(pytest.fail.Exception) as info:
        tooling.require_import_linter(module_name=MISSING, environ={var: 'true'})
    assert 'pip install -r backend/requirements-dev.txt' in str(info.value)
    assert 'CI' in str(info.value)


@pytest.mark.Trait('Task', 'T305')
@pytest.mark.parametrize('env', [{}, {'CI': 'true'}])
def test_installed_tool_is_returned_in_both_modes(env):
    assert tooling.require_import_linter(module_name='json', environ=env).__name__ == 'json'


@pytest.mark.Trait('Task', 'T305')
def test_the_architecture_tests_that_need_the_tool_go_through_the_helper():
    here = Path(__file__).parent
    text = (here / 'test_import_contracts.py').read_text(encoding='utf-8')
    assert 'require_import_linter' in text and 'from importlinter' not in text
