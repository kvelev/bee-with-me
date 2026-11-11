#!/usr/bin/env python3
"""
Local smoke test for the develop images.

Builds deploy/docker/backend.Dockerfile and frontend.Dockerfile (context = repository root, the same as
.github/workflows/deploy-develop.yml), runs them against an empty throw-away PostGIS and checks the basics.
Every PR into `develop` should pass this before merge: a merge deploys to bee-dev for human testers.

Usage:
    python tools/smoke.py                  # Podman first, Docker second (or CONTAINER_ENGINE=podman|docker)
    python tools/smoke.py --no-build       # reuse the smoke-local images from an earlier run
    python tools/smoke.py --engine docker

Exit code: 0 all steps PASS, 1 at least one FAIL, 2 no usable container engine.

Standard library only. Never reads or writes a .env file, never touches data/, tiles/ or backend/uploads/:
the database and the backend's writable folders live in named volumes that are removed at the end.
Passwords are generated per run and handed to the containers through the environment of the engine
process (`-e NAME`, no value on the command line); they are never printed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_TAG = 'smoke-local'
BACKEND_IMAGE = f'bee-with-me-backend:{IMAGE_TAG}'
FRONTEND_IMAGE = f'bee-with-me-frontend:{IMAGE_TAG}'
# Fully qualified: Podman does not resolve short names without a configured registry
POSTGIS_IMAGE = 'docker.io/postgis/postgis:16-3.4'

# Values of deploy/k8s/app/backend.yaml (ConfigMap) and postgres.yaml
DB_NAME = 'rescuer_locator'
DB_USER = 'rescuer'

BUILD_TIMEOUT = 1800
RUN_TIMEOUT = 900          # includes pulling the PostGIS image
STARTUP_TIMEOUT = 180      # migrations on an empty database + app start
HTTP_TIMEOUT = 20
WS_TIMEOUT = 20


class StepFail(Exception):
    """A check did not hold; the message is the one-line reason shown after FAIL."""


# --------------------------------------------------------------------------- engine

def pick_engine(env=None, which=None) -> str:
    """CONTAINER_ENGINE (podman|docker) -> podman -> docker. Raises StepFail when none is usable."""
    env = os.environ if env is None else env
    which = which or shutil.which
    override = (env.get('CONTAINER_ENGINE') or '').strip().lower()
    if override:
        if override not in ('podman', 'docker'):
            raise StepFail(f'CONTAINER_ENGINE must be podman or docker, got {override!r}')
        if not which(override):
            raise StepFail(f'CONTAINER_ENGINE={override} but {override} is not on PATH')
        return override
    for name in ('podman', 'docker'):
        if which(name):
            return name
    raise StepFail('no container engine found: install Podman (or Docker) or set CONTAINER_ENGINE')


# --------------------------------------------------------------------------- report

@dataclass
class StepResult:
    name: str
    status: str            # PASS | FAIL | SKIP
    seconds: float = 0.0
    detail: str = ''


@dataclass
class Report:
    results: list = field(default_factory=list)

    def add(self, name: str, status: str, seconds: float = 0.0, detail: str = '') -> None:
        self.results.append(StepResult(name, status, seconds, detail))

    def status_of(self, name: str) -> str | None:
        for r in self.results:
            if r.name == name:
                return r.status
        return None

    @staticmethod
    def line(r: StepResult) -> str:
        text = f'{r.status:<4}  {r.name}  ({r.seconds:.1f}s)'
        return f'{text}  - {r.detail}' if r.detail else text

    @property
    def exit_code(self) -> int:
        return 0 if self.results and all(r.status == 'PASS' for r in self.results) else 1

    def summary(self) -> str:
        counts = {s: sum(1 for r in self.results if r.status == s) for s in ('PASS', 'FAIL', 'SKIP')}
        verdict = 'SMOKE PASSED' if self.exit_code == 0 else 'SMOKE FAILED'
        return f"{verdict}: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped"


# --------------------------------------------------------------------------- http + websocket (stdlib)

# No proxies: urllib would send the admin password and tokens to HTTP_PROXY / the Windows system proxy
# even for 127.0.0.1
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_request(method: str, url: str, *, token: str | None = None, json_body=None, form=None,
                 timeout: float = HTTP_TIMEOUT) -> tuple[int, bytes]:
    """One HTTP call; returns (status, body). A non-2xx status is returned, not raised."""
    headers = {}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers['Content-Type'] = 'application/json'
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise StepFail(f'{method} {url} failed: {getattr(exc, "reason", exc)}') from exc


def expect_status(status: int, want: int, what: str) -> None:
    if status != want:
        raise StepFail(f'{what}: expected HTTP {want}, got {status}')


WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def ws_accept_key(client_key: str) -> str:
    return base64.b64encode(hashlib.sha1((client_key + WS_GUID).encode()).digest()).decode()


def ws_encode_frame(opcode: int, payload: bytes, mask_key: bytes | None = None) -> bytes:
    """A single final client frame (clients must mask, RFC 6455 section 5.3)."""
    mask_key = os.urandom(4) if mask_key is None else mask_key
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack('>H', n)
    else:
        head += bytes([0x80 | 127]) + struct.pack('>Q', n)
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return head + mask_key + masked


class WebSocketClient:
    """Just enough RFC 6455 to read the text messages /ws broadcasts."""

    def __init__(self, host: str, port: int, path: str = '/ws', timeout: float = WS_TIMEOUT):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f'GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n'
                   f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(request.encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise StepFail('WebSocket handshake: connection closed')
            buf += chunk
        head, _, self._buf = buf.partition(b'\r\n\r\n')
        lines = head.decode('latin-1').split('\r\n')
        if ' 101 ' not in lines[0]:
            raise StepFail(f'WebSocket handshake refused: {lines[0]}')
        headers = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(':') for ln in lines[1:])}
        if headers.get('sec-websocket-accept') != ws_accept_key(key):
            raise StepFail('WebSocket handshake: wrong Sec-WebSocket-Accept')

    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise StepFail('WebSocket closed by the server')
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv_text(self) -> str:
        """Next complete text message; answers pings, fails on close."""
        message = b''
        while True:
            b0, b1 = self._read(2)
            opcode, length = b0 & 0x0F, b1 & 0x7F
            if length == 126:
                length = struct.unpack('>H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._read(8))[0]
            payload = self._read(length)       # server frames are not masked
            if opcode == 0x9:
                self.sock.sendall(ws_encode_frame(0xA, payload))
            elif opcode == 0x8:
                raise StepFail('WebSocket closed by the server')
            elif opcode in (0x1, 0x0):
                message += payload
                if b0 & 0x80:
                    return message.decode('utf-8')

    def close(self) -> None:
        try:
            self.sock.sendall(ws_encode_frame(0x8, b''))
        except OSError:
            pass
        self.sock.close()


def wait_for_message(client, match, timeout: float = WS_TIMEOUT):
    """Read messages until `match(dict)` is true; StepFail on timeout. Non-JSON messages are skipped."""
    deadline = time.monotonic() + timeout
    client.sock.settimeout(timeout)
    while time.monotonic() < deadline:
        client.sock.settimeout(max(0.5, deadline - time.monotonic()))
        try:
            text = client.recv_text()
        except (socket.timeout, TimeoutError):
            break
        try:
            msg = json.loads(text)
        except ValueError:
            continue
        if isinstance(msg, dict) and match(msg):
            return msg
    raise StepFail(f'no matching WebSocket message within {timeout:.0f}s')


# --------------------------------------------------------------------------- runner

def default_runner(cmd, *, timeout, env=None, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd, check=False)


class Smoke:
    """Owns the containers, network and volumes of one run; `cleanup()` removes exactly those."""

    def __init__(self, engine: str, *, runner=default_runner, repo_root: Path = REPO_ROOT,
                 no_build: bool = False, out=print, run_id: str | None = None):
        self.engine = engine
        self.runner = runner
        self.repo_root = Path(repo_root)
        self.no_build = no_build
        self.out = out
        self.run_id = run_id or secrets.token_hex(3)
        self.prefix = f'bee-smoke-{self.run_id}'
        self.network = f'{self.prefix}-net'
        self.db_name = f'{self.prefix}-db'
        self.backend_name = f'{self.prefix}-backend'
        self.frontend_name = f'{self.prefix}-frontend'
        self.volumes = [f'{self.prefix}-pgdata', f'{self.prefix}-uploads', f'{self.prefix}-tiles']
        self.containers: list[str] = []
        self.networks: list[str] = []
        self.created_volumes: list[str] = []
        self.report = Report()
        # Generated per run, passed to the engine process environment only
        self.secrets = {
            'POSTGRES_PASSWORD': secrets.token_urlsafe(18),
            'SECRET_KEY': secrets.token_urlsafe(36),
            'OFFLINE_MAPS_PASSWORD': secrets.token_urlsafe(18),
            'INITIAL_ADMIN_PASSWORD': secrets.token_urlsafe(18),
        }
        self.ctx: dict = {}

    # -- helpers
    def redact(self, text: str) -> str:
        for value in self.secrets.values():
            text = text.replace(value, '***')
        return text

    def eng(self, *args: str, timeout: float = 60, env: dict | None = None):
        return self.runner([self.engine, *args], timeout=timeout, env=env)

    def eng_ok(self, *args: str, timeout: float = 60, env: dict | None = None):
        proc = self.eng(*args, timeout=timeout, env=env)
        if proc.returncode != 0:
            tail = self.redact((proc.stderr or proc.stdout or '').strip())[-400:]
            raise StepFail(f'{self.engine} {args[0]} exit {proc.returncode}: {tail}')
        return proc

    def step(self, name: str, fn, needs: tuple = ()) -> bool:
        blocked = [n for n in needs if self.report.status_of(n) != 'PASS']
        if blocked:
            self.report.add(name, 'SKIP', 0.0, f'needs: {blocked[0]}')
            self.out(Report.line(self.report.results[-1]))
            return False
        started = time.monotonic()
        try:
            detail = fn() or ''
            status = 'PASS'
        except StepFail as exc:
            status, detail = 'FAIL', str(exc)
        except subprocess.TimeoutExpired as exc:
            status, detail = 'FAIL', f'timeout after {exc.timeout:.0f}s'
        except Exception as exc:    # a bug in the script must still end as a FAIL line, then cleanup
            status, detail = 'FAIL', f'{type(exc).__name__}: {exc}'
        self.report.add(name, status, time.monotonic() - started, self.redact(detail))
        self.out(Report.line(self.report.results[-1]))
        return status == 'PASS'

    def secret_env(self) -> dict:
        return {**os.environ, **self.secrets}

    # -- cleanup
    def cleanup(self) -> list[str]:
        """Remove everything this run created. Never raises; returns the problems found."""
        problems = []
        for kind, items, args in (('container', self.containers, ('rm', '-f', '-v')),
                                  ('network', self.networks, ('network', 'rm')),
                                  ('volume', self.created_volumes, ('volume', 'rm', '-f'))):
            for item in list(items):
                try:
                    proc = self.eng(*args, item, timeout=60)
                    if proc.returncode != 0 and not any(m in (proc.stderr or '').lower() for m in ('no such', 'not found')):
                        problems.append(f'{kind} {item}: {(proc.stderr or "").strip()[:200]}')
                    else:
                        items.remove(item)
                except Exception as exc:
                    problems.append(f'{kind} {item}: {type(exc).__name__}: {exc}')
        return problems

    # -- container commands (built here so tests can read them)
    def build_cmd(self, component: str) -> list[str]:
        image = BACKEND_IMAGE if component == 'backend' else FRONTEND_IMAGE
        return ['build', '-f', f'deploy/docker/{component}.Dockerfile', '-t', image, '.']

    def db_run_cmd(self) -> list[str]:
        return ['run', '-d', '--name', self.db_name, '--network', self.network, '--network-alias', 'postgres',
                '-e', f'POSTGRES_DB={DB_NAME}', '-e', f'POSTGRES_USER={DB_USER}', '-e', 'POSTGRES_PASSWORD',
                '-e', 'PGDATA=/var/lib/postgresql/data/pgdata',
                '-v', f'{self.volumes[0]}:/var/lib/postgresql/data', POSTGIS_IMAGE]

    def backend_run_cmd(self) -> list[str]:
        # Mirrors deploy/k8s/app/backend.yaml: ConfigMap values, read-only root, no capabilities, /tmp writable
        return ['run', '-d', '--name', self.backend_name, '--network', self.network,
                '-p', '127.0.0.1::8000',
                '--read-only', '--tmpfs', '/tmp:rw,size=256m', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges',
                '-e', 'POSTGRES_HOST=postgres', '-e', 'POSTGRES_PORT=5432',
                '-e', f'POSTGRES_DB={DB_NAME}', '-e', f'POSTGRES_USER={DB_USER}',
                '-e', 'ALLOW_MIGRATE_WITHOUT_BACKUP=true', '-e', 'ENABLE_TEST_ENDPOINTS=true',
                '-e', 'POSTGRES_PASSWORD', '-e', 'SECRET_KEY', '-e', 'OFFLINE_MAPS_PASSWORD',
                '-e', 'INITIAL_ADMIN_PASSWORD',
                '-v', f'{self.volumes[1]}:/app/backend/uploads', '-v', f'{self.volumes[2]}:/app/tiles',
                BACKEND_IMAGE]

    def frontend_run_cmd(self) -> list[str]:
        return ['run', '-d', '--name', self.frontend_name, '-p', '127.0.0.1::8080', FRONTEND_IMAGE]

    def mapped_port(self, container: str, container_port: int) -> int:
        out = self.eng_ok('port', container, f'{container_port}/tcp').stdout
        for line in out.splitlines():
            host_port = line.strip().rsplit(':', 1)[-1]
            if host_port.isdigit():
                return int(host_port)
        raise StepFail(f'no published port for {container}:{container_port}')

    def log_tail(self, container: str, lines: int = 12) -> str:
        proc = self.eng('logs', '--tail', str(lines), container, timeout=30)
        text = self.redact(((proc.stdout or '') + (proc.stderr or '')).strip())
        return ' | '.join(text.splitlines()[-lines:])[-700:]

    def is_running(self, container: str) -> bool:
        proc = self.eng('inspect', '-f', '{{.State.Running}}', container, timeout=30)
        return proc.returncode == 0 and proc.stdout.strip() == 'true'

    # -- steps
    def s_engine(self):
        proc = self.eng('version', timeout=60)
        if proc.returncode != 0:
            hint = ' (start it with: podman machine start)' if self.engine == 'podman' else ''
            raise StepFail(f'{self.engine} is not responding{hint}')
        return self.engine

    def s_build(self, component: str):
        image = BACKEND_IMAGE if component == 'backend' else FRONTEND_IMAGE
        if self.no_build:
            self.eng_ok('image', 'inspect', image)
            return 'reused existing image'
        # context = repository root, like deploy-develop.yml
        proc = self.runner([self.engine, *self.build_cmd(component)], timeout=BUILD_TIMEOUT, cwd=self.repo_root)
        if proc.returncode != 0:
            tail = self.redact(((proc.stderr or '') + (proc.stdout or '')).strip())[-500:]
            raise StepFail(f'build {component} exit {proc.returncode}: {tail}')
        return f'tag {IMAGE_TAG}'

    def s_database(self):
        self.networks.append(self.network)
        self.eng_ok('network', 'create', self.network)
        for vol in self.volumes:
            self.created_volumes.append(vol)
            self.eng_ok('volume', 'create', vol)
        self.containers.append(self.db_name)
        self.eng_ok(*self.db_run_cmd(), timeout=RUN_TIMEOUT, env=self.secret_env())
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            # -h 127.0.0.1: initdb's temporary server listens on the socket only, the final one on TCP
            proc = self.eng('exec', self.db_name, 'pg_isready', '-h', '127.0.0.1', '-U', DB_USER, '-d', DB_NAME,
                            timeout=30)
            if proc.returncode == 0:
                return 'empty PostGIS 16 ready'
            time.sleep(2)
        raise StepFail(f'database not ready in 120s: {self.log_tail(self.db_name)}')

    def s_backend_start(self):
        self.containers.append(self.backend_name)
        self.eng_ok(*self.backend_run_cmd(), timeout=RUN_TIMEOUT, env=self.secret_env())
        port = self.mapped_port(self.backend_name, 8000)
        self.ctx['api'] = f'http://127.0.0.1:{port}'
        self.ctx['api_port'] = port
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if not self.is_running(self.backend_name):
                raise StepFail(f'backend exited during start-up (migrations?): {self.log_tail(self.backend_name)}')
            try:
                status, _ = http_request('GET', f"{self.ctx['api']}/health", timeout=5)
                if status == 200:
                    return 'migrations applied, app up'
            except StepFail:
                pass
            time.sleep(2)
        raise StepFail(f'/health not up in {STARTUP_TIMEOUT}s: {self.log_tail(self.backend_name)}')

    def s_health(self):
        status, body = http_request('GET', f"{self.ctx['api']}/health")
        expect_status(status, 200, 'GET /health')
        return ''

    def s_login(self):
        api = self.ctx['api']
        status, body = http_request('POST', f'{api}/api/auth/login',
                                    form={'username': 'admin', 'password': self.secrets['INITIAL_ADMIN_PASSWORD']})
        expect_status(status, 200, 'POST /api/auth/login')
        tokens = json.loads(body)
        status, body = http_request('POST', f'{api}/api/auth/refresh', json_body={'refresh_token': tokens['refresh_token']})
        expect_status(status, 200, 'POST /api/auth/refresh')
        self.ctx['token'] = json.loads(body)['access_token']
        return 'login + refresh'

    def s_reads(self):
        api, token = self.ctx['api'], self.ctx['token']
        for path in ('/api/locations/live', '/api/users/', '/api/devices/'):
            status, _ = http_request('GET', api + path, token=token)
            expect_status(status, 200, f'GET {path}')
        return '3 endpoints'

    def s_settings(self):
        status, body = http_request('GET', f"{self.ctx['api']}/api/settings", token=self.ctx['token'])
        expect_status(status, 200, 'GET /api/settings')
        data = json.loads(body)
        if not isinstance(data, dict) or 'hq_radius_m' not in data:
            raise StepFail('GET /api/settings: no settings row (key hq_radius_m missing)')
        return 'settings row readable'

    def s_fire(self):
        status, body = http_request('GET', f"{self.ctx['api']}/api/fire/status", token=self.ctx['token'])
        expect_status(status, 200, 'GET /api/fire/status')
        data = json.loads(body)
        if not isinstance(data, dict) or 'feeds' not in data:
            raise StepFail('GET /api/fire/status: no feeds key in the answer')
        return 'fire status readable behind the login'

    def s_weather(self):
        # 503 is the answer of an environment without OWM_API_KEY (the smoke stack has none); 502 = upstream unreachable
        status, _ = http_request('GET', f"{self.ctx['api']}/api/weather/current?lat=42.7&lon=23.3",
                                 token=self.ctx['token'])
        if status not in (200, 502, 503):
            raise StepFail(f'GET /api/weather/current: expected HTTP 200, 502 or 503, got {status}')
        return f'weather proxy answered {status} behind the login'

    def s_websocket(self):
        api, token, port = self.ctx['api'], self.ctx['token'], self.ctx['api_port']
        sn = 900000 + secrets.randbelow(90000)
        status, body = http_request('POST', f'{api}/api/users/', token=token, json_body={
            'first_name': 'Smoke', 'last_name': 'Test', 'phone': '+359000000000', 'role': 'rescuer'})
        expect_status(status, 201, 'create smoke user')
        user_id = json.loads(body)['id']
        status, body = http_request('POST', f'{api}/api/devices/', token=token, json_body={
            'dev_sn': sn, 'name': 'smoke-device', 'user_id': user_id})
        expect_status(status, 201, 'create smoke device')
        device_id = json.loads(body)['id']
        ws = WebSocketClient('127.0.0.1', port)
        try:
            status, _ = http_request('POST', f'{api}/api/test/simulate', token=token,
                                     json_body={'device_id': device_id, 'lat': 42.6977, 'lon': 23.3219})
            expect_status(status, 200, 'POST /api/test/simulate')
            wait_for_message(ws, lambda m: m.get('type') == 'location_update' and m.get('device_id') == device_id)
        finally:
            ws.close()
        return 'location_update received on /ws'

    def s_frontend(self):
        self.containers.append(self.frontend_name)
        self.eng_ok(*self.frontend_run_cmd(), timeout=RUN_TIMEOUT)
        port = self.mapped_port(self.frontend_name, 8080)
        deadline = time.monotonic() + 30
        last = 'no answer'
        while time.monotonic() < deadline:
            try:
                status, body = http_request('GET', f'http://127.0.0.1:{port}/', timeout=5)
                if status == 200:
                    return check_html(body)
                last = f'HTTP {status}'
            except StepFail as exc:
                last = str(exc)
            time.sleep(1)
        raise StepFail(f'GET / through nginx: {last}')

    # -- orchestration
    def run(self) -> int:
        try:
            self.step('engine ready', self.s_engine)
            self.step('build backend image', lambda: self.s_build('backend'), needs=('engine ready',))
            self.step('build frontend image', lambda: self.s_build('frontend'), needs=('engine ready',))
            self.step('empty database up', self.s_database, needs=('engine ready',))
            self.step('a. migrations + backend start', self.s_backend_start,
                      needs=('build backend image', 'empty database up'))
            self.step('b. GET /health = 200', self.s_health, needs=('a. migrations + backend start',))
            self.step('c. admin login + token refresh', self.s_login, needs=('a. migrations + backend start',))
            self.step('d. live / users / devices = 200', self.s_reads, needs=('c. admin login + token refresh',))
            self.step('e. simulated frame reaches /ws', self.s_websocket, needs=('c. admin login + token refresh',))
            self.step('g. GET /api/settings = 200', self.s_settings, needs=('c. admin login + token refresh',))
            self.step('h. GET /api/fire/status = 200', self.s_fire, needs=('c. admin login + token refresh',))
            self.step('i. GET /api/weather/current is served', self.s_weather, needs=('c. admin login + token refresh',))
            self.step('f. frontend image serves the SPA', self.s_frontend, needs=('build frontend image',))
        finally:
            started = time.monotonic()
            problems = self.cleanup()
            if problems:
                self.report.add('cleanup', 'FAIL', time.monotonic() - started, '; '.join(problems)[:500])
            else:
                self.report.add('cleanup', 'PASS', time.monotonic() - started, 'containers, network, volumes removed')
            self.out(Report.line(self.report.results[-1]))
        self.out(self.report.summary())
        return self.report.exit_code


def check_html(body: bytes) -> str:
    text = body.decode('utf-8', 'replace')
    if '<div id="app"' not in text:
        raise StepFail('GET / = 200 but the HTML has no <div id="app">')
    return '<div id="app"> found'


def git_label(repo_root: Path = REPO_ROOT, runner=default_runner) -> str:
    """Short commit (+dirty flag) for the header; best effort."""
    try:
        sha = runner(['git', '-C', str(repo_root), 'rev-parse', '--short', 'HEAD'], timeout=10)
        dirty = runner(['git', '-C', str(repo_root), 'status', '--porcelain', '--untracked-files=no'], timeout=10)
        if sha.returncode != 0:
            return 'unknown'
        return sha.stdout.strip() + (' (uncommitted changes)' if dirty.stdout.strip() else '')
    except Exception:
        return 'unknown'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Smoke test of the develop images (see docs/SMOKE.md)')
    parser.add_argument('--engine', choices=('podman', 'docker'), help='override CONTAINER_ENGINE')
    parser.add_argument('--no-build', action='store_true', help=f'reuse the {IMAGE_TAG} images of an earlier run')
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.engine:
        env['CONTAINER_ENGINE'] = args.engine
    try:
        engine = pick_engine(env)
    except StepFail as exc:
        print(f'FAIL  engine  - {exc}')
        return 2
    print(f'Smoke test of commit {git_label()} with {engine}')
    return Smoke(engine, no_build=args.no_build).run()


if __name__ == '__main__':
    sys.exit(main())
