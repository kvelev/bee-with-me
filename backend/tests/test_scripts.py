"""Static checks on the backup/start scripts plus a syntax parse of each."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.tests.shells import BASH, SKIP_REASON

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ['scripts/backup.ps1', 'scripts/backup.sh', 'start.ps1', 'start.sh']


def _read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


@pytest.mark.Trait("Task", "T5")
@pytest.mark.parametrize('rel', SCRIPTS)
def test_engine_is_podman_first_with_docker_fallback_and_override(rel):
    text = _read(rel)
    assert 'CONTAINER_ENGINE' in text
    start = text.index('CONTAINER_ENGINE')
    assert text.index('podman', start) < text.index('docker', start)   # podman is tried first
    # no hard-coded engine calls: every exec/cp/compose/ps goes through the chosen engine
    assert not re.search(r'^\s*docker (exec|cp|compose|ps|info)\b', text, re.MULTILINE)


@pytest.mark.Trait("Task", "T5")
@pytest.mark.parametrize('rel', ['scripts/backup.ps1', 'scripts/backup.sh'])
def test_backup_uses_custom_format_written_inside_the_container(rel):
    text = _read(rel)
    assert 'pg_dump -Fc' in text
    assert ' cp ' in text
    assert 'pg_restore' in text
    assert 'Out-File' not in text
    assert '.dump' in text
    assert 'com.docker.compose.service=db' in text


@pytest.mark.Trait("Task", "T5")
@pytest.mark.parametrize('rel,marker', [('start.ps1', "'Starting backend"), ('start.sh', "'Starting backend")])
def test_start_script_backs_up_before_the_backend_starts(rel, marker):
    text = _read(rel)
    check = text.index('backend.db.migrate status')
    backup = text.index('backup.', check)
    start = text.index(marker)
    assert check < backup < start


@pytest.mark.Trait("Task", "T5")
@pytest.mark.parametrize('rel,flags', [('start.ps1', ['SkipContainers', "Alias('SkipDocker')"]),
                                       ('start.sh', ['--skip-containers', '--skip-docker'])])
def test_old_skip_flag_still_works(rel, flags):
    text = _read(rel)
    assert all(flag in text for flag in flags)


@pytest.mark.Trait("Task", "T5")
def test_readme_documents_podman_first():
    text = _read('README.md')
    assert text.index('podman compose') < text.index('docker compose')
    assert 'podman machine start' in text
    assert 'podman-restart' in text
    assert 'docker-compose.podman-machine.yaml' in text


@pytest.mark.Trait("Task", "T5")
@pytest.mark.parametrize('rel', ['start.ps1', 'start.sh'])
def test_start_scripts_use_the_podman_machine_override(rel):
    assert 'docker-compose.podman-machine.yaml' in _read(rel)


@pytest.mark.Trait("Task", "T5")
def test_podman_machine_override_uses_named_volume_and_host_network():
    text = _read('docker/docker-compose.podman-machine.yaml')
    assert 'pgdata:/var/lib/postgresql/data' in text
    assert 'network_mode: host' in text
    assert 'ports: !reset []' in text


@pytest.mark.Trait("Task", "T5")
@pytest.mark.skipif(shutil.which('powershell') is None and shutil.which('pwsh') is None, reason='no PowerShell')
@pytest.mark.parametrize('rel', ['scripts/backup.ps1', 'start.ps1'])
def test_powershell_scripts_parse(rel):
    exe = shutil.which('pwsh') or shutil.which('powershell')
    cmd = ("$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
           f"'{ROOT / rel}', [ref]$null, [ref]$e) | Out-Null; if ($e) {{ $e; exit 1 }}")
    assert subprocess.run([exe, '-NoProfile', '-Command', cmd]).returncode == 0


@pytest.mark.Trait("Task", "T5")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
@pytest.mark.parametrize('rel', ['scripts/backup.sh', 'start.sh'])
def test_bash_scripts_parse(rel):
    # BASH comes from shells.find_bash(): on Windows a bare 'bash' resolves to System32\bash.exe
    # (WSL) first, which can't read Windows paths, so Git Bash is used instead (B22).
    assert subprocess.run([BASH, '-n', str(ROOT / rel)]).returncode == 0


# ── B4: only this compose project's db container is ever picked ──────────────

@pytest.mark.Trait("Bug", "B4")
def test_compose_project_is_named_bee_with_me():
    lines = [l for l in _read('docker/docker-compose.yaml').splitlines()
             if l.strip() and not l.lstrip().startswith('#')]
    assert lines[0] == 'name: bee-with-me'


@pytest.mark.Trait("Bug", "B4")
@pytest.mark.parametrize('rel', ['scripts/backup.ps1', 'scripts/backup.sh'])
def test_backup_filters_on_project_and_service_labels(rel):
    text = _read(rel)
    ps_lines = [l for l in text.splitlines() if ' ps -q ' in l]
    assert ps_lines, 'no container lookup found'
    for line in ps_lines:
        assert 'label=com.docker.compose.project=bee-with-me' in line
        assert 'label=com.docker.compose.service=db' in line


@pytest.mark.Trait("Bug", "B4")
def test_readme_names_the_compose_project_and_volume():
    text = _read('README.md')
    assert 'bee-with-me-db-1' in text
    assert 'bee-with-me_pgdata' in text


# ── B5: never start (and migrate) without the pre-migration backup ───────────

_REFUSE = ('Could not check database migrations (database not reachable?) - not starting, '
           'so the database is never migrated without a backup.')


@pytest.mark.Trait("Bug", "B5")
@pytest.mark.parametrize('rel,deadline,pause', [
    ('start.ps1', 'AddSeconds(90)', 'Start-Sleep -Seconds 3'),
    ('start.sh', 'SECONDS + 90', 'sleep 3'),
])
def test_start_script_retries_migration_check_for_90_seconds(rel, deadline, pause):
    text = _read(rel)
    section = text[text.index('Checking database migrations'):text.index("'Starting backend")]
    assert deadline in section
    assert pause in section
    assert 'backend.db.migrate status' in section


@pytest.mark.Trait("Bug", "B5")
@pytest.mark.parametrize('rel,keyword', [('start.ps1', 'throw'), ('start.sh', 'die')])
def test_start_script_refuses_when_migration_check_keeps_failing(rel, keyword):
    text = _read(rel)
    lines = [l.strip() for l in text.splitlines() if _REFUSE in l]
    assert lines, 'refusal message missing'
    assert all(keyword in l.split(_REFUSE)[0] for l in lines)
    assert 'compose -f docker' in lines[0] and 'logs' in lines[0]
    # the old warn-and-continue branch is gone
    assert 'the backend will report the problem on start' not in text


@pytest.mark.Trait("Bug", "B5")
def test_start_ps1_wraps_backup_in_try_catch():
    text = _read('start.ps1')
    assert re.search(
        r"try\s*\{\s*&\s*\"\$root\\scripts\\backup\.ps1\"[^}]*\}\s*catch\s*\{\s*"
        r"throw 'Backup failed - not starting, so the database is never migrated without a backup\.'",
        text,
    )
    assert 'if (-not $?)' not in text


@pytest.mark.Trait("Bug", "B5")
def test_readme_says_skip_containers_skips_the_backup():
    text = _read('README.md')
    assert re.search(r'-SkipContainers.{0,400}backup', text, re.DOTALL)
    assert re.search(r'--skip-containers.{0,400}backup', text, re.DOTALL)
    section = text[text.index('### 2. Database'):text.index('The backend creates')]
    assert 'podman-machine' in section


# ── B6: Postgres and tiles only reachable on loopback ────────────────────────

@pytest.mark.Trait("Bug", "B6")
def test_podman_machine_override_binds_postgres_to_loopback():
    text = _read('docker/docker-compose.podman-machine.yaml')
    assert 'listen_addresses=127.0.0.1' in text
    assert re.search(r'command:\s*\["postgres",\s*"-c",\s*"listen_addresses=127\.0\.0\.1"\]', text)


@pytest.mark.Trait("Bug", "B6")
def test_base_compose_publishes_db_and_tiles_on_loopback_only():
    text = _read('docker/docker-compose.yaml')
    published = re.findall(r'^\s*-\s*"([^"]+)"\s*$', text, re.MULTILINE)
    port_maps = [p for p in published if re.search(r':\d+$', p) and not p.startswith('..')]
    assert '127.0.0.1:${POSTGRES_PORT:-5432}:5432' in port_maps
    assert '127.0.0.1:8080:8080' in port_maps
    assert all(p.startswith('127.0.0.1:') for p in port_maps), port_maps


@pytest.mark.Trait("Bug", "B6")
def test_readme_says_database_listens_on_localhost_only():
    text = _read('README.md')
    assert re.search(r'only listens on localhost', text)


# ── B8: dumps private to the user; temp dump always removed; backups ignored by git ──

@pytest.mark.Trait("Bug", "B8")
def test_backup_sh_creates_private_dumps():
    text = _read('scripts/backup.sh')
    umask = text.index('umask 077')
    assert umask < text.index('mkdir -p "$OUT_DIR"')
    copy = text.index('cp "$CONTAINER:$IN_CONTAINER" "$TARGET"')
    assert copy < text.index('chmod 600 "$TARGET"')


@pytest.mark.Trait("Bug", "B8")
def test_backup_sh_traps_exit_to_remove_the_temp_dump():
    text = _read('scripts/backup.sh')
    traps = [l for l in text.splitlines() if l.strip().startswith('trap ')]
    assert traps, 'no trap'
    trap = traps[0]
    assert 'EXIT' in trap and 'rm -f' in trap and 'IN_CONTAINER' in trap
    # armed before the dump is written (so a failed copy still cleans up)
    assert text.index(trap) < text.index('pg_dump -Fc')


@pytest.mark.Trait("Bug", "B8")
def test_backup_ps1_restricts_a_created_outdir_to_the_current_user():
    text = _read('scripts/backup.ps1')
    assert '/inheritance:r' in text
    # B18: granted by SID (was ${env:USERNAME}), through Set-PrivateAcl right after the folder is created
    assert '/grant:r "*${mySid}:(OI)(CI)F"' in text
    create = text.index('New-Item -ItemType Directory -Path $OutDir')
    assert create < text.index('Set-PrivateAcl $OutDir', create) < create + 200


@pytest.mark.Trait("Bug", "B8")
def test_backup_ps1_always_removes_the_temp_dump():
    text = _read('scripts/backup.ps1')
    m = re.search(r'try\s*\{(?P<body>.*?)\}\s*finally\s*\{(?P<fin>.*?)\}', text, re.DOTALL)
    assert m, 'no try/finally'
    assert 'pg_dump -Fc' in m['body'] and ' cp ' in m['body']
    assert 'rm -f $inContainer' in m['fin']


@pytest.mark.Trait("Bug", "B8")
def test_gitignore_has_backup_rules():
    lines = _read('.gitignore').splitlines()
    assert '/backups/' in lines
    assert '*.dump' in lines


@pytest.mark.Trait("Bug", "B8")
@pytest.mark.skipif(shutil.which('git') is None, reason='no git')
@pytest.mark.parametrize('path', ['backups/x.dump', 'elsewhere/beewithme_1.dump'])
def test_git_ignores_dumps(path):
    res = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', '--no-index', path])
    assert res.returncode == 0, f'{path} is not ignored'


# ── B9: retry only "unreachable" (3); invalid files (1) refuse at once ───────

_INVALID = 'migration files are invalid: see the message above'


def _migration_section(rel):
    text = _read(rel)
    return text[text.index('Checking database migrations'):text.index("'Starting backend")]


@pytest.mark.Trait("Bug", "B9")
@pytest.mark.parametrize('rel,retry', [
    ('start.ps1', '$migExit -ne 3 -or'),
    ('start.sh', '$mig -eq 3 && $SECONDS -lt $mig_deadline'),
])
def test_start_script_retries_only_exit_3(rel, retry):
    section = _migration_section(rel)
    assert retry in section
    assert '$migExit -ne 1' not in section and '$mig -eq 1 &&' not in section


@pytest.mark.Trait("Bug", "B9")
@pytest.mark.parametrize('rel,case1,keyword', [
    ('start.ps1', re.compile(r'^\s*1\s*\{\s*throw\b'), 'throw'),
    ('start.sh', re.compile(r'^\s*1\)\s*die\b'), 'die'),
])
def test_start_script_refuses_at_once_on_invalid_migration_files(rel, case1, keyword):
    lines = _migration_section(rel).splitlines()
    hits = [l for l in lines if case1.search(l)]
    assert hits, 'no branch for exit 1'
    assert _INVALID in hits[0]
    # exit 3 (after the retries) still refuses with the "not reachable" message
    assert any(_REFUSE in l and keyword in l for l in lines)


@pytest.mark.Trait("Bug", "B9")
def test_start_ps1_backup_failure_keeps_the_error_text():
    text = _read('start.ps1')
    m = re.search(r"catch\s*\{\s*throw 'Backup failed[^\n]*", text)
    assert m and '$_.Exception.Message' in m.group(0)


@pytest.mark.Trait("Bug", "B9")
def test_gitattributes_forces_lf_for_shell_scripts():
    lines = [l.split() for l in _read('.gitattributes').splitlines() if l.strip() and not l.startswith('#')]
    assert ['*.sh', 'text', 'eol=lf'] in lines


@pytest.mark.Trait("Bug", "B9")
@pytest.mark.skipif(shutil.which('git') is None, reason='no git')
@pytest.mark.parametrize('rel', ['start.sh', 'scripts/backup.sh'])
def test_shell_scripts_are_lf_in_the_index_and_attributes(rel):
    attr = subprocess.run(['git', '-C', str(ROOT), 'check-attr', 'eol', '--', rel],
                          capture_output=True, text=True).stdout
    assert attr.strip().endswith('eol: lf')
    blob = subprocess.run(['git', '-C', str(ROOT), 'show', f':{rel}'], capture_output=True).stdout
    assert blob and b'\r\n' not in blob


@pytest.mark.Trait("Bug", "B9")
def test_readme_lists_exit_code_3():
    text = _read('README.md')
    line = next(l for l in text.splitlines() if 'backend.db.migrate status' in l and 'exit 0' in l)
    assert '3 = database not reachable' in line and '1 = ' in line


# ── B10: restore scripts (drop/create, single-transaction restore, guarded) ──

from backend.tests.test_restore import CREATE_CMD, DROP_CMD, RESTORE_CMD  # noqa: E402

RESTORE_SCRIPTS = ['scripts/restore.ps1', 'scripts/restore.sh']


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.parametrize('rel', RESTORE_SCRIPTS)
def test_restore_script_finds_the_container_like_backup(rel):
    text = _read(rel)
    assert 'CONTAINER_ENGINE' in text
    start = text.index('CONTAINER_ENGINE')
    assert text.index('podman', start) < text.index('docker', start)
    assert not re.search(r'^\s*docker (exec|cp|compose|ps|info)\b', text, re.MULTILINE)
    ps_lines = [l for l in text.splitlines() if ' ps -q ' in l]
    assert ps_lines
    for line in ps_lines:
        assert 'label=com.docker.compose.project=bee-with-me' in line
        assert 'label=com.docker.compose.service=db' in line


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.parametrize('rel', RESTORE_SCRIPTS)
def test_restore_script_drops_creates_and_restores_in_one_transaction(rel):
    text = _read(rel)
    drop = text.index(' '.join(DROP_CMD))
    create = text.index(' '.join(CREATE_CMD) + ' ', drop)
    restore = text.index(' '.join(RESTORE_CMD), create)
    assert drop < create < restore
    assert '--clean' not in text   # the old "restore over the live database" way is gone
    assert text.index('backend.db.migrate status', restore)


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.parametrize('rel,force,yes', [('scripts/restore.ps1', '$Force', '$Yes'),
                                           ('scripts/restore.sh', '--force', '--yes')])
def test_restore_script_refuses_while_backend_runs_and_asks_first(rel, force, yes):
    text = _read(rel)
    assert '8000' in text
    assert force in text and yes in text
    first_drop = text.index(' '.join(DROP_CMD))
    assert text.index('8000') < first_drop
    assert re.search(r'Read-Host|read -r', text)


@pytest.mark.Trait("Bug", "B10")
def test_restore_ps1_always_removes_the_temp_dump():
    text = _read('scripts/restore.ps1')
    blocks = [m for m in re.finditer(r'\btry\s*\{(?P<body>.*?)\}\s*finally\s*\{(?P<fin>.*?)\}', text, re.DOTALL)
              if 'pg_restore' in m['body']]
    assert blocks, 'no try/finally around the restore'
    assert 'rm -f $inContainer' in blocks[0]['fin']


@pytest.mark.Trait("Bug", "B10")
def test_restore_sh_traps_exit_to_remove_the_temp_dump():
    text = _read('scripts/restore.sh')
    traps = [l for l in text.splitlines() if l.strip().startswith('trap ')]
    assert traps and 'EXIT' in traps[0] and 'rm -f' in traps[0] and 'IN_CONTAINER' in traps[0]
    assert text.index(traps[0]) < text.index(' cp ')


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.parametrize('rel,hint', [('scripts/backup.ps1', 'restore.ps1'), ('scripts/backup.sh', 'restore.sh')])
def test_backup_hint_points_at_the_restore_script(rel, hint):
    text = _read(rel)
    tail = text[text.index('To restore'):]
    assert hint in tail
    assert '--clean' not in text
    assert re.search(r"""['"]\$target\\?['"]""", tail, re.IGNORECASE)   # the dump path is quoted


