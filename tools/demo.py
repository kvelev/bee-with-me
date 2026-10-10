#!/usr/bin/env python3
"""
Demo simulation — creates test users, devices, groups and sends live location updates.

Usage:
    python tools/demo.py                   # random walk near Sofia
    python tools/demo.py --lat 42.1 --lon 24.7 --interval 90
    python tools/demo.py --no-photos       # skip uploading the persona photos
    python tools/demo.py --replace-photos  # upload photos even if a user already has one

Photos come from tools/demo-user-personas/ (optional; a missing file is skipped). By default a photo is
uploaded only for users that have none yet, so re-running does not pile up files in uploads/.
"""

import argparse
import random
import sys
import time
from pathlib import Path

import httpx

BASE = 'http://localhost:8000/api'
PERSONAS_DIR = Path(__file__).resolve().parent / 'demo-user-personas'
PHOTO_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}

DEMO_USERS = [
    {
        'first_name': 'Ivan',   'last_name': 'Petrov',
        'phone': '+359888000001', 'pin': '1234',
        'username': 'demo_ivan', 'password': 'demo123',
        'rank': 'Sergeant', 'blood_type': 'A+', 'role': 'rescuer',
        'photo': 'ivan-petrov.png', 'dev_sn': 9001, 'dev_name': 'Tracker Ivan',
    },
    {
        'first_name': 'Maria',  'last_name': 'Georgieva',
        'phone': '+359888000002', 'pin': '2345',
        'username': 'demo_maria', 'password': 'demo123',
        'rank': 'Corporal', 'blood_type': 'B+', 'role': 'rescuer',
        'photo': 'maria-georgieva.png', 'dev_sn': 9002, 'dev_name': 'Tracker Maria',
    },
    {
        'first_name': 'Georgi', 'last_name': 'Dimitrov',
        'phone': '+359888000003', 'pin': '3456',
        'username': 'demo_georgi', 'password': 'demo123',
        'rank': 'Lieutenant', 'blood_type': 'O+', 'role': 'rescuer',
        'photo': 'georgi-dimitrov.png', 'dev_sn': 9003, 'dev_name': 'Tracker Georgi',
    },
    {
        'first_name': 'Elena',  'last_name': 'Stoyanova',
        'phone': '+359888000004', 'pin': '4567',
        'username': 'demo_elena', 'password': 'demo123',
        'rank': 'Private', 'blood_type': 'AB-', 'role': 'rescuer',
        'photo': 'elena-stoyanova.png', 'dev_sn': 9004, 'dev_name': 'Tracker Elena',
    },
    {
        'first_name': 'Bai',    'last_name': 'Ivan',
        'phone': '+359888000005', 'pin': '5678',
        'username': 'demo_bai_ivan', 'password': 'demo123',
        'role': 'rescuer',
        'photo': 'bai-ivan.png', 'dev_sn': 9005, 'dev_name': 'Tracker Bai Ivan',
    },
    {
        'first_name': 'Kiril',  'last_name': 'Iliev',
        'phone': '+359888000006', 'pin': '6789',
        'username': 'demo_kiril', 'password': 'demo123',
        'role': 'rescuer',
        'photo': 'kiril-iliev.jpg', 'dev_sn': 9006, 'dev_name': 'Tracker Kiril',
    },
]

SOS_DEVICE = 'demo_elena'   # this device will always transmit with SOS active

DEMO_GROUPS = [
    {
        'name': 'Alpha Team',
        'description': 'First response unit',
        'color': '#ef4444',
        'member_usernames': ['demo_ivan', 'demo_maria'],
        'leader_username': 'demo_ivan',
    },
    {
        'name': 'Bravo Team',
        'description': 'Support unit',
        'color': '#3b82f6',
        'member_usernames': ['demo_georgi', 'demo_elena'],
        'leader_username': 'demo_georgi',
    },
]


def login(username: str = 'admin', password: str = 'admin') -> dict:
    resp = httpx.post(f'{BASE}/auth/login', data={'username': username, 'password': password})
    resp.raise_for_status()
    return {'Authorization': f'Bearer {resp.json()["access_token"]}'}


