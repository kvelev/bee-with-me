"""tools/smoke.py: engine choice, result reporting, cleanup and the command lines it builds.

The real smoke test (images, containers, network) is run by hand, never from pytest or CI. Here the
container engine is a recording fake and no socket leaves the process.
"""

import base64
import hashlib
import importlib.util
import re
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location('smoke_under_test', ROOT / 'tools' / 'smoke.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module      # dataclasses looks the module up by name
    spec.loader.exec_module(module)
    return module


smoke = _load()


class FakeEngine:
    """Records every engine command; `fail` maps a command prefix to (returncode, stderr)."""

    def __init__(self, fail=None):
        self.calls = []
        self.envs = []
        self.fail = fail or {}

    def __call__(self, cmd, *, timeout, env=None, cwd=None):
        self.calls.append(list(cmd))
        self.envs.append(env)
        for prefix, (code, err) in self.fail.items():
            if ' '.join(cmd[1:]).startswith(prefix):
                return SimpleNamespace(returncode=code, stdout='', stderr=err)
        return SimpleNamespace(returncode=0, stdout='', stderr='')


def make(fake=None, **kw):
    lines = []
    s = smoke.Smoke('podman', runner=fake or FakeEngine(), out=lines.append, run_id='abc123', **kw)
    return s, lines


# --------------------------------------------------------------------------- T200

@pytest.mark.Trait("Task", "T200")
def test_engine_order_is_override_then_podman_then_docker():
    both = {'podman': '/p', 'docker': '/d'}.get
    assert smoke.pick_engine({}, which=both) == 'podman'
    assert smoke.pick_engine({}, which={'docker': '/d'}.get) == 'docker'
    assert smoke.pick_engine({'CONTAINER_ENGINE': 'docker'}, which=both) == 'docker'
    assert smoke.pick_engine({'CONTAINER_ENGINE': ' Podman '}, which=both) == 'podman'


@pytest.mark.Trait("Task", "T200")
def test_engine_errors_are_clear():
    with pytest.raises(smoke.StepFail, match='no container engine'):
        smoke.pick_engine({}, which=lambda n: None)
    with pytest.raises(smoke.StepFail, match='podman or docker'):
        smoke.pick_engine({'CONTAINER_ENGINE': 'nerdctl'}, which=lambda n: '/x')
    with pytest.raises(smoke.StepFail, match='not on PATH'):
        smoke.pick_engine({'CONTAINER_ENGINE': 'docker'}, which={'podman': '/p'}.get)


@pytest.mark.Trait("Task", "T200")
def test_main_exits_2_without_an_engine(monkeypatch, capsys):
    monkeypatch.setattr(smoke.shutil, 'which', lambda n: None)
    monkeypatch.delenv('CONTAINER_ENGINE', raising=False)
    assert smoke.main([]) == 2
    assert 'FAIL' in capsys.readouterr().out


@pytest.mark.Trait("Task", "T200")
def test_report_lines_and_exit_code():
    r = smoke.Report()
    assert r.exit_code == 1                       # nothing ran is not a pass
    r.add('one', 'PASS', 1.0)
    assert r.exit_code == 0
    r.add('two', 'FAIL', 0.5, 'HTTP 500')
    r.add('three', 'SKIP', 0, 'needs: two')
    assert r.exit_code == 1
    assert smoke.Report.line(r.results[0]) == 'PASS  one  (1.0s)'
    assert smoke.Report.line(r.results[1]) == 'FAIL  two  (0.5s)  - HTTP 500'
    assert r.summary() == 'SMOKE FAILED: 1 passed, 1 failed, 1 skipped'


@pytest.mark.Trait("Task", "T200")
def test_step_turns_failures_timeouts_and_bugs_into_fail_lines_and_skips_dependants():
    s, lines = make()

    def boom():
        raise RuntimeError('oops')

    def slow():
        raise subprocess.TimeoutExpired('x', 5)

    assert s.step('ok', lambda: 'fine')
    assert not s.step('fail', lambda: (_ for _ in ()).throw(smoke.StepFail('nope')))
    assert not s.step('bug', boom)
    assert not s.step('slow', slow)
    assert not s.step('dependant', lambda: 'never', needs=('fail',))
    statuses = {r.name: (r.status, r.detail) for r in s.report.results}
    assert statuses['ok'][0] == 'PASS'
    assert statuses['fail'] == ('FAIL', 'nope')
    assert statuses['bug'] == ('FAIL', 'RuntimeError: oops')
    assert statuses['slow'] == ('FAIL', 'timeout after 5s')
    assert statuses['dependant'] == ('SKIP', 'needs: fail')
    assert len(lines) == 5


@pytest.mark.Trait("Task", "T200")
def test_cleanup_removes_what_was_created_and_is_idempotent():
    fake = FakeEngine()
    s, _ = make(fake)
    s.containers += [s.db_name, s.backend_name]
    s.networks.append(s.network)
    s.created_volumes += s.volumes
    assert s.cleanup() == []
    removed = [' '.join(c[1:]) for c in fake.calls]
    assert f'rm -f -v {s.db_name}' in removed and f'rm -f -v {s.backend_name}' in removed
    assert f'network rm {s.network}' in removed
    assert all(f'volume rm -f {v}' in removed for v in s.volumes)
    fake.calls.clear()
    assert s.cleanup() == []
    assert fake.calls == []                        # nothing left to remove the second time


@pytest.mark.Trait("Task", "T200")
def test_cleanup_tolerates_missing_and_reports_real_errors_without_raising():
    fake = FakeEngine(fail={'rm -f -v': (1, 'Error: no such container')})
    s, _ = make(fake)
    s.containers.append('gone')
    assert s.cleanup() == []

    def explode(cmd, *, timeout, env=None, cwd=None):
        raise OSError('engine vanished')

    s, _ = make(explode)
    s.containers.append('x')
    problems = s.cleanup()
    assert len(problems) == 1 and 'engine vanished' in problems[0]


@pytest.mark.Trait("Task", "T200")
def test_run_cleans_up_even_when_every_step_fails_and_exit_code_is_1():
    fake = FakeEngine(fail={'version': (1, 'cannot connect')})
    s, lines = make(fake)
    assert s.run() == 1
    assert any(l.startswith('FAIL  engine ready') and 'podman machine start' in l for l in lines)
    assert lines[-1].startswith('SMOKE FAILED')


@pytest.mark.Trait("Task", "T200")
def test_run_cleans_up_when_a_step_raises_keyboard_interrupt():
    fake = FakeEngine()
    s, _ = make(fake)
    s.networks.append(s.network)

    def interrupted():
        raise KeyboardInterrupt

    s.s_engine = interrupted
    with pytest.raises(KeyboardInterrupt):
        s.run()
    assert any(c[1:3] == ['network', 'rm'] for c in fake.calls)


# --------------------------------------------------------------------------- T201

def _flat(cmd):
    return ' '.join(cmd)


@pytest.mark.Trait("Task", "T201")
@pytest.mark.parametrize('component', ['backend', 'frontend'])
def test_build_uses_the_deploy_dockerfiles_with_repo_root_context(component):
    s, _ = make()
    cmd = s.build_cmd(component)
    assert cmd[:3] == ['build', '-f', f'deploy/docker/{component}.Dockerfile']
    assert cmd[-1] == '.'
    assert cmd[cmd.index('-t') + 1].endswith(':smoke-local')
    assert (ROOT / f'deploy/docker/{component}.Dockerfile').is_file()


@pytest.mark.Trait("Task", "T201")
def test_build_runs_in_the_repo_root_through_the_engine():
    seen = {}

    def runner(cmd, *, timeout, env=None, cwd=None):
        seen.update(cmd=cmd, cwd=cwd, timeout=timeout)
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    s, _ = make(runner)
    s.s_build('backend')
    assert seen['cmd'][0] == 'podman' and seen['cwd'] == smoke.REPO_ROOT and seen['timeout'] >= 600


@pytest.mark.Trait("Task", "T201")
def test_build_failure_is_a_fail_with_the_tail_and_no_secret():
    s, _ = make(FakeEngine(fail={'build': (1, 'step 4 failed ' + 'x' * 900)}))
    s.secrets['SECRET_KEY'] = 'xxxxxxxx'
    with pytest.raises(smoke.StepFail) as err:
        s.s_build('backend')
    assert 'exit 1' in str(err.value) and len(str(err.value)) < 700


@pytest.mark.Trait("Task", "T201")
def test_ports_are_published_on_loopback_only():
    s, _ = make()
    for cmd in (s.backend_run_cmd(), s.frontend_run_cmd()):
        ports = [cmd[i + 1] for i, a in enumerate(cmd) if a == '-p']
        assert ports and all(p.startswith('127.0.0.1:') for p in ports)
    assert '-p' not in s.db_run_cmd()               # the database is reachable on the private network only


@pytest.mark.Trait("Task", "T201")
def test_backend_env_follows_the_k8s_configmap_and_has_no_bind_mount():
    s, _ = make()
    cmd = s.backend_run_cmd()
    flat = _flat(cmd)
    for expected in ('POSTGRES_HOST=postgres', 'POSTGRES_PORT=5432', 'POSTGRES_DB=rescuer_locator',
                     'POSTGRES_USER=rescuer', 'ALLOW_MIGRATE_WITHOUT_BACKUP=true', 'ENABLE_TEST_ENDPOINTS=true',
                     '--read-only', '--cap-drop ALL', 'no-new-privileges'):
        assert expected in flat
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == '-v']
    assert mounts and all(not re.match(r'^([A-Za-z]:|[/.~])', m) for m in mounts)   # named volumes only
    for db_mount in [s.db_run_cmd()[i + 1] for i, a in enumerate(s.db_run_cmd()) if a == '-v']:
        assert not db_mount.startswith(('/', '.', '~')) and not re.match(r'^[A-Za-z]:', db_mount)
    k8s = (ROOT / 'deploy/k8s/app/backend.yaml').read_text(encoding='utf-8')
    for key in ('POSTGRES_HOST: postgres', 'POSTGRES_DB: rescuer_locator', 'POSTGRES_USER: rescuer',
                'ENABLE_TEST_ENDPOINTS: "true"', 'ALLOW_MIGRATE_WITHOUT_BACKUP: "true"'):
        assert key in k8s                           # the mirrored values still exist upstream


