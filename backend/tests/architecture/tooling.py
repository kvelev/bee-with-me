"""Gate for the dev-only tool the architecture tests need (import-linter, in requirements-dev.txt).

Outside CI a missing tool skips the module with the install command; in CI (env `CI` or `GITHUB_ACTIONS`) it fails
loudly, because a silently skipped architecture gate is the same as no gate (decision of 2026-11-10, option A).
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from types import ModuleType

import pytest

INSTALL = 'pip install -r backend/requirements-dev.txt'


def in_ci(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get('CI') or env.get('GITHUB_ACTIONS'))


def require_import_linter(module_name: str = 'importlinter', environ: Mapping[str, str] | None = None) -> ModuleType:
    """The imported tool, or a skip (local) / failure (CI) that names the install command.

    Call at module level of a test file: both outcomes are allowed during collection.
    """
    if in_ci(environ):
        try:
            return importlib.import_module(module_name)
        except ImportError:
            pytest.fail(
                f'{module_name} is missing in CI: the architecture tests must not be skipped there. '
                f'The CI backend job has to install the dev requirements ({INSTALL}).',
                pytrace=False)
    return pytest.importorskip(
        module_name,
        reason=f'{module_name} is not installed: the architecture tests need it. Install it with `{INSTALL}`.',
    )