def check_test_endpoints(headers: dict) -> None:
    r = httpx.get(f'{BASE}/test/devices', headers=headers)
    if r.status_code == 404:
        print('Test endpoints are off: set ENABLE_TEST_ENDPOINTS=true in .env and restart the backend.',
              file=sys.stderr)
        sys.exit(1)
    r.raise_for_status()


def get_all_pages(path: str, headers: dict) -> list:
    """Every item of a paginated list endpoint ({items, total, limit, offset})."""
    items, offset = [], 0
    while True:
        r = httpx.get(f'{BASE}{path}', headers=headers, params={'limit': 500, 'offset': offset})
        r.raise_for_status()
        page = r.json()
        items.extend(page['items'])
        offset += len(page['items'])
        if not page['items'] or offset >= page['total']:
            return items


def get_existing_users(headers: dict) -> dict:
    return {u['username']: u for u in get_all_pages('/users/', headers) if u.get('username')}


def get_or_create_users(headers: dict) -> dict:
    existing = get_existing_users(headers)
    result = {}
    for u in DEMO_USERS:
        uname = u['username']
        if uname in existing:
            user = existing[uname]
            if not user.get('is_active', True):
                httpx.patch(f'{BASE}/users/{user["id"]}/reactivate', headers=headers).raise_for_status()
                print(f'  Reactivated user: {user["full_name"]}')
            else:
                print(f'  Using existing user: {user["full_name"]}')
            result[uname] = user['id']
        else:
            payload = {k: v for k, v in u.items() if k not in ('dev_sn', 'dev_name', 'photo')}
            resp = httpx.post(f'{BASE}/users/', headers=headers, json=payload)
            resp.raise_for_status()
            uid = resp.json()['id']
            result[uname] = uid
            print(f'  Created user: {u["first_name"]} {u["last_name"]} (id={uid})')
    return result


def upload_photos(headers: dict, user_ids: dict, replace: bool = False) -> None:
    existing = get_existing_users(headers)
    for u in DEMO_USERS:
        uname = u['username']
        path = PERSONAS_DIR / u['photo']
        user = existing.get(uname, {})
        if user.get('photo_url') and not replace:
            print(f'  Photo skipped for {uname}: already has one ({user["photo_url"]})')
            continue
        if not path.is_file():
            print(f'  Photo skipped for {uname}: file not found ({path})')
            continue
        ctype = PHOTO_TYPES.get(path.suffix.lower())
        if ctype is None:
            print(f'  Photo skipped for {uname}: unsupported type {path.suffix}')
            continue
        resp = httpx.post(f'{BASE}/users/{user_ids[uname]}/photo', headers=headers,
                          files={'file': (path.name, path.read_bytes(), ctype)})
        resp.raise_for_status()
        print(f'  Uploaded photo for {uname}: {path.name} -> {resp.json()["photo_url"]}')


def get_or_create_devices(headers: dict, user_ids: dict) -> dict:
    # /api/devices/ lists inactive devices too; /api/test/devices only active ones, so a device
    # deactivated earlier would look missing and its re-create would fail with 409.
    r = httpx.get(f'{BASE}/devices/', headers=headers)
    r.raise_for_status()
    existing = {d['dev_sn']: d for d in r.json()}
    result = {}
    for u in DEMO_USERS:
        sn = u['dev_sn']
        if sn in existing:
            device = existing[sn]
            did = str(device['id'])
            if not device['is_active']:
                httpx.post(f'{BASE}/devices/{did}/reactivate', headers=headers).raise_for_status()
                print(f'  Reactivated device: SN={sn}')
            else:
                print(f'  Using existing device: SN={sn}')
            if str(device.get('user_id')) != str(user_ids[u['username']]):
                httpx.put(f'{BASE}/devices/{did}/assign', headers=headers,
                          json={'user_id': user_ids[u['username']]}).raise_for_status()
                print(f'    Assigned SN={sn} to {u["username"]}')
            result[u['username']] = did
        else:
            resp = httpx.post(f'{BASE}/devices/', headers=headers, json={
                'dev_sn':      sn,
                'name':        u['dev_name'],
                'device_type': 'bee',
                'user_id':     user_ids[u['username']],
            })
            resp.raise_for_status()
            did = resp.json()['id']
            result[u['username']] = did
            print(f'  Created device: {u["dev_name"]} SN={sn} (id={did})')
    return result