@pytest.mark.Trait("Task", "T201")
def test_secrets_never_appear_on_a_command_line_and_reach_the_engine_by_environment():
    fake = FakeEngine()
    s, _ = make(fake)
    s.s_database()
    s.eng_ok(*s.backend_run_cmd(), env=s.secret_env())
    values = list(s.secrets.values())
    assert all(len(v) >= 16 for v in values)
    for call in fake.calls:
        assert not any(v in part for v in values for part in call)
    run_envs = [e for c, e in zip(fake.calls, fake.envs) if c[1] == 'run']
    assert run_envs and all(e and e['INITIAL_ADMIN_PASSWORD'] == s.secrets['INITIAL_ADMIN_PASSWORD'] for e in run_envs)
    flat = _flat(s.backend_run_cmd())
    assert '-e INITIAL_ADMIN_PASSWORD ' in flat + ' ' and '-e POSTGRES_PASSWORD ' in flat + ' '


@pytest.mark.Trait("Task", "T201")
def test_secrets_are_redacted_from_reports_and_are_new_every_run():
    a, _ = make()
    b, _ = make()
    assert a.secrets['SECRET_KEY'] != b.secrets['SECRET_KEY']
    leaked = f"error with {a.secrets['INITIAL_ADMIN_PASSWORD']} inside"
    assert a.secrets['INITIAL_ADMIN_PASSWORD'] not in a.redact(leaked)
    a.step('leaky', lambda: (_ for _ in ()).throw(smoke.StepFail(leaked)))
    assert a.secrets['INITIAL_ADMIN_PASSWORD'] not in a.report.results[0].detail


