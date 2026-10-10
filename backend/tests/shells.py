"""Which bash the `[sh]` script tests run (B22).

On Windows, `shutil.which('bash')` from PowerShell/cmd finds C:\\Windows\\system32\\bash.EXE, the WSL
launcher: it cannot see C:/ paths and re-quotes `-c` arguments, so every `[sh]` case fails. The
tests need Git Bash. Order: BWM_TEST_BASH; a PATH bash that is not under System32/WindowsApps;
Git Bash next to git.exe (`<git root>\\bin\\bash.exe`, then `usr\\bin\\bash.exe`);
%ProgramFiles%\\Git\\bin\\bash.exe. None when nothing suitable exists (the `[sh]` cases then skip).
On Linux: `shutil.which('bash')`.
"""

import os
import shutil
from pathlib import Path, PureWindowsPath

_BAD_DIRS = ('system32', 'sysnative', 'windowsapps')
SKIP_REASON = 'no Git Bash / bash'


def _is_launcher(path: str) -> bool:
    # PureWindowsPath: split on backslashes even when the tests run on Linux/macOS (CI)
    parts = [p.lower() for p in PureWindowsPath(path).parts]
    return any(bad in parts for bad in _BAD_DIRS)


def _git_bash_near(git: str) -> str | None:
    git_path = Path(git).resolve()
    # cmd\git.exe, bin\git.exe -> parents[1]; mingw64\bin\git.exe -> parents[2]
    for root in git_path.parents[1:3]:
        for rel in (('bin', 'bash.exe'), ('usr', 'bin', 'bash.exe')):
            cand = root.joinpath(*rel)
            if cand.is_file() and not _is_launcher(str(cand)):
                return str(cand)
    return None


def find_bash(*, windows: bool | None = None) -> str | None:
    override = os.environ.get('BWM_TEST_BASH')
    if override:
        return override
    if windows is None:
        windows = os.name == 'nt'
    found = shutil.which('bash')
    if not windows:
        return found
    if found and not _is_launcher(found):
        return found
    git = shutil.which('git')
    if git:
        near = _git_bash_near(git)
        if near:
            return near
    program_files = os.environ.get('ProgramFiles')
    if program_files:
        cand = Path(program_files) / 'Git' / 'bin' / 'bash.exe'
        if cand.is_file():
            return str(cand)
    return None


BASH = find_bash()