@pytest.mark.Trait("Bug", "B10")
def test_startup_failure_message_and_baseline_point_at_restore_scripts():
    main_text = _read('backend/main.py')
    assert 'scripts/restore.ps1' in main_text and 'scripts/restore.sh' in main_text
    down = _read('backend/db/migrations/0001_baseline.sql').split('-- migrate:down', 1)[1]
    assert 'restore.ps1' in down and 'restore.sh' in down


@pytest.mark.Trait("Bug", "B10")
def test_readme_has_a_backup_and_restore_section():
    text = _read('README.md')
    section = text[text.index('Backup and restore'):]
    assert 'restore.ps1' in section and 'restore.sh' in section
    assert section.lower().index('podman') < section.lower().index('docker')
    assert re.search(r'[Ss]top the backend', section)


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.skipif(shutil.which('powershell') is None and shutil.which('pwsh') is None, reason='no PowerShell')
def test_restore_ps1_parses():
    exe = shutil.which('pwsh') or shutil.which('powershell')
    cmd = ("$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
           f"'{ROOT / 'scripts/restore.ps1'}', [ref]$null, [ref]$e) | Out-Null; if ($e) {{ $e; exit 1 }}")
    assert subprocess.run([exe, '-NoProfile', '-Command', cmd]).returncode == 0