@pytest.mark.Trait("Task", "T201")
def test_mapped_port_parses_engine_output():
    def runner(cmd, *, timeout, env=None, cwd=None):
        return SimpleNamespace(returncode=0, stdout='127.0.0.1:34567\n', stderr='')

    s, _ = make(runner)
    assert s.mapped_port('c', 8000) == 34567

    def empty(cmd, *, timeout, env=None, cwd=None):
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    s, _ = make(empty)
    with pytest.raises(smoke.StepFail):
        s.mapped_port('c', 8000)


@pytest.mark.Trait("Task", "T201")
def test_http_helper_returns_non_2xx_and_maps_connection_errors_to_fail(monkeypatch):
    import urllib.error

    def raise_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, 'no', {}, None)

    monkeypatch.setattr(smoke._OPENER, 'open', raise_http)
    assert smoke.http_request('GET', 'http://127.0.0.1:1/x')[0] == 401

    def refuse(req, timeout):
        raise urllib.error.URLError(ConnectionRefusedError('refused'))

    monkeypatch.setattr(smoke._OPENER, 'open', refuse)
    with pytest.raises(smoke.StepFail, match='failed'):
        smoke.http_request('GET', 'http://127.0.0.1:1/x')

    with pytest.raises(smoke.StepFail, match='expected HTTP 200, got 500'):
        smoke.expect_status(500, 200, 'GET /health')


