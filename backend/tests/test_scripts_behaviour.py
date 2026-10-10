"""B14: start.ps1 / start.sh decision logic, run for real against stubs.

Each test copies the start scripts into a temp project with stub backup scripts, stub `pip` and
`backend.db.migrate` modules and a stub container engine first on PATH (backend/tests/stubs/), and runs
the script with BWM_START_DRY_RUN=1: it stops after the migration check. Nothing touches the real
project tree, containers or database. A local listener stands in for Postgres on POSTGRES_PORT.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from backend.tests.script_env import script_env
from backend.tests.shells import SKIP_REASON, find_bash

ROOT = Path(__file__).resolve().parents[2]
STUBS = Path(__file__).resolve().parent / 'stubs'
PS_EXE = shutil.which('powershell') or shutil.which('pwsh')
BASH = find_bash()
DRY = 'DRY RUN: would start backend and frontend'

KINDS = [
    pytest.param('ps', marks=pytest.mark.skipif(PS_EXE is None or os.name != 'nt',
                                                 reason='needs Windows PowerShell')),
    pytest.param('sh', marks=pytest.mark.skipif(BASH is None, reason=SKIP_REASON)),
]


def _copy_text(src, dst, *, lf):
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding='utf-8')
    dst.write_text(text.replace('\r\n', '\n'), encoding='utf-8', newline='\n' if lf else '\r\n')


@pytest.fixture(scope='session')
def _venv(tmp_path_factory):
    """A real (pip-less) venv for start.ps1, which calls .venv\\Scripts\\python.exe by path."""
    if os.name != 'nt':
        return None
    path = tmp_path_factory.mktemp('venv') / '.venv'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(path)], check=True, timeout=300)
    return path


@pytest.fixture()
def postgres_port():
    """Something listening on a free port (IPv4 and, where possible, IPv6 loopback): 'Postgres is up'."""
    for _ in range(20):
        v4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        v4.bind(('127.0.0.1', 0))
        port = v4.getsockname()[1]
        socks = [v4]
        try:
            v6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            v6.bind(('::1', port))
            socks.append(v6)
        except OSError:
            pass
        for s in socks:
            s.listen(16)
        try:
            yield port
        finally:
            for s in socks:
                s.close()
        return


@pytest.fixture()
def project(tmp_path, _venv, postgres_port):
    proj = tmp_path / 'proj'
    for rel in ('start.ps1', 'start.sh'):
        _copy_text(ROOT / rel, proj / rel, lf=rel.endswith('.sh'))
    for src in (STUBS / 'project').rglob('*'):
        if src.is_file() and '__pycache__' not in src.parts:
            _copy_text(src, proj / src.relative_to(STUBS / 'project'), lf=not src.suffix == '.ps1')
    (proj / 'backend' / 'requirements.txt').write_text('', encoding='utf-8')
    (proj / '.env.example').write_text(f'POSTGRES_PORT={postgres_port}\nPOSTGRES_DB=stub_db\n', encoding='utf-8')
    if _venv is not None:
        shutil.copytree(_venv, proj / '.venv')
    _copy_text(STUBS / 'posix' / 'python', proj / '.venv' / 'bin' / 'python', lf=True)
    for rel in ('start.sh', 'scripts/backup.sh', '.venv/bin/python'):
        os.chmod(proj / rel, 0o755)
    return proj


def _run(kind, project, tmp_path, *, engine='podman', migrate='0', wait=None, args=(), bash_path_prepend=None, **stub):
    log = tmp_path / 'calls.log'
    log.write_text('', encoding='utf-8')
    if kind == 'sh':
        posix = tmp_path / 'posix-stubs'
        for name in ('podman', 'docker'):
            _copy_text(STUBS / 'posix' / name, posix / name, lf=True)
            os.chmod(posix / name, 0o755)
        shutil.copy(STUBS / 'engine_stub.py', tmp_path / 'engine_stub.py')
        stub_dir = posix
    else:
        stub_dir = STUBS / 'win'
    env = {k: v for k, v in script_env().items() if not k.startswith('BWM_')}
    env.update({
        'PATH': os.pathsep.join([str(stub_dir), os.environ.get('PATH', '')]),
        'CONTAINER_ENGINE': engine,
        'BWM_START_DRY_RUN': '1',
        'BWM_STUB_LOG': log.as_posix(),
        'BWM_STUB_PYTHON': Path(sys.executable).as_posix(),
        'BWM_STUB_MIGRATE_EXITS': migrate,
        # Git Bash would rewrite /mnt/... values into C:/Program Files/Git/mnt/... for the native stub
        'MSYS2_ENV_CONV_EXCL': 'BWM_STUB_',
    })
    if wait is not None:
        env['BWM_MIGRATE_WAIT_S'] = str(wait)
    env.update({f'BWM_STUB_{k.upper()}': v for k, v in stub.items()})
    if kind == 'ps':
        cmd = [PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(project / 'start.ps1'), '-NoBrowser',
               *args]
    else:
        cmd = [BASH, (project / 'start.sh').as_posix(), '--no-browser', *args]
        if bash_path_prepend:
            # Git Bash's launcher puts /mingw64/bin:/usr/bin in front of the inherited PATH, so fakes of
            # openssl/base64 only win when PATH is set inside bash, right before the script runs. The script
            # is then run by "$BASH" (the real bash.exe already running), not by BASH again: re-running the
            # launcher (Git\bin\bash.exe) would put /mingw64/bin:/usr/bin back in front of the fakes.
            cmd = [BASH, '-c', 'PATH="$(cygpath -u "$1" 2>/dev/null || printf %s "$1"):$PATH"; shift; exec "$BASH" "$@"', 'bwm', Path(bash_path_prepend).as_posix(), *cmd[1:]]
    res = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, timeout=300)
    res.calls = log.read_text(encoding='utf-8').splitlines()
    res.out = res.stdout + res.stderr
    return res


def _backups(res):
    return [c for c in res.calls if c.startswith('backup ')]


def _migrates(res):
    return [c for c in res.calls if c.startswith('migrate ')]


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_up_to_date_database_starts_without_a_backup(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='0')
    assert res.returncode == 0, res.out
    assert DRY in res.out
    assert _migrates(res) == ['migrate status']
    assert _backups(res) == []
    assert any(' compose -p bee-with-me ' in c and c.rstrip().endswith('up -d') for c in res.calls), res.calls


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_pending_migrations_back_up_before_the_start(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='10')
    assert res.returncode == 0, res.out
    backups = _backups(res)
    assert len(backups) == 1 and 'backups' in backups[0], res.calls
    assert res.calls.index('migrate status') < res.calls.index(backups[0])
    assert res.out.index('STUB BACKUP DONE') < res.out.index(DRY)


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_failing_backup_refuses_to_start(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='10', backup_fail='1')
    assert res.returncode != 0
    assert DRY not in res.out
    assert 'Backup failed - not starting' in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_database_newer_than_the_app_refuses(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='2')
    assert res.returncode != 0
    assert DRY not in res.out and _backups(res) == []
    assert 'newer than this version' in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_invalid_migration_files_refuse_at_once(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='1', wait=30)
    assert res.returncode != 0
    assert DRY not in res.out and _backups(res) == []
    assert _migrates(res) == ['migrate status']
    assert 'migration files are invalid' in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_unreachable_database_refuses_after_the_retries(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='3', wait=5)   # longer than one status call: at least one retry
    assert res.returncode != 0
    assert DRY not in res.out and _backups(res) == []
    assert len(_migrates(res)) >= 2   # retried at least once
    assert 'database not reachable?' in res.out and 'never migrated without a backup' in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.parametrize('kind', KINDS)
def test_database_coming_up_late_is_retried_then_backed_up(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='3,10', wait=30)
    assert res.returncode == 0, res.out
    assert len(_migrates(res)) == 2 and len(_backups(res)) == 1
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('kind', KINDS)
def test_old_docker_project_is_backed_up_and_stopped_before_compose_up(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=str(project / 'docker'))
    assert res.returncode == 0, res.out
    backups = _backups(res)
    flag = '-Container olddb123' if kind == 'ps' else '--container olddb123'
    assert backups and flag in backups[0], res.calls
    down = next(i for i, c in enumerate(res.calls) if ' compose -p docker -f ' in c and c.rstrip().endswith('down'))
    up = next(i for i, c in enumerate(res.calls) if ' compose -p bee-with-me ' in c and c.rstrip().endswith('up -d'))
    assert res.calls.index(backups[0]) < down < up
    assert ' -v' not in res.calls[down]
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('kind', KINDS)
def test_old_project_backup_failure_leaves_it_running(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123', backup_fail='1',
               old_workdir=str(project / 'docker'))
    assert res.returncode != 0
    assert not any(' down' in c for c in res.calls if c.startswith('engine '))
    assert not any('up -d' in c for c in res.calls)
    assert 'Backup of the old database failed' in res.out


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.Trait("Bug", "B12")
def test_old_podman_machine_volume_stops_with_restore_steps(project, tmp_path):
    # podman-machine mode: start.ps1 with podman on Windows; start.sh with podman under Git Bash/macOS
    kind = 'ps' if (os.name == 'nt' and PS_EXE) else 'sh'
    if kind == 'sh' and (BASH is None or os.name != 'nt'):
        pytest.skip('podman-machine mode needs Windows (or macOS)')
    res = _run(kind, project, tmp_path, engine='podman', migrate='0', old_db='olddb123',
               old_workdir=str(project / 'docker'), old_mount='/var/lib/containers/storage/volumes/docker_pgdata/_data')
    assert res.returncode != 0
    assert DRY not in res.out
    assert 'docker_pgdata' in res.out and 'restore.' in res.out and 'beewithme_stub.dump' in res.out
    assert any(' compose -p docker -f ' in c for c in res.calls)


@pytest.mark.Trait("Bug", "B14")
@pytest.mark.Trait("Bug", "B13")
@pytest.mark.parametrize('kind', KINDS)
def test_engine_warning_on_stderr_does_not_abort(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='0', info_warn='1')
    assert res.returncode == 0, res.out
    assert DRY in res.out


# ── B17: only an old install of THIS folder is backed up and stopped ──────────

def _old_stopped(res):
    return any(' compose -p docker -f ' in c and c.rstrip().endswith('down') for c in res.calls)


def _wsl_form(path):
    """C:/Users/x -> /mnt/c/Users/x (how podman machine records a Windows folder)."""
    p = Path(path).as_posix()
    return f'/mnt/{p[0].lower()}{p[2:]}' if len(p) > 1 and p[1] == ':' else p


def _variants(project):
    """working_dir spellings that all mean <project>/docker."""
    base = str(project / 'docker')
    out = [base, base + os.sep]
    if os.name == 'nt':
        out += [base.upper(), base.replace(os.sep, '/') + '/', _wsl_form(base)]
    return out


@pytest.mark.Trait("Bug", "B17")
@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('variant', range(5))
def test_old_container_of_this_folder_by_working_dir_is_backed_up_and_stopped(kind, variant, project, tmp_path):
    variants = _variants(project)
    if variant >= len(variants):
        pytest.skip('Windows-only path spelling')
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=variants[variant], old_mount='/somewhere/else')
    assert res.returncode == 0, res.out
    assert _backups(res) and _old_stopped(res), res.calls
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B17")
@pytest.mark.parametrize('kind', KINDS)
def test_old_container_of_this_folder_by_data_mount_is_backed_up_and_stopped(kind, project, tmp_path):
    mount = str(project / 'data' / 'pgdata')
    if os.name == 'nt':
        mount = _wsl_form(mount) + '/'
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir='/home/other/app/docker', old_mount=mount)
    assert res.returncode == 0, res.out
    assert _backups(res) and _old_stopped(res), res.calls
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B17")
@pytest.mark.parametrize('kind', KINDS)
def test_old_container_of_another_folder_is_left_alone_with_instructions(kind, project, tmp_path):
    other = tmp_path / 'other-app'
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=str(other / 'docker'), old_mount=str(other / 'data' / 'pgdata'))
    assert res.returncode != 0
    assert _backups(res) == [] and not _old_stopped(res), res.calls
    assert not any('up -d' in c for c in res.calls)
    assert DRY not in res.out
    flag = '-Container olddb123' if kind == 'ps' else '--container olddb123'
    assert flag in res.out and 'restore.' in res.out and 'another folder' in res.out, res.out


@pytest.mark.Trait("Bug", "B17")
@pytest.mark.parametrize('kind', KINDS)
def test_old_container_without_inspect_information_is_left_alone(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123')
    assert res.returncode != 0
    assert _backups(res) == [] and not _old_stopped(res), res.calls
    assert not any('up -d' in c for c in res.calls)
    assert DRY not in res.out


# ── B18: pip failures are reported (not fatal), stderr from native calls never aborts ─

@pytest.mark.Trait("Bug", "B18")
@pytest.mark.parametrize('kind', KINDS)
def test_failing_pip_install_warns_and_the_start_continues(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='0', pip_fail='1')
    assert res.returncode == 0, res.out
    assert any(c.startswith('pip ') for c in res.calls)
    assert 'pip install failed' in res.out
    assert res.out.index('pip install failed') < res.out.index(DRY)


@pytest.mark.Trait("Bug", "B18")
@pytest.mark.parametrize('kind', KINDS)
def test_migrate_status_warning_on_stderr_does_not_abort(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, migrate='10', migrate_warn='1')
    assert res.returncode == 0, res.out
    assert len(_backups(res)) == 1 and DRY in res.out


# ── B20: a trailing or doubled separator in the project path or the old working_dir still matches ─

@pytest.mark.Trait("Bug", "B20")
@pytest.mark.parametrize('kind', KINDS)
def test_project_path_with_a_trailing_separator_still_matches_the_old_container(kind, project, tmp_path):
    if kind == 'ps':
        args = ('-ProjectPath', str(project) + '\\')
    else:
        args = ('--project-path', project.as_posix() + '/')
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=str(project / 'docker'), old_mount='/somewhere/else', args=args)
    assert res.returncode == 0, res.out
    assert _backups(res) and _old_stopped(res), res.calls
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B20")
@pytest.mark.parametrize('kind', KINDS)
def test_old_working_dir_with_doubled_separators_still_matches(kind, project, tmp_path):
    doubled = str(project).replace(os.sep, os.sep * 2) + os.sep * 2 + 'docker'
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=doubled, old_mount='/somewhere/else')
    assert res.returncode == 0, res.out
    assert _backups(res) and _old_stopped(res), res.calls
    assert DRY in res.out


# ── B21: the project folder is printed without a trailing separator ───────────────────────────

@pytest.mark.Trait("Bug", "B21")
@pytest.mark.parametrize('kind', KINDS)
def test_project_folder_line_has_no_trailing_separator(kind, project, tmp_path):
    if kind == 'ps':
        args = ('-ProjectPath', str(project) + '\\\\')
    else:
        args = ('--project-path', project.as_posix() + '//')
    res = _run(kind, project, tmp_path, migrate='0', args=args)
    assert res.returncode == 0, res.out
    line = next(l for l in res.out.splitlines() if 'Using project folder:' in l)
    line = re.sub(r'\x1b\[[0-9;]*m', '', line).rstrip()   # start.sh colours its step lines
    assert not line.endswith(('\\', '/')), line
    assert line.lower().endswith(project.name.lower()), line


# ── B57: data/backups made by the user before compose up, invariant timestamps, secret key, engine guard ──

def _state(res, name):
    return [c for c in res.calls if c.startswith(f'state {name} ')]


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_data_backups_folder_exists_before_compose_up(kind, project, tmp_path):
    # rootful Docker would create data/ as root through the bind mount; the user makes it first
    res = _run(kind, project, tmp_path, migrate='0')
    assert res.returncode == 0, res.out
    assert _state(res, 'compose-up') == ['state compose-up backups_dir=1'], res.calls
    assert (project / 'data' / 'backups').is_dir()


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_old_install_backup_finds_the_backups_folder_already_made(kind, project, tmp_path):
    res = _run(kind, project, tmp_path, engine='docker', migrate='0', old_db='olddb123',
               old_workdir=str(project / 'docker'))
    assert res.returncode == 0, res.out
    assert 'backup-state dir_existed=1' in res.calls, res.calls


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_skip_containers_does_not_need_the_backups_folder_first(kind, project, tmp_path):
    flag = '-SkipContainers' if kind == 'ps' else '--skip-containers'
    res = _run(kind, project, tmp_path, args=(flag,))
    assert res.returncode == 0, res.out
    assert _state(res, 'compose-up') == []


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_data_backups_that_cannot_be_made_stops_with_a_next_step(kind, project, tmp_path):
    (project / 'data').write_text('a file where the data folder should be', encoding='utf-8')
    res = _run(kind, project, tmp_path, migrate='0')
    assert res.returncode != 0
    assert DRY not in res.out and not any('up -d' in c for c in res.calls), res.calls
    assert 'Cannot write to the backup folder' in res.out, res.out


# backup.sh / backup.ps1 themselves (real scripts, a stub database container)

def _backup_project(tmp_path):
    proj = tmp_path / 'bproj'
    for rel in ('scripts/backup.sh', 'scripts/backup.ps1'):
        _copy_text(ROOT / rel, proj / rel, lf=rel.endswith('.sh'))
    return proj


def _run_backup(kind, tmp_path, out_dir, *, culture=None, engine='podman', db='stubdb', extra_env=None):
    proj = _backup_project(tmp_path)
    log = tmp_path / 'calls.log'
    log.write_text('', encoding='utf-8')
    if kind == 'sh':
        posix = tmp_path / 'posix-stubs'
        for name in ('podman', 'docker'):
            _copy_text(STUBS / 'posix' / name, posix / name, lf=True)
            os.chmod(posix / name, 0o755)
        shutil.copy(STUBS / 'engine_stub.py', tmp_path / 'engine_stub.py')
        stub_dir = posix
    else:
        stub_dir = STUBS / 'win'
    env = script_env()
    env.update({
        'PATH': str(stub_dir) + os.pathsep + os.environ.get('PATH', ''),
        'CONTAINER_ENGINE': engine,
        'BWM_STUB_LOG': log.as_posix(),
        'BWM_STUB_PYTHON': Path(sys.executable).as_posix(),
        'MSYS2_ENV_CONV_EXCL': 'BWM_STUB_',
    })
    if db:
        env['BWM_STUB_DB'] = db
    env.update(extra_env or {})
    if kind == 'ps':
        script = proj / 'scripts' / 'backup.ps1'
        arg = f" -OutDir '{out_dir}'" if out_dir is not None else ''
        prefix = ''
        if culture:
            prefix = ("[Threading.Thread]::CurrentThread.CurrentCulture = "
                      f"[Globalization.CultureInfo]::GetCultureInfo('{culture}'); ")
        cmd = [PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
               f"{prefix}& '{script}'{arg}"]
    else:
        cmd = [BASH, (proj / 'scripts' / 'backup.sh').as_posix()] + ([Path(out_dir).as_posix()] if out_dir is not None else [])
    res = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, timeout=300)
    res.calls = log.read_text(encoding='utf-8').splitlines()
    res.out = res.stdout + res.stderr
    res.proj = proj
    return res


def _marker(out_dir):
    import json
    return json.loads((Path(out_dir) / 'last-backup.json').read_text(encoding='utf-8'))


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_backup_stub_flow_writes_a_parseable_marker(kind, tmp_path):
    from datetime import datetime
    out = tmp_path / 'out'
    res = _run_backup(kind, tmp_path, out)
    assert res.returncode == 0, res.out
    marker = _marker(out)
    assert datetime.fromisoformat(marker['created_at']).tzinfo is not None, marker
    assert (out / marker['dump']).is_file()


@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
def test_backup_sh_streams_the_dump_when_docker_cp_fails(tmp_path):
    # Docker Desktop: cp out of a container with a single-file bind mount (old installs mounted
    # schema.sql) fails with "mkdirat ...: file exists"; the old-install backup must still succeed.
    out = tmp_path / 'out'
    res = _run_backup('sh', tmp_path, out, engine='docker', extra_env={'BWM_STUB_CP_FAIL': '1'})
    assert res.returncode == 0, res.out
    assert 'streaming the dump' in res.out, res.out
    assert any(c.startswith('engine exec') and ' cat /tmp/beewithme_' in c for c in res.calls), res.calls
    assert (out / _marker(out)['dump']).read_bytes() == b'PGDMP'


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')
@pytest.mark.parametrize('culture', ['fi-FI', 'th-TH', 'ar-SA'])
def test_backup_ps1_timestamps_ignore_the_culture(culture, tmp_path):
    from datetime import datetime, timezone
    out = tmp_path / 'out'
    res = _run_backup('ps', tmp_path, out, culture=culture)
    assert res.returncode == 0, res.out
    marker = _marker(out)
    created = datetime.fromisoformat(marker['created_at'])   # fi-FI used to give 10.34.59: a ValueError
    assert abs((datetime.now(timezone.utc) - created).total_seconds()) < 600, marker
    assert re.fullmatch(r'beewithme_20\d\d-\d\d-\d\d_\d{6}_[0-9a-f]{6}\.dump', marker['dump']), marker['dump']
    assert abs(datetime.now().year - int(marker['dump'][10:14])) <= 1   # th-TH/ar-SA would give 2569 / 1448


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')
def test_backup_ps1_default_out_dir_is_data_backups_of_the_project(tmp_path):
    res = _run_backup('ps', tmp_path, None)
    assert res.returncode == 0, res.out
    assert (res.proj / 'data' / 'backups' / 'last-backup.json').is_file(), res.out


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_backup_into_a_folder_it_cannot_use_stops_before_any_engine_call(kind, tmp_path):
    out = tmp_path / 'not-a-folder'
    out.write_text('a file', encoding='utf-8')
    res = _run_backup(kind, tmp_path, out)
    assert res.returncode != 0, res.out
    assert 'Cannot write to the backup folder' in res.out, res.out
    assert not [c for c in res.calls if c.startswith('engine exec')], res.calls
    assert out.read_text(encoding='utf-8') == 'a file'


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.skipif(os.name == 'nt' or not hasattr(os, 'geteuid') or os.geteuid() == 0,
                    reason='needs POSIX permissions as non-root')
def test_backup_sh_into_a_read_only_folder_names_the_chown_fix(tmp_path):
    out = tmp_path / 'bproj' / 'data' / 'backups'   # under the project root, where the hint applies
    out.mkdir(parents=True)
    out.chmod(0o555)
    try:
        res = _run_backup('sh', tmp_path, out)
    finally:
        out.chmod(0o755)
    assert res.returncode != 0, res.out
    assert 'Cannot write to the backup folder' in res.out and 'chown' in res.out, res.out
    assert not [c for c in res.calls if c.startswith('engine exec')], res.calls


@pytest.mark.Trait("Bug", "B57")
def test_start_sh_udev_hint_is_not_world_writable():
    text = (ROOT / 'start.sh').read_text(encoding='utf-8')
    assert 'MODE="0666"' not in text
    assert 'MODE="0660"' in text and 'GROUP="plugdev"' in text and 'usermod -aG plugdev' in text


# a fresh install gets its own random secret key

EXAMPLE = 'POSTGRES_PORT={port}\nSECRET_KEY=change-me-example-key\nexport POSTGRES_DB=stub_db\nOTHER_SETTING=1\n'


def _fresh_install(kind, project, tmp_path, example):
    (project / '.env.example').write_text(example.format(port=5432), encoding='utf-8', newline='\n')
    (project / '.env').unlink(missing_ok=True)
    flag = '-SkipContainers' if kind == 'ps' else '--skip-containers'
    return _run(kind, project, tmp_path, args=(flag,))


def _secret_lines(project):
    return [l for l in (project / '.env').read_text(encoding='utf-8').splitlines() if l.upper().startswith('SECRET_KEY=')]


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_fresh_install_replaces_the_example_secret_key_with_a_random_one(kind, project, tmp_path):
    res = _fresh_install(kind, project, tmp_path, EXAMPLE)
    assert res.returncode == 0, res.out
    lines = (project / '.env').read_text(encoding='utf-8').splitlines()
    secret = [l for l in lines if l.startswith('SECRET_KEY=')]
    assert len(secret) == 1, lines
    key = secret[0].split('=', 1)[1]
    assert key != 'change-me-example-key' and len(key) >= 48 and not re.search(r'\s|["\']', key), key
    assert [l for l in lines if not l.startswith('SECRET_KEY=')] == \
        ['POSTGRES_PORT=5432', 'export POSTGRES_DB=stub_db', 'OTHER_SETTING=1']
    assert key not in res.out   # never printed
    again = _fresh_install(kind, project, tmp_path, EXAMPLE)
    assert again.returncode == 0, again.out
    assert _secret_lines(project)[0].split('=', 1)[1] != key   # random each time


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_fresh_install_adds_a_secret_key_when_the_example_has_none(kind, project, tmp_path):
    res = _fresh_install(kind, project, tmp_path, 'POSTGRES_PORT={port}\n')
    assert res.returncode == 0, res.out
    lines = _secret_lines(project)
    assert len(lines) == 1 and len(lines[0].split('=', 1)[1]) >= 48, lines


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_existing_secrets_file_is_left_alone(kind, project, tmp_path):
    (project / '.env.example').write_text(EXAMPLE.format(port=5432), encoding='utf-8')
    mine = 'POSTGRES_PORT=5432\nSECRET_KEY=mine-do-not-touch\n'
    (project / '.env').write_text(mine, encoding='utf-8', newline='\n')
    flag = '-SkipContainers' if kind == 'ps' else '--skip-containers'
    res = _run(kind, project, tmp_path, args=(flag,))
    assert res.returncode == 0, res.out
    assert (project / '.env').read_text(encoding='utf-8') == mine


# engine switch guard: data/pgdata (bind mount of the base file) must not be silently replaced by the
# Podman-machine named volume

def _machine_override_kind():
    if os.name == 'nt' and PS_EXE:
        return 'ps'
    if os.name == 'nt' and BASH:
        return 'sh'
    pytest.skip('the Podman machine override only applies on Windows (or macOS)')


@pytest.mark.Trait("Bug", "B57")
def test_existing_bind_mount_data_stops_the_podman_machine_override(project, tmp_path):
    kind = _machine_override_kind()
    pgdata = project / 'data' / 'pgdata'
    pgdata.mkdir(parents=True)
    (pgdata / 'PG_VERSION').write_text('16\n', encoding='utf-8')
    res = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert res.returncode != 0, res.out
    assert DRY not in res.out and not any('up -d' in c for c in res.calls), res.calls
    assert 'CONTAINER_ENGINE' in res.out and 'docker' in res.out and 'data' in res.out, res.out
    assert (pgdata / 'PG_VERSION').is_file()


@pytest.mark.Trait("Bug", "B57")
def test_podman_machine_override_without_old_data_still_starts(project, tmp_path):
    kind = _machine_override_kind()
    res = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert res.returncode == 0, res.out
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B57")
@pytest.mark.parametrize('kind', KINDS)
def test_docker_with_existing_bind_mount_data_starts(kind, project, tmp_path):
    pgdata = project / 'data' / 'pgdata'
    pgdata.mkdir(parents=True)
    (pgdata / 'PG_VERSION').write_text('16\n', encoding='utf-8')
    res = _run(kind, project, tmp_path, engine='docker', migrate='0')
    assert res.returncode == 0, res.out
    assert DRY in res.out


# ── B59: the engine guard explains the rename; private, atomically written secrets file; private backups folder ──

def _pgdata_with_files(project):
    pgdata = project / 'data' / 'pgdata'
    pgdata.mkdir(parents=True)
    (pgdata / 'PG_VERSION').write_text('16\n', encoding='utf-8')
    return pgdata


@pytest.mark.Trait("Bug", "B59")
def test_engine_guard_names_the_rename_and_the_restore_step(project, tmp_path):
    kind = _machine_override_kind()
    pgdata = _pgdata_with_files(project)
    res = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert res.returncode != 0, res.out
    assert not any('up -d' in c for c in res.calls), res.calls
    out = res.out.replace('\\', '/')
    assert re.search(r'data/pgdata\.docker-\d{8}', out), res.out          # the exact new folder name
    assert ('Rename-Item' if kind == 'ps' else 'mv ') in res.out, res.out    # ... and the command that does it
    assert 'restore.' + ('ps1' if kind == 'ps' else 'sh') in res.out, res.out
    assert 'never delete' not in res.out, res.out    # the old advice that led nowhere
    assert (pgdata / 'PG_VERSION').is_file()          # the guard itself still changes nothing


@pytest.mark.Trait("Bug", "B59")
def test_after_the_rename_podman_starts(project, tmp_path):
    kind = _machine_override_kind()
    pgdata = _pgdata_with_files(project)
    blocked = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert blocked.returncode != 0, blocked.out
    pgdata.rename(project / 'data' / 'pgdata.docker-20261004')
    res = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert res.returncode == 0, res.out
    assert DRY in res.out


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')
def test_failing_icacls_leaves_no_secrets_file_and_stops_with_a_message(project, tmp_path):
    (project / '.env.example').write_text(EXAMPLE.format(port=5432), encoding='utf-8', newline='\n')
    (project / '.env').unlink(missing_ok=True)
    res = _run('ps', project, tmp_path, args=('-SkipContainers',), icacls_fail='1')
    assert res.returncode != 0, res.out
    leftovers = sorted(p.name for p in project.iterdir() if p.name.startswith('.env') and p.name != '.env.example')
    assert leftovers == [], leftovers    # neither the file nor a temp copy of the key
    assert 'icacls' in res.out, res.out
    assert 'change-me-example-key' not in res.out


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')
def test_successful_fresh_install_leaves_no_temp_file(project, tmp_path):
    res = _fresh_install('ps', project, tmp_path, EXAMPLE)
    assert res.returncode == 0, res.out
    names = sorted(p.name for p in project.iterdir() if p.name.startswith('.env'))
    assert names == ['.env', '.env.example'], names


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(os.name == 'nt' or BASH is None, reason='POSIX modes need a POSIX file system')
def test_start_sh_makes_data_backups_private(project, tmp_path):
    res = _run('sh', project, tmp_path, migrate='0')
    assert res.returncode == 0, res.out
    assert (project / 'data' / 'backups').stat().st_mode & 0o777 == 0o700


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(os.name == 'nt' or BASH is None, reason='POSIX modes need a POSIX file system')
def test_start_sh_tightens_an_existing_data_backups(project, tmp_path):
    backups = project / 'data' / 'backups'
    backups.mkdir(parents=True)
    backups.chmod(0o755)
    res = _run('sh', project, tmp_path, migrate='0')
    assert res.returncode == 0, res.out
    assert backups.stat().st_mode & 0o777 == 0o700


def _fake_failing_tool(fake_dir, name):
    """A tool that logs 'fake <name>' to BWM_STUB_LOG and fails."""
    path = fake_dir / name
    path.write_text(f'#!/usr/bin/env bash\necho "fake {name}" >> "$BWM_STUB_LOG"\nexit 1\n', encoding='utf-8', newline='\n')
    path.chmod(0o755)


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
def test_start_sh_falls_back_to_urandom_when_openssl_fails(project, tmp_path):
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    _fake_failing_tool(fake, 'openssl')
    (project / '.env.example').write_text(EXAMPLE.format(port=5432), encoding='utf-8', newline='\n')
    (project / '.env').unlink(missing_ok=True)
    res = _run('sh', project, tmp_path, args=('--skip-containers',), bash_path_prepend=fake)
    assert res.returncode == 0, res.out
    assert 'fake openssl' in res.calls, res.calls    # the fake really ran: the fallback made the key
    key = _secret_lines(project)[0].split('=', 1)[1]
    assert key != 'change-me-example-key' and len(key) >= 48, key


@pytest.mark.Trait("Bug", "B59")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
def test_start_sh_stops_naming_both_attempts_when_nothing_can_make_a_key(project, tmp_path):
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    for name in ('openssl', 'base64'):
        _fake_failing_tool(fake, name)
    (project / '.env.example').write_text(EXAMPLE.format(port=5432), encoding='utf-8', newline='\n')
    (project / '.env').unlink(missing_ok=True)
    res = _run('sh', project, tmp_path, args=('--skip-containers',), bash_path_prepend=fake)
    assert res.returncode != 0, res.out
    assert 'fake openssl' in res.calls and 'fake base64' in res.calls, res.calls
    assert not (project / '.env').exists()
    assert 'openssl' in res.out and '/dev/urandom' in res.out, res.out


# ── B60: engine-guard steps use the right engine; temp secrets file cleanup ──

def _guard_kinds():
    """Both start scripts apply the Podman machine override on Windows (start.sh under Git Bash too)."""
    return [pytest.param('ps', marks=pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')),
            pytest.param('sh', marks=pytest.mark.skipif(BASH is None or os.name != 'nt', reason='Podman machine override: Windows'))]


def _guard_text(kind, project, tmp_path):
    """The guard message as one line: PowerShell hard-wraps its error text at the console width (and repeats it
    after 'FullyQualifiedErrorId'), so take the first copy and drop the line breaks before matching."""
    _pgdata_with_files(project)
    res = _run(kind, project, tmp_path, engine='podman', migrate='0')
    assert res.returncode != 0, res.out
    first = re.split(r'\nAt \S+:\d+ char:', res.out.replace('\\', '/'))[0]
    return re.sub(r'\x1b\[[0-9;]*m', '', first).replace('\n', '')


@pytest.mark.Trait("Bug", "B60")
@pytest.mark.parametrize('kind', _guard_kinds())
def test_guard_backup_step_forces_docker_and_stops_the_docker_stack(kind, project, tmp_path):
    out = _guard_text(kind, project, tmp_path)
    # the backup scripts pick podman first themselves, so the step must say CONTAINER_ENGINE=docker on that line
    assert re.search(r"CONTAINER_ENGINE\s*=\s*'?docker'?;?[^\"]*\"[^\"]*scripts/backup\.(ps1|sh)\"", out), out
    assert re.search(r'docker compose -p bee-with-me -f "?[^"\s]*docker/docker-compose\.yaml"? stop', out), out


@pytest.mark.Trait("Bug", "B60")
@pytest.mark.parametrize('kind', _guard_kinds())
def test_guard_rename_is_timestamped_and_podman_start_clears_the_engine_override(kind, project, tmp_path):
    out = _guard_text(kind, project, tmp_path)
    assert re.search(r'pgdata\.docker-\d{8}-\d{6}', out), out
    assert re.search(r'(Remove-Item Env:CONTAINER_ENGINE|unset CONTAINER_ENGINE)[^"]*"[^"]*start\.(ps1|sh)"', out), out
    if kind == 'sh':
        assert 'mv -n' in out, out


@pytest.mark.Trait("Bug", "B60")
@pytest.mark.parametrize('kind', _guard_kinds())
def test_guard_restore_step_stops_the_backend_and_names_a_dump_path(kind, project, tmp_path):
    out = _guard_text(kind, project, tmp_path)
    assert re.search(r'stop the backend[^"]*"[^"]*scripts/restore\.(ps1|sh)" "[^"]*data/backups/[^"]+"', out), out


@pytest.mark.Trait("Bug", "B60")
@pytest.mark.skipif(PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')
def test_acl_is_restricted_while_the_temp_secrets_file_is_still_empty(project, tmp_path):
    res = _fresh_install('ps', project, tmp_path, EXAMPLE)
    assert res.returncode == 0, res.out
    calls = [c for c in res.calls if c.startswith('icacls ')]
    assert calls == ['icacls size=0'], res.calls   # restricted before the key was written
    assert (project / '.env').stat().st_size > 0


@pytest.mark.Trait("Bug", "B60")
def test_temp_secrets_files_are_git_ignored():
    lines = [l.strip() for l in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()]
    assert '.env.new*' in lines, 'temp secrets file names must be ignored'
    assert 'data/' in lines   # the root data folder stays ignored


@pytest.mark.Trait("Bug", "B60")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
def test_start_sh_temp_secrets_file_is_made_by_mktemp_and_a_stale_one_is_ignored(project, tmp_path):
    stale = project / '.env.new'
    stale.write_text('stale', encoding='utf-8')
    res = _fresh_install('sh', project, tmp_path, EXAMPLE)
    assert res.returncode == 0, res.out
    assert stale.read_text(encoding='utf-8') == 'stale'   # a leftover is neither reused nor overwritten
    assert len(_secret_lines(project)) == 1
    names = sorted(p.name for p in project.iterdir() if p.name.startswith('.env.new'))
    assert names == ['.env.new'], names                    # no temp file of this run left behind
    text = (ROOT / 'start.sh').read_text(encoding='utf-8')
    assert 'mktemp' in text and re.search(r'trap .*rm -f', text)


# ── B61: the guard restores the step-(1) Docker dump, not "the newest file" ──

@pytest.mark.Trait("Bug", "B61")
@pytest.mark.parametrize('kind', _guard_kinds())
def test_guard_restore_step_names_the_step_1_dump_not_the_newest(kind, project, tmp_path):
    out = _guard_text(kind, project, tmp_path)
    assert 'newest' not in out.lower(), out     # step (3) makes a dump of the empty Podman database: that one is newer
    step1 = out.split('(2)')[0]
    step4 = re.split(r'(?<!step )\(4\)', out)[1]    # not the "step (4)" mention inside step 1
    assert 'dump' in step1 and re.search(r'note|write down', step1, re.I), step1   # step 1: note the file name it prints
    assert 'step (1)' in step4, step4                                              # step 4 restores that one
    assert re.search(r'scripts/restore\.(ps1|sh)" "[^"]*data/backups/[^"]+"', step4), step4