@pytest.mark.Trait("Bug", "B10")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
def test_restore_sh_parses():
    assert subprocess.run([BASH, '-n', str(ROOT / 'scripts/restore.sh')]).returncode == 0


# ── B12: explicit compose project; upgrade from the old project "docker" ─────

ALL_SCRIPTS = ['start.ps1', 'start.sh', 'scripts/backup.ps1', 'scripts/backup.sh',
               'scripts/restore.ps1', 'scripts/restore.sh']


def _compose_calls(text):
    """Lines (code or printed hints, not comments) that run a compose command."""
    return [l for l in text.splitlines()
            if not l.lstrip().startswith('#') and _COMPOSE_CALL.search(l)]


# `compose`, then only -p/-f options or a files array, then the subcommand
_COMPOSE_CALL = re.compile(r'\bcompose((\s+-[pf]\s+\S+)|(\s+@\w+)|(\s+"\$\{\w+\[@\]\}"))*\s+(up|down|logs)\b')


@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('rel', ALL_SCRIPTS)
def test_every_compose_call_names_the_project(rel):
    calls = _compose_calls(_read(rel))
    assert calls, 'no compose call found'
    for line in calls:
        assert re.search(r'-p (bee-with-me|docker)\b', line), line


@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('rel,param', [('scripts/backup.ps1', '[string]$Container'),
                                       ('scripts/backup.sh', '--container')])