@pytest.mark.Trait("Task", "T201")
def test_backend_that_exits_during_startup_fails_with_its_logs(monkeypatch):
    class Dead(FakeEngine):
        def __call__(self, cmd, *, timeout, env=None, cwd=None):
            self.calls.append(list(cmd))
            if cmd[1] == 'port':
                return SimpleNamespace(returncode=0, stdout='127.0.0.1:40000\n', stderr='')
            if cmd[1] == 'inspect':
                return SimpleNamespace(returncode=0, stdout='false\n', stderr='')
            if cmd[1] == 'logs':
                return SimpleNamespace(returncode=0, stdout='', stderr='RuntimeError: migration 0003 failed')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

    s, _ = make(Dead())
    with pytest.raises(smoke.StepFail, match='migration 0003 failed'):
        s.s_backend_start()


@pytest.mark.Trait("Task", "T201")
def test_database_step_waits_on_tcp_not_the_init_socket():
    fake = FakeEngine()
    s, _ = make(fake)
    s.s_database()
    ready = [c for c in fake.calls if 'pg_isready' in c][0]
    assert '-h' in ready and ready[ready.index('-h') + 1] == '127.0.0.1'
    assert 'PGDATA=/var/lib/postgresql/data/pgdata' in s.db_run_cmd()


# --------------------------------------------------------------------------- T202

@pytest.mark.Trait("Task", "T202")
def test_ws_accept_key_matches_the_rfc_example():
    assert smoke.ws_accept_key('dGhlIHNhbXBsZSBub25jZQ==') == 's3pPLMBiTxaQ9kYGzzhZRbK+xOo='


@pytest.mark.Trait("Task", "T202")
@pytest.mark.parametrize('size', [0, 5, 125, 126, 300, 65535, 65536])
def test_client_frames_are_masked_and_carry_the_right_length(size):
    payload = bytes(range(256)) * (size // 256 + 1)
    payload = payload[:size]
    frame = smoke.ws_encode_frame(0x1, payload, mask_key=b'\x01\x02\x03\x04')
    assert frame[0] == 0x81 and frame[1] & 0x80
    n = frame[1] & 0x7F
    offset = 2
    if n == 126:
        n, offset = struct.unpack('>H', frame[2:4])[0], 4
    elif n == 127:
        n, offset = struct.unpack('>Q', frame[2:10])[0], 10
    assert n == size
    key = frame[offset:offset + 4]
    body = bytes(b ^ key[i % 4] for i, b in enumerate(frame[offset + 4:]))
    assert body == payload


class FakeSock:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []

    def recv(self, n):
        return self.chunks.pop(0) if self.chunks else b''

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, t):
        pass

    def close(self):
        pass


def _client(chunks):
    c = object.__new__(smoke.WebSocketClient)
    c.sock = FakeSock(chunks)
    c._buf = b''
    return c


def _server_frame(opcode, payload, fin=True):
    head = bytes([(0x80 if fin else 0) | opcode])
    n = len(payload)
    head += bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n)
    return head + payload


@pytest.mark.Trait("Task", "T202")
def test_recv_text_joins_fragments_and_answers_pings():
    c = _client([_server_frame(0x9, b'hi'), _server_frame(0x1, b'{"a":', fin=False) + _server_frame(0x0, b'1}')])
    assert c.recv_text() == '{"a":1}'
    assert c.sock.sent and c.sock.sent[0][0] == 0x8A     # pong, masked


