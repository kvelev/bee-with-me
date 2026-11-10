"""import-linter is a dev/CI tool: it lives in requirements-dev.txt, not in the file the production image installs."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _lines(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding='utf-8').splitlines() if ln.strip() and not ln.startswith('#')]


@pytest.mark.Trait('Task', 'T304')
def test_import_linter_is_not_in_the_runtime_requirements():
    assert not [ln for ln in _lines(REPO / 'backend' / 'requirements.txt') if ln.lower().startswith('import-linter')]


@pytest.mark.Trait('Task', 'T304')
def test_dev_requirements_pin_import_linter_and_include_the_runtime_file():
    lines = _lines(REPO / 'backend' / 'requirements-dev.txt')
    assert '-r requirements.txt' in lines
    assert 'import-linter>=2.16,<3' in lines


@pytest.mark.Trait('Task', 'T304')
def test_the_production_image_installs_only_the_runtime_file():
    docker = (REPO / 'deploy' / 'docker' / 'backend.Dockerfile').read_text(encoding='utf-8')
    assert 'requirements-dev' not in docker


@pytest.mark.Trait('Task', 'T304')
def test_ci_backend_job_installs_the_dev_file():
    ci = (REPO / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    backend_job = re.search(r'^  backend:\n(.*?)^  \w[\w-]*:\n', ci, re.S | re.M).group(1)
    assert 'pip install -r backend/requirements-dev.txt' in backend_job
    cache_key = backend_job.split('cache-dependency-path:')[1].split('- name:')[0]
    assert 'backend/requirements.txt' in cache_key and 'backend/requirements-dev.txt' in cache_key