def test_backup_accepts_a_container_override(rel, param):
    text = _read(rel)
    assert param in text
    lookup = text.index(' ps -q ')
    override = text.index('$Container' if rel.endswith('.ps1') else 'CONTAINER_OVERRIDE')
    assert override < lookup or 'CONTAINER_OVERRIDE' in text[lookup - 200:lookup + 200]


@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('rel,backup,refuse', [
    ('start.ps1', r'backup\.ps1"? -OutDir "\$root\\data\\backups" -Container \$oldDb', 'throw'),
    ('start.sh', r'backup\.sh" --container "\$OLD_DB" "\$ROOT/data/backups"', 'die'),
])
def test_start_script_backs_up_and_stops_the_old_project_before_compose_up(rel, backup, refuse):
    text = _read(rel)
    find = text.index('label=com.docker.compose.project=docker')
    assert 'label=com.docker.compose.service=db' in text[find:find + 200]
    m = re.search(backup, text)
    assert m, 'old container is not backed up through the override'
    after_backup = text[m.end():m.end() + 300]
    assert refuse in after_backup   # a failed backup refuses to continue
    down = re.search(r'compose -p docker -f "\$(root|ROOT)[\\/]docker[\\/]docker-compose\.yaml" down', text)
    assert down and ' -v' not in text[down.start():text.index('\n', down.start())]
    up = text.index('compose -p bee-with-me', down.end())
    assert find < m.start() < down.start() < up


@pytest.mark.Trait("Bug", "B12")
@pytest.mark.parametrize('rel', ['start.ps1', 'start.sh'])
def test_start_script_gives_restore_steps_for_the_old_podman_volume(rel):
    text = _read(rel)
    assert 'docker_pgdata' in text
    hint = text[text.index('docker_pgdata'):]
    assert 'restore.ps1' in hint[:600] if rel.endswith('.ps1') else 'restore.sh' in hint[:600]


@pytest.mark.Trait("Bug", "B12")
def test_readme_has_an_upgrade_note():
    text = _read('README.md')
    section = text[text.index('Upgrading from 1.7.1 or earlier'):]
    assert 'docker-db-1' in section[:1500] and 'docker_pgdata' in section[:1500]
    assert 'restore' in section[:1500]


# ── B13: PS 5.1 native stderr, validated dumps, .env parsing ─────────────────

PS_SCRIPTS = ['start.ps1', 'scripts/backup.ps1', 'scripts/restore.ps1']
SH_SCRIPTS = ['start.sh', 'scripts/backup.sh', 'scripts/restore.sh']
_PS_EXE = shutil.which('powershell') or shutil.which('pwsh')   # 5.1 first: that is where the bug lives

# quotes, a CRLF line end and an inline comment; '#' inside a value without a space stays
_ENV_SAMPLE = ('POSTGRES_DB="quoted_db" # the database\r\n'
               "POSTGRES_USER='single'\r\n"
               'POSTGRES_PORT=6543   # the port\r\n'
               '  PLAIN = value\r\n'
               'HASH=a#b\r\n'
               '# POSTGRES_HOST=commented-out\r\n')
_ENV_EXPECTED = {'POSTGRES_DB': 'quoted_db', 'POSTGRES_USER': 'single', 'POSTGRES_PORT': '6543',
                 'PLAIN': 'value', 'HASH': 'a#b', 'POSTGRES_HOST': 'DEFAULT'}