@pytest.mark.Trait("Task", "T202")
def test_recv_text_reads_a_126_length_frame_and_fails_on_close():
    big = b'x' * 300
    assert _client([_server_frame(0x1, big)]).recv_text() == big.decode()
    with pytest.raises(smoke.StepFail, match='closed'):
        _client([_server_frame(0x8, b'')]).recv_text()


@pytest.mark.Trait("Task", "T202")
def test_wait_for_message_matches_the_device_and_skips_noise():
    msgs = [b'not json', b'{"type":"sos_alert","device_id":"d1"}', b'{"type":"location_update","device_id":"d1"}']
    c = _client([_server_frame(0x1, m) for m in msgs])
    got = smoke.wait_for_message(c, lambda m: m.get('type') == 'location_update' and m.get('device_id') == 'd1', timeout=2)
    assert got['type'] == 'location_update'


@pytest.mark.Trait("Task", "T202")
def test_wait_for_message_times_out_as_a_fail():
    c = _client([])
    with pytest.raises(smoke.StepFail):
        smoke.wait_for_message(c, lambda m: True, timeout=1)


@pytest.mark.Trait("Task", "T202")
def test_html_check_requires_the_app_mount_point():
    assert smoke.check_html(b'<html><body><div id="app"></div></body></html>')
    with pytest.raises(smoke.StepFail, match='no <div id="app">'):
        smoke.check_html(b'<html>nginx welcome</html>')


@pytest.mark.Trait("Task", "T202")
def test_the_frontend_index_really_has_the_mount_point():
    html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert smoke.check_html(html.encode())


@pytest.mark.Trait("Task", "T202")
def test_test_endpoint_and_ws_message_shape_match_the_checks():
    src = (ROOT / 'backend/routers/test.py').read_text(encoding='utf-8')
    assert "prefix='/api/test'" in src and "'/simulate'" in src
    # T541: the message is built by tracking.api.location_update_payload (domain/payload.py), not inline
    assert 'tracking_api.location_update_payload(' in src
    payload_src = (ROOT / 'backend/modules/tracking/domain/payload.py').read_text(encoding='utf-8')
    assert "'device_id':" in payload_src
    ws = (ROOT / 'backend/core/ws.py').read_text(encoding='utf-8')
    assert "'type': channel" in ws and "'location_update'" in ws


# --------------------------------------------------------------------------- T590: LIVE_PERSONAL_FIELDS switch

@pytest.mark.Trait("Task", "T590")
def test_the_switch_is_not_passed_by_default_and_changes_nothing_else():
    default, _ = make()
    assert 'LIVE_PERSONAL_FIELDS' not in _flat(default.backend_run_cmd())
    for value, text in ((False, 'false'), (True, 'true')):
        s, _ = make(live_personal_fields=value)
        cmd = s.backend_run_cmd()
        assert f'-e LIVE_PERSONAL_FIELDS={text} ' in _flat(cmd) + ' '
        rest = [a for i, a in enumerate(cmd)
                if not a.startswith('LIVE_PERSONAL_FIELDS=') and not (a == '-e' and cmd[i + 1].startswith('LIVE_PERSONAL_FIELDS='))]
        assert rest == default.backend_run_cmd()


@pytest.mark.Trait("Task", "T590")
def test_the_switch_does_not_change_the_steps():
    names = []
    for value in (None, False, True):
        s, _ = make(FakeEngine(fail={'version': (1, 'cannot connect')}), live_personal_fields=value)
        s.run()
        names.append([r.name for r in s.report.results])
    assert names[0] == names[1] == names[2] and len(names[0]) == 15