def get_or_create_groups(headers: dict, user_ids: dict) -> None:
    existing = {g['name'] for g in get_all_pages('/groups/', headers)}
    for g in DEMO_GROUPS:
        if g['name'] in existing:
            print(f'  Using existing group: {g["name"]}')
            continue
        resp = httpx.post(f'{BASE}/groups/', headers=headers, json={
            'name':        g['name'],
            'description': g['description'],
            'color':       g['color'],
        })
        resp.raise_for_status()
        gid = resp.json()['id']
        print(f'  Created group: {g["name"]} (id={gid})')
        for uname in g['member_usernames']:
            is_leader = (uname == g['leader_username'])
            httpx.post(f'{BASE}/groups/{gid}/members', headers=headers, json={
                'user_id':   user_ids[uname],
                'is_leader': is_leader,
            }).raise_for_status()
            print(f'    Added {uname} {"(leader)" if is_leader else ""}')


def run(lat: float, lon: float, interval: float, headers: dict, devices: dict) -> None:
    print(f'\nStreaming location updates every {interval}s — Ctrl+C to stop\n')
    positions = {uname: (lat + random.uniform(-0.05, 0.05), lon + random.uniform(-0.05, 0.05))
                 for uname in devices}
    step = 0
    while True:
        step += 1
        for uname, did in devices.items():
            plat, plon = positions[uname]
            plat += random.uniform(-0.003, 0.003)
            plon += random.uniform(-0.003, 0.003)
            positions[uname] = (plat, plon)

            resp = httpx.post(f'{BASE}/test/simulate', headers=headers, json={
                'device_id':  did,
                'lat':        round(plat, 6),
                'lon':        round(plon, 6),
                'sos_active': uname == SOS_DEVICE,
            })
            if resp.status_code == 200:
                body = resp.json()
                sos_tag = ' 🚨 SOS' if uname == SOS_DEVICE else ''
                print(f'  [{step:>4}] {uname:<15} {body["mgrs"]}   {plat:.5f}N {plon:.5f}E{sos_tag}')
            else:
                print(f'  Error {resp.status_code}: {resp.text}', file=sys.stderr)

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description='Bee With Me demo simulator')
    parser.add_argument('--lat',      type=float, default=42.698, help='Start latitude  (default: Sofia)')
    parser.add_argument('--lon',      type=float, default=23.322, help='Start longitude (default: Sofia)')
    parser.add_argument('--interval', type=float, default=60.0,  help='Seconds between updates, at least 60 like a real tracker (default: 60)')
    parser.add_argument('--user',     default='admin')
    parser.add_argument('--password', default='admin')
    parser.add_argument('--no-photos', action='store_true', help='Do not upload persona photos')
    parser.add_argument('--replace-photos', action='store_true',
                        help='Upload photos even for users that already have one')
    args = parser.parse_args()
    if args.interval < 60:
        parser.error('--interval must be at least 60 seconds (a real tracker reports about once a minute)')

    print('Bee With Me — demo simulator')
    print('─' * 40)

    try:
        headers = login(args.user, args.password)
        print('  Logged in as admin')
    except httpx.HTTPStatusError as e:
        print(f'Login failed: {e}', file=sys.stderr)
        sys.exit(1)

    check_test_endpoints(headers)
    user_ids = get_or_create_users(headers)
    if not args.no_photos:
        upload_photos(headers, user_ids, replace=args.replace_photos)
    devices  = get_or_create_devices(headers, user_ids)
    get_or_create_groups(headers, user_ids)

    try:
        run(args.lat, args.lon, args.interval, headers, devices)
    except KeyboardInterrupt:
        print('\nStopped.')


def _pause_before_close() -> None:
    """Keep a double-clicked console window open so the output can be read."""
    if sys.stdin and sys.stdin.isatty():
        try:
            input('\nPress Enter to close...')
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == '__main__':
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except httpx.HTTPStatusError as e:
        code = 1
        print(f'\nHTTP {e.response.status_code} from {e.request.method} {e.request.url}\n{e.response.text}',
              file=sys.stderr)
    except httpx.HTTPError as e:
        code = 1
        print(f'\nCannot reach the backend at {BASE}: {e}\nIs it running (uvicorn on port 8000)?', file=sys.stderr)
    except Exception:
        import traceback
        code = 1
        traceback.print_exc()
    _pause_before_close()
    sys.exit(code)