def _block(text, start, end_line='}'):
    i = text.index(start)
    j = text.index('\n' + end_line + '\n', i)
    return text[i:j + len(end_line) + 2]


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.parametrize('rel', PS_SCRIPTS)
def test_ps_scripts_run_every_engine_call_through_invoke_native(rel):
    text = _read(rel)
    fn = _block(text, 'function Invoke-Native')
    assert "$ErrorActionPreference = 'Continue'" in fn
    calls = [l for l in text.splitlines() if '& $engine' in l]
    assert calls
    for line in calls:
        assert 'Invoke-Native { & $engine' in line, line


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.skipif(_PS_EXE is None or shutil.which('cmd') is None, reason='needs PowerShell and cmd')
def test_invoke_native_ignores_stderr_and_keeps_the_exit_code(tmp_path):
    fn = _block(_read('start.ps1'), 'function Invoke-Native')
    script = tmp_path / 'probe.ps1'
    script.write_text("$ErrorActionPreference = 'Stop'\n" + fn +
                      'Invoke-Native { & cmd /c "echo warning 1>&2 & exit 0" *> $null }\n'
                      '"first=$LASTEXITCODE"\n'
                      'Invoke-Native { & cmd /c "echo broken 1>&2 & exit 3" 2>&1 } | Out-Null\n'
                      '"second=$LASTEXITCODE"\n'
                      "\"eap=$ErrorActionPreference\"\n", encoding='utf-8')
    res = subprocess.run([_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert 'first=0' in res.stdout and 'second=3' in res.stdout and 'eap=Stop' in res.stdout


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.skipif(_PS_EXE is None, reason='no PowerShell')
@pytest.mark.parametrize('rel', PS_SCRIPTS)
def test_ps_dotenv_parsing_strips_quotes_cr_and_comments(rel, tmp_path):
    fn = _block(_read(rel), 'function Read-DotEnv')
    (tmp_path / '.env').write_bytes(_ENV_SAMPLE.encode('utf-8'))
    script = tmp_path / 'probe.ps1'
    keys = ', '.join(f"'{k}'" for k in _ENV_EXPECTED)
    script.write_text("$ErrorActionPreference = 'Stop'\n" + fn +
                      f"$v = Read-DotEnv '{tmp_path / '.env'}'\n"
                      f"foreach ($k in @({keys})) {{ $x = if ($v[$k]) {{ $v[$k] }} else {{ 'DEFAULT' }}; \"$k=[$x]\" }}\n",
                      encoding='utf-8')
    res = subprocess.run([_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    for key, value in _ENV_EXPECTED.items():
        assert f'{key}=[{value}]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
@pytest.mark.parametrize('rel', SH_SCRIPTS)
def test_sh_dotenv_parsing_strips_quotes_cr_and_comments(rel, tmp_path):
    fn = _block(_read(rel), 'env_value() {')
    (tmp_path / '.env').write_bytes(_ENV_SAMPLE.encode('utf-8'))
    probe = (f'ROOT="{tmp_path.as_posix()}"\n' + fn +
             ''.join(f'printf "%s=[%s]\\n" {k} "$(env_value {k} DEFAULT)"\n' for k in _ENV_EXPECTED))
    res = subprocess.run([BASH, '-c', probe], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    for key, value in _ENV_EXPECTED.items():
        assert f'{key}=[{value}]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.parametrize('rel', ['scripts/backup.ps1', 'scripts/backup.sh'])
def test_backup_writes_a_partial_file_and_keeps_it_only_after_validation(rel):
    text = _read(rel)
    assert '.partial' in text
    validate = text.index('pg_restore -l')
    copy = text.index(' cp ', text.index('pg_dump -Fc'))
    rename = text.index('Move-Item -LiteralPath $partial' if rel.endswith('.ps1') else 'mv -f "$TARGET" "$FINAL"')
    assert text.index('pg_dump -Fc') < validate < copy < rename
    if rel.endswith('.ps1'):
        catch = re.search(r'\}\s*catch\s*\{(?P<body>.*?)\}\s*finally', text, re.DOTALL)
        assert catch and 'Remove-Item -LiteralPath $partial' in catch['body']
    else:
        trap = next(l for l in text.splitlines() if l.strip().startswith('trap '))
        assert 'rm -f "$PARTIAL"' in trap


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.parametrize('rel,random', [('scripts/backup.ps1', 'NewGuid()'), ('scripts/backup.sh', '$RANDOM'),
                                        ('scripts/restore.ps1', 'NewGuid()'), ('scripts/restore.sh', '$RANDOM')])
def test_dump_names_carry_a_random_suffix(rel, random):
    text = _read(rel)
    assert random in text
    line = next(l for l in text.splitlines() if '/tmp/beewithme_' in l and not l.lstrip().startswith('#'))
    assert 'suffix' in line or 'STAMP' in line or 'RANDOM' in line, line


@pytest.mark.Trait("Bug", "B13")
@pytest.mark.parametrize('rel,prune', [
    ('scripts/backup.ps1', "Where-Object { $_.Name -like 'beewithme_*.dump' }"),
    ('scripts/backup.sh', 'ls -1t "$OUT_DIR"/beewithme_*.dump'),
])
def test_pruning_only_counts_finished_dumps(rel, prune):
    assert prune in _read(rel)


# ── B16: restore checks the dump, restores into a side database, then swaps ──

def _code_lines(text):
    return [l for l in text.splitlines() if not l.lstrip().startswith('#')]


@pytest.mark.Trait("Bug", "B16")
@pytest.mark.parametrize('rel', RESTORE_SCRIPTS)
def test_restore_checks_the_dump_before_touching_any_database(rel):
    body = '\n'.join(_code_lines(_read(rel)))
    check = body.index('pg_restore -l')
    assert check < body.index('createdb -U')
    assert check < body.index(' '.join(RESTORE_CMD))
    assert check < body.index('ALTER DATABASE')
    assert body.index(' '.join(RESTORE_CMD)) < body.index('RENAME TO')
    assert 'PGDMP' in body and 'plain SQL dump' in body
    assert '_restore_' in body and '_before_restore_' in body


@pytest.mark.Trait("Bug", "B16")
@pytest.mark.parametrize('rel', RESTORE_SCRIPTS)
def test_restore_never_drops_the_live_database(rel):
    lines = _code_lines(_read(rel))
    body = '\n'.join(lines)
    check_line = next(i for i, l in enumerate(lines) if 'pg_restore -l' in l)
    drops = [(i, l) for i, l in enumerate(lines) if 'dropdb' in l]
    assert drops
    for i, line in drops:
        # only the side database (cleanup) or, in a printed hint, the kept old database
        assert re.search(r'restoreDb|RESTORE_DB|keptDb|KEPT_DB', line), line
        assert not re.search(r'dropdb\b.*[\s"]\$(db|DB)"?(\s|$|\}|\))', line), line
        if i < check_line:
            assert re.search(r'restoreDb|RESTORE_DB', line), line   # before the check: cleanup only
    assert '--force' in body


# ── B18: gate re-run minors ──────────────────────────────────────────────────

@pytest.mark.Trait("Bug", "B18")
def test_start_ps1_runs_pip_and_migrate_status_through_invoke_native():
    text = _read('start.ps1')
    for marker in ('-m pip install', '-m backend.db.migrate status'):
        line = next(l for l in _code_lines(text) if marker in l and 'python.exe' in l)
        assert 'Invoke-Native {' in line, line
    after_pip = text[text.index('-m pip install'):][:400]
    assert '$LASTEXITCODE' in after_pip and 'pip install failed' in after_pip


@pytest.mark.Trait("Bug", "B18")
def test_start_sh_reports_a_failing_pip_install():
    text = _read('start.sh')
    pip = text.index('-m pip install')
    window = text[pip - 80:pip + 300]
    assert re.search(r'if\s+!\s+"\$ROOT/\.venv/bin/python" -m pip install', window) and 'pip install failed' in window


_ENV_EXPORT_SAMPLE = 'export POSTGRES_DB=exported_db\r\n  export   POSTGRES_USER="exp_user"\r\nexporter=x\r\n'
_ENV_EXPORT_EXPECTED = {'POSTGRES_DB': 'exported_db', 'POSTGRES_USER': 'exp_user', 'exporter': 'x'}


@pytest.mark.Trait("Bug", "B18")
@pytest.mark.skipif(_PS_EXE is None, reason='no PowerShell')
@pytest.mark.parametrize('rel', PS_SCRIPTS)
def test_ps_dotenv_parsing_accepts_export_lines(rel, tmp_path):
    fn = _block(_read(rel), 'function Read-DotEnv')
    (tmp_path / '.env').write_bytes(_ENV_EXPORT_SAMPLE.encode('utf-8'))
    script = tmp_path / 'probe.ps1'
    keys = ', '.join(f"'{k}'" for k in _ENV_EXPORT_EXPECTED)
    script.write_text("$ErrorActionPreference = 'Stop'\n" + fn +
                      f"$v = Read-DotEnv '{tmp_path / '.env'}'\n"
                      f"foreach ($k in @({keys})) {{ \"$k=[$($v[$k])]\" }}\n", encoding='utf-8')
    res = subprocess.run([_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    for key, value in _ENV_EXPORT_EXPECTED.items():
        assert f'{key}=[{value}]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B18")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
@pytest.mark.parametrize('rel', SH_SCRIPTS)
def test_sh_dotenv_parsing_accepts_export_lines(rel, tmp_path):
    fn = _block(_read(rel), 'env_value() {')
    (tmp_path / '.env').write_bytes(_ENV_EXPORT_SAMPLE.encode('utf-8'))
    probe = (f'ROOT="{tmp_path.as_posix()}"\n' + fn +
             ''.join(f'printf "%s=[%s]\\n" {k} "$(env_value {k} DEFAULT)"\n' for k in _ENV_EXPORT_EXPECTED))
    res = subprocess.run([BASH, '-c', probe], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    for key, value in _ENV_EXPORT_EXPECTED.items():
        assert f'{key}=[{value}]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B18")
@pytest.mark.parametrize('rel,env_first', [
    ('scripts/backup.ps1', r'\$env:POSTGRES_DB'), ('scripts/backup.sh', r'\$\{POSTGRES_DB:-'),
    ('scripts/restore.ps1', r'\$env:POSTGRES_DB'), ('scripts/restore.sh', r'\$\{POSTGRES_DB:-'),
])
def test_process_env_overrides_the_dotenv_file(rel, env_first):
    text = _read(rel)
    assert re.search(env_first, text), 'POSTGRES_DB from the environment is not read first'
    assert re.search(env_first.replace('DB', 'USER'), text), 'POSTGRES_USER from the environment is not read first'


@pytest.mark.Trait("Bug", "B18")
@pytest.mark.parametrize('rel', ['scripts/backup.ps1', 'scripts/backup.sh'])
def test_backup_marker_records_the_database(rel):
    text = _read(rel)
    assert 'current_database()' in text
    assert re.search(r'["\']?database["\']?\s*[=:]', text)


@pytest.mark.Trait("Bug", "B18")
def test_backup_ps1_grants_the_dump_folder_by_sid_and_reapplies_when_unrestricted():
    text = _read('scripts/backup.ps1')
    assert '[Security.Principal.WindowsIdentity]::GetCurrent().User.Value' in text
    icacls = [l for l in _code_lines(text) if 'icacls' in l and '/grant' in l]
    assert icacls and all('*$' in l or '"*' in l for l in icacls), icacls
    assert '${env:USERNAME}:' not in text
    assert 'AreAccessRulesProtected' in text


@pytest.mark.Trait("Bug", "B18")
def test_backup_sh_notes_that_modes_are_not_enforced_under_git_bash():
    text = _read('scripts/backup.sh')
    i = text.index('not enforced on NTFS')
    assert 'MINGW*|MSYS*' in text[i - 400:i] and 'backup.ps1' in text[i:i + 300]


@pytest.mark.Trait("Bug", "B18")
def test_backup_ps1_restore_hint_is_double_quoted():
    text = _read('scripts/backup.ps1')
    hint = next(l for l in text.splitlines() if 'restore.ps1' in l and 'Write-Host' in l)
    assert "'$root" not in hint and "'$target'" not in hint, hint
    assert '""$target""' in hint and 'restore.ps1""' in hint, hint


@pytest.mark.Trait("Bug", "B18")
def test_gitignore_ignores_partial_dumps():
    assert '*.dump.partial' in _read('.gitignore').splitlines()


@pytest.mark.Trait("Bug", "B18")
def test_readme_reset_commands_name_the_project_and_no_field_start_uses_reload():
    text = _read('README.md')
    for line in text.splitlines():
        if re.search(r'compose (down|up)\b', line) or re.search(r'compose\b.*\b(down -v)\b', line):
            assert '-p bee-with-me' in line or '-p docker' in line or 'docker compose -p' in line, line
        if re.search(r'uvicorn backend\.main:app --reload', line):
            assert 'ALLOW_MIGRATE_WITHOUT_BACKUP' in line, line


@pytest.mark.Trait("Bug", "B18")
def test_readme_backup_section_has_the_security_notes():
    text = _read('README.md')
    section = text[text.index('#### Backup and restore'):text.index('### 3. Backend')]
    assert 'trusted' in section and 'superuser' in section
    assert 'FAT' in section and 'exFAT' in section and 'creates the folder' in section


# ── B20: .env keys in any case, KEEP >= 1, no restore over a system database ──────────────────

_ENV_LOWER_SAMPLE = 'postgres_db=lower_db\r\nPostgres_User=mixed_user\r\n'


@pytest.mark.Trait("Bug", "B20")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
@pytest.mark.parametrize('rel', SH_SCRIPTS)
def test_sh_dotenv_keys_match_in_any_case(rel, tmp_path):
    fn = _block(_read(rel), 'env_value() {')
    (tmp_path / '.env').write_bytes(_ENV_LOWER_SAMPLE.encode('utf-8'))
    probe = (f'ROOT="{tmp_path.as_posix()}"\n' + fn +
             'printf "DB=[%s] USER=[%s]\\n" "$(env_value POSTGRES_DB DEFAULT)" "$(env_value POSTGRES_USER DEFAULT)"\n')
    res = subprocess.run([BASH, '-c', probe], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert 'DB=[lower_db] USER=[mixed_user]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B20")
@pytest.mark.skipif(_PS_EXE is None, reason='no PowerShell')
@pytest.mark.parametrize('rel', PS_SCRIPTS)
def test_ps_dotenv_keys_match_in_any_case(rel, tmp_path):
    fn = _block(_read(rel), 'function Read-DotEnv')
    (tmp_path / '.env').write_bytes(_ENV_LOWER_SAMPLE.encode('utf-8'))
    script = tmp_path / 'probe.ps1'
    script.write_text("$ErrorActionPreference = 'Stop'\n" + fn +
                      f"$v = Read-DotEnv '{tmp_path / '.env'}'\n"
                      "\"DB=[$($v['POSTGRES_DB'])] USER=[$($v['POSTGRES_USER'])]\"\n", encoding='utf-8')
    res = subprocess.run([_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert 'DB=[lower_db] USER=[mixed_user]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B20")
def test_readme_says_an_empty_environment_variable_counts_as_unset():
    text = _read('README.md')
    section = text[text.index('#### Backup and restore'):text.index('### 3. Backend')]
    assert 'empty string' in section and 'unset' in section


def _run_script(kind, rel, tmp_path, args, **env_overrides):
    """Runs a copy of a backup/restore script with an engine that does not exist (stops before any container)."""
    from backend.tests.script_env import script_env
    proj = tmp_path / 'proj'
    (proj / 'scripts').mkdir(parents=True, exist_ok=True)
    ext = 'ps1' if kind == 'ps' else 'sh'
    src = ROOT / f'{rel}.{ext}'
    dst = proj / f'{rel}.{ext}'
    dst.write_text(src.read_text(encoding='utf-8').replace('\r\n', '\n'), encoding='utf-8',
                   newline='\n' if kind == 'sh' else '\r\n')
    env = script_env(CONTAINER_ENGINE='bwm-no-such-engine', **env_overrides)
    if kind == 'ps':
        cmd = [_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(dst), *args]
    else:
        cmd = [BASH, dst.as_posix(), *args]
    res = subprocess.run(cmd, cwd=proj, env=env, capture_output=True, text=True, timeout=120)
    res.out = res.stdout + res.stderr
    return res


_KINDS = [
    # backup.ps1/restore.ps1 are Windows-only (WindowsIdentity, icacls): pwsh on Linux/macOS cannot run them
    pytest.param('ps', marks=pytest.mark.skipif(_PS_EXE is None or os.name != 'nt', reason='needs Windows PowerShell')),
    pytest.param('sh', marks=pytest.mark.skipif(BASH is None, reason=SKIP_REASON)),
]


@pytest.mark.Trait("Bug", "B20")
@pytest.mark.parametrize('kind', _KINDS)
@pytest.mark.parametrize('keep', ['0', '-1', 'abc'])
def test_backup_refuses_a_keep_below_one(kind, keep, tmp_path):
    out_dir = tmp_path / 'out'
    args = ['-OutDir', str(out_dir), '-Keep', keep] if kind == 'ps' else [out_dir.as_posix(), keep]
    res = _run_script(kind, 'scripts/backup', tmp_path, args)
    assert res.returncode != 0, res.out
    if not (kind == 'ps' and keep == 'abc'):   # PowerShell's own [int] binding refuses 'abc'
        assert 'Keep must be a whole number of at least 1' in res.out, res.out
    assert not out_dir.exists()   # refused before anything was created


@pytest.mark.Trait("Bug", "B20")
@pytest.mark.parametrize('kind', _KINDS)
@pytest.mark.parametrize('db', ['postgres', 'template0', 'template1'])
def test_restore_refuses_a_system_database(kind, db, tmp_path):
    dump = tmp_path / 'stub.dump'
    dump.write_bytes(b'PGDMP not really')
    args = [str(dump), '-Yes', '-Force'] if kind == 'ps' else ['--yes', '--force', dump.as_posix()]
    res = _run_script(kind, 'scripts/restore', tmp_path, args, POSTGRES_DB=db, POSTGRES_USER='rescuer')
    assert res.returncode != 0, res.out
    assert 'system database' in res.out, res.out


# ── B21: empty OutDir, locale-free name check, lower-case `export` only, README env notes ─────

@pytest.mark.Trait("Bug", "B21")
@pytest.mark.parametrize('kind', _KINDS)
@pytest.mark.parametrize('out_dir', ['', '   '])
def test_backup_with_an_empty_out_dir_uses_the_project_backups_folder(kind, out_dir, tmp_path):
    args = ['-OutDir', out_dir] if kind == 'ps' else [out_dir]
    res = _run_script(kind, 'scripts/backup', tmp_path, args)
    proj = tmp_path / 'proj'
    # the engine does not exist, so the run stops after the folder was made: <root>/backups, as backup.sh ""
    assert (proj / 'backups').is_dir(), res.out
    assert {p.name for p in proj.iterdir() if p.is_dir()} == {'scripts', 'backups'}, res.out
    assert 'is not restricted to this user' not in res.out, res.out   # never pointed at a drive root


@pytest.mark.Trait("Bug", "B21")
def test_backup_ps1_appends_dot_only_to_a_bare_drive_letter():
    text = _read('scripts/backup.ps1')
    line = next(l for l in _code_lines(text) if r"+= '\.'" in l)
    assert '-not $OutDir' not in line, line
    assert r"'^[A-Za-z]:\z'" in line, line


def _locale_available(name):
    if BASH is None:
        return False
    res = subprocess.run([BASH, '-c', 'locale -a'], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        return False
    want = name.lower().replace('-', '')
    return any(l.strip().lower().replace('-', '') == want for l in res.stdout.splitlines())


@pytest.mark.Trait("Bug", "B21")
@pytest.mark.skipif(not _locale_available('en_US.UTF-8'), reason='locale en_US.UTF-8 not installed')
@pytest.mark.parametrize('db', ['Postgres', 'Template1', 'Bwm_x', 'POSTGRES'])
def test_restore_sh_refuses_upper_case_names_under_a_utf8_locale(db, tmp_path):
    dump = tmp_path / 'stub.dump'
    dump.write_bytes(b'PGDMP not really')
    res = _run_script('sh', 'scripts/restore', tmp_path, ['--yes', '--force', dump.as_posix()],
                      POSTGRES_DB=db, POSTGRES_USER='rescuer', LC_ALL='en_US.UTF-8', LANG='en_US.UTF-8')
    assert res.returncode != 0, res.out
    assert 'restore supports database names' in res.out or 'system database' in res.out, res.out


@pytest.mark.Trait("Bug", "B21")
@pytest.mark.parametrize('kind', _KINDS)
@pytest.mark.parametrize('db', ['Postgres', 'Template1', 'Bwm_x'])
def test_restore_refuses_upper_case_names(kind, db, tmp_path):
    dump = tmp_path / 'stub.dump'
    dump.write_bytes(b'PGDMP not really')
    args = [str(dump), '-Yes', '-Force'] if kind == 'ps' else ['--yes', '--force', dump.as_posix()]
    res = _run_script(kind, 'scripts/restore', tmp_path, args, POSTGRES_DB=db, POSTGRES_USER='rescuer')
    assert res.returncode != 0, res.out
    assert 'restore supports database names' in res.out or 'system database' in res.out, res.out


@pytest.mark.Trait("Bug", "B21")
@pytest.mark.parametrize('kind', _KINDS)
def test_restore_refuses_template_postgis(kind, tmp_path):
    dump = tmp_path / 'stub.dump'
    dump.write_bytes(b'PGDMP not really')
    args = [str(dump), '-Yes', '-Force'] if kind == 'ps' else ['--yes', '--force', dump.as_posix()]
    res = _run_script(kind, 'scripts/restore', tmp_path, args, POSTGRES_DB='template_postgis', POSTGRES_USER='rescuer')
    assert res.returncode != 0, res.out
    assert 'system database' in res.out, res.out


@pytest.mark.Trait("Bug", "B21")
def test_restore_sh_name_check_does_not_depend_on_the_locale():
    lines = _code_lines(_read('scripts/restore.sh'))
    check = next(l for l in lines if 'restore supports database names' in l)
    assert 'a-z' not in check or 'LC_ALL=C' in check, check
    i = next(i for i, l in enumerate(lines) if 'template_postgis' in l)
    # compared as is: NAME_RE above already admits lower-case names only (no ${DB,,}: bash 3.2)
    assert lines[i - 1].strip() == 'case "$DB" in', lines[i - 1]


@pytest.mark.Trait("Bug", "B21")
def test_restore_ps1_compares_reserved_names_lower_cased():
    line = next(l for l in _code_lines(_read('scripts/restore.ps1')) if 'template_postgis' in l)
    assert 'ToLowerInvariant()' in line, line


_ENV_UPPER_EXPORT = 'EXPORT POSTGRES_DB=upper_export_db\r\nExport POSTGRES_USER=mixed_export\r\n'


@pytest.mark.Trait("Bug", "B21")
@pytest.mark.skipif(BASH is None, reason=SKIP_REASON)
@pytest.mark.parametrize('rel', SH_SCRIPTS)
def test_sh_dotenv_accepts_export_only_in_lower_case(rel, tmp_path):
    fn = _block(_read(rel), 'env_value() {')
    (tmp_path / '.env').write_bytes((_ENV_UPPER_EXPORT + 'export postgres_port=7777\r\n').encode('utf-8'))
    probe = (f'ROOT="{tmp_path.as_posix()}"\n' + fn +
             'printf "DB=[%s] USER=[%s] PORT=[%s]\n" "$(env_value POSTGRES_DB DEFAULT)" '
             '"$(env_value POSTGRES_USER DEFAULT)" "$(env_value POSTGRES_PORT DEFAULT)"\n')
    res = subprocess.run([BASH, '-c', probe], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert 'DB=[DEFAULT] USER=[DEFAULT] PORT=[7777]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B21")
@pytest.mark.skipif(_PS_EXE is None, reason='no PowerShell')
@pytest.mark.parametrize('rel', PS_SCRIPTS)
def test_ps_dotenv_accepts_export_only_in_lower_case(rel, tmp_path):
    fn = _block(_read(rel), 'function Read-DotEnv')
    (tmp_path / '.env').write_bytes((_ENV_UPPER_EXPORT + 'export postgres_port=7777\r\n').encode('utf-8'))
    script = tmp_path / 'probe.ps1'
    script.write_text("$ErrorActionPreference = 'Stop'\n" + fn +
                      f"$v = Read-DotEnv '{tmp_path / '.env'}'\n"
                      "\"DB=[$($v['POSTGRES_DB'])] USER=[$($v['POSTGRES_USER'])] PORT=[$($v['POSTGRES_PORT'])]\"\n",
                      encoding='utf-8')
    res = subprocess.run([_PS_EXE, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert 'DB=[] USER=[] PORT=[7777]' in res.stdout, res.stdout


@pytest.mark.Trait("Bug", "B21")
def test_readme_says_the_env_notes_apply_to_the_scripts_only():
    text = _read('README.md')
    section = text[text.index('#### Backup and restore'):text.index('### 3. Backend')]
    assert 'scripts only' in section, section
    assert '`EXPORT' in section and 'lower case' in section, section


# macOS ships bash 3.2 as /bin/bash: ${x^^}, ${x,,} and friends are a runtime "bad substitution"
# there (backup.sh failed inside start.sh's old-install backup). Only Git-Bash-only lines may use them.
_CASE_MODIFIER = re.compile(r'\$\{[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?(\^\^?|,,?)')


@pytest.mark.parametrize('rel', ['scripts/backup.sh', 'scripts/restore.sh', 'start.sh'])
def test_sh_scripts_avoid_bash4_case_modifiers(rel):
    bad = [l for l in _code_lines(_read(rel)) if _CASE_MODIFIER.search(l) and 'MINGW' not in l]
    assert not bad, bad