@pytest.mark.Trait("Task", "T590")
def test_step_e_checks_the_message_against_the_switch_and_reports_no_value():
    thin = {'type': 'location_update', 'device_id': 7, 'latitude': 42.7}
    full = {**thin, 'full_name': 'Ivan Petrov', 'phone': '+359888123456'}
    assert smoke.personal_fields_note(full, None) == '' and smoke.personal_fields_note(thin, None) == ''
    assert 'thin message, 2 keys, LIVE_PERSONAL_FIELDS=false' in smoke.personal_fields_note(thin, False)
    note = smoke.personal_fields_note(full, True)
    assert 'full message, 4 keys, LIVE_PERSONAL_FIELDS=true' in note
    assert 'Ivan' not in note and '+359' not in note
    with pytest.raises(smoke.StepFail, match='carries the personal keys') as err:
        smoke.personal_fields_note(full, False)
    assert 'Ivan' not in str(err.value) and '+359' not in str(err.value)
    with pytest.raises(smoke.StepFail, match='lacks the personal keys'):
        smoke.personal_fields_note(thin, True)
    # the key the check looks for is a key of the personal part, and of nothing else
    payload_src = (ROOT / 'backend/modules/tracking/domain/payload.py').read_text(encoding='utf-8')
    fix, personal = payload_src.split('class PersonalDetails')
    assert 'full_name:' in personal and 'full_name:' not in fix.split('class PositionFix')[1]


@pytest.mark.Trait("Task", "T590")
@pytest.mark.parametrize('argv, expected', [([], None), (['--live-personal-fields', 'false'], False),
                                             (['--live-personal-fields', 'true'], True)])
def test_main_hands_the_switch_to_the_run(monkeypatch, capsys, argv, expected):
    seen = {}

    class FakeSmoke:
        def __init__(self, engine, **kw):
            seen.update(kw)

        def run(self):
            return 0

    monkeypatch.setattr(smoke, 'Smoke', FakeSmoke)
    monkeypatch.setattr(smoke, 'pick_engine', lambda env: 'podman')
    monkeypatch.setattr(smoke, 'git_label', lambda: 'abc1234')
    assert smoke.main(argv) == 0
    assert seen['live_personal_fields'] is expected
    header = capsys.readouterr().out
    assert ('LIVE_PERSONAL_FIELDS' in header) == (expected is not None)
    with pytest.raises(SystemExit):
        smoke.main(['--live-personal-fields', 'maybe'])

# --------------------------------------------------------------------------- T203

@pytest.mark.Trait("Task", "T203")
@pytest.mark.parametrize('rel', ['tools/smoke.ps1', 'tools/smoke.sh', 'tools/smoke.py'])
def test_no_hard_coded_docker_calls(rel):
    text = (ROOT / rel).read_text(encoding='utf-8')
    assert not re.search(r'^\s*docker\s+(run|build|exec|rm|ps|compose|info|network|volume)\b', text, re.MULTILINE)
    assert 'subprocess.run(["docker"' not in text and "subprocess.run(['docker'" not in text


@pytest.mark.Trait("Task", "T203")
def test_wrappers_pass_arguments_and_the_exit_code_to_smoke_py():
    ps1 = (ROOT / 'tools/smoke.ps1').read_text(encoding='utf-8')
    sh = (ROOT / 'tools/smoke.sh').read_text(encoding='utf-8')
    assert 'smoke.py' in ps1 and '@args' in ps1 and 'exit $LASTEXITCODE' in ps1
    assert 'smoke.py' in sh and '"$@"' in sh and 'exec ' in sh
    assert sh.startswith('#!')


@pytest.mark.Trait("Task", "T203")
def test_smoke_docs_cover_every_step_and_both_engines():
    doc = (ROOT / 'docs/SMOKE.md').read_text(encoding='utf-8')
    for needle in ('podman', 'docker', 'CONTAINER_ENGINE', 'PASS', 'FAIL', 'smoke.ps1', 'smoke.sh',
                   'migrations', '/health', 'refresh', '/api/locations/live', '/ws', '<div id="app">',
                   'not checked', 'smoke-local'):
        assert needle.lower() in doc.lower(), needle


@pytest.mark.Trait("Task", "T203")
def test_pytest_and_ci_do_not_run_the_real_smoke():
    ci = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert 'smoke.py' not in ci
    assert not [n for n in dir(smoke) if n.startswith('test_')]


# --------------------------------------------------------------------------- T204

@pytest.mark.Trait("Task", "T204")
def test_smoke_doc_records_a_verified_run():
    doc = (ROOT / 'docs/SMOKE.md').read_text(encoding='utf-8')
    m = re.search(r'Last verified run[^\n]*', doc)
    assert m, 'add a "Last verified run" line'
    line = m.group(0)
    assert re.search(r'\b[0-9a-f]{7,40}\b', line) and 'PASS' in line


@pytest.mark.Trait("Task", "T201")
def test_http_helper_bypasses_proxies_so_credentials_stay_on_the_host(monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://proxy.invalid:3128')
    monkeypatch.setenv('http_proxy', 'http://proxy.invalid:3128')
    # an empty ProxyHandler({}) registers no handler methods; the default one (reads HTTP_PROXY) must be absent
    assert 'ProxyHandler' not in [type(h).__name__ for h in smoke._OPENER.handlers]


# --------------------------------------------------------------------------- T400

def _settings_step(monkeypatch, status, body):
    s, _ = make()
    s.ctx['api'] = 'http://127.0.0.1:1'
    s.ctx['token'] = 'tok'
    seen = []

    def fake(method, url, **kw):
        seen.append((method, url, kw.get('token')))
        return status, body

    monkeypatch.setattr(smoke, 'http_request', fake)
    return s, seen


@pytest.mark.Trait("Task", "T400")
def test_settings_step_passes_on_200_with_a_settings_row(monkeypatch):
    s, seen = _settings_step(monkeypatch, 200, b'{"hq_radius_m": 5000}')
    assert s.step('g. GET /api/settings = 200', s.s_settings)
    assert seen == [('GET', 'http://127.0.0.1:1/api/settings', 'tok')]
    assert s.report.results[-1].status == 'PASS'


@pytest.mark.Trait("Task", "T400")
def test_settings_step_fails_on_503(monkeypatch):
    s, _ = _settings_step(monkeypatch, 503, b'')
    assert not s.step('g. GET /api/settings = 200', s.s_settings)
    last = s.report.results[-1]
    assert last.status == 'FAIL' and 'GET /api/settings' in last.detail


# --------------------------------------------------------------------------- T520

@pytest.mark.Trait("Task", "T520")
@pytest.mark.parametrize('status', [200, 502, 503])
def test_weather_step_passes_on_503_and_on_200(monkeypatch, status):
    s, seen = _settings_step(monkeypatch, status, b'')
    assert s.step('i. GET /api/weather/current is served', s.s_weather)
    assert seen == [('GET', 'http://127.0.0.1:1/api/weather/current?lat=42.7&lon=23.3', 'tok')]
    assert s.report.results[-1].status == 'PASS'


@pytest.mark.Trait("Task", "T520")
def test_weather_step_fails_on_401(monkeypatch):
    s, _ = _settings_step(monkeypatch, 401, b'')
    assert not s.step('i. GET /api/weather/current is served', s.s_weather)
    last = s.report.results[-1]
    assert last.status == 'FAIL' and '/api/weather/current' in last.detail and '401' in last.detail


# --------------------------------------------------------------------------- T502

@pytest.mark.Trait("Task", "T502")
def test_fire_step_passes_on_200_with_feeds(monkeypatch):
    s, seen = _settings_step(monkeypatch, 200, b'{"feeds": []}')
    assert s.step('h. GET /api/fire/status = 200', s.s_fire)
    assert seen == [('GET', 'http://127.0.0.1:1/api/fire/status', 'tok')]
    assert s.report.results[-1].status == 'PASS'


@pytest.mark.Trait("Task", "T502")
def test_fire_step_fails_on_500(monkeypatch):
    s, _ = _settings_step(monkeypatch, 500, b'')
    assert not s.step('h. GET /api/fire/status = 200', s.s_fire)
    last = s.report.results[-1]
    assert last.status == 'FAIL' and '/api/fire/status' in last.detail


# --------------------------------------------------------------------------- T540

@pytest.mark.Trait("Task", "T540")
def test_sos_step_passes_on_200_with_a_list(monkeypatch):
    s, seen = _settings_step(monkeypatch, 200, b'[]')
    assert s.step('j. GET /api/locations/sos = 200', s.s_sos)
    assert seen == [('GET', 'http://127.0.0.1:1/api/locations/sos', 'tok')]
    assert s.report.results[-1].status == 'PASS'


@pytest.mark.Trait("Task", "T540")
def test_sos_step_fails_on_500(monkeypatch):
    s, _ = _settings_step(monkeypatch, 500, b'')
    assert not s.step('j. GET /api/locations/sos = 200', s.s_sos)
    last = s.report.results[-1]
    assert last.status == 'FAIL' and '/api/locations/sos' in last.detail
