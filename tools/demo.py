#!/usr/bin/env python3
"""
Demo simulation — creates test users, devices, groups and sends live location updates.

Usage:
    python tools/demo.py                   # random walk near Sofia
    python tools/demo.py --lat 42.1 --lon 24.7 --interval 2
"""

import argparse
import random
import sys
import time

import httpx

BASE = 'http://localhost:8000/api'

DEMO_USERS = [
    {
        'first_name': 'Ivan',   'last_name': 'Petrov',
        'phone': '+359888000001', 'pin': '1234',
        'username': 'demo_ivan', 'password': 'demo123',
        'rank': 'Sergeant', 'blood_type': 'A+', 'role': 'rescuer',
        'dev_sn': 9001, 'dev_name': 'Tracker Ivan',
    },
    {
        'first_name': 'Maria',  'last_name': 'Georgieva',
        'phone': '+359888000002', 'pin': '2345',
        'username': 'demo_maria', 'password': 'demo123',
        'rank': 'Corporal', 'blood_type': 'B+', 'role': 'rescuer',
        'dev_sn': 9002, 'dev_name': 'Tracker Maria',
    },
    {
        'first_name': 'Georgi', 'last_name': 'Dimitrov',
        'phone': '+359888000003', 'pin': '3456',
        'username': 'demo_georgi', 'password': 'demo123',
        'rank': 'Lieutenant', 'blood_type': 'O+', 'role': 'rescuer',
        'dev_sn': 9003, 'dev_name': 'Tracker Georgi',
    },
    {
        'first_name': 'Elena',  'last_name': 'Stoyanova',
        'phone': '+359888000004', 'pin': '4567',
        'username': 'demo_elena', 'password': 'demo123',
        'rank': 'Private', 'blood_type': 'AB-', 'role': 'rescuer',
        'dev_sn': 9004, 'dev_name': 'Tracker Elena',
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


def get_existing_users(headers: dict) -> dict:
    r = httpx.get(f'{BASE}/users/', headers=headers)
    r.raise_for_status()
    return {u['username']: u for u in r.json() if u.get('username')}


def get_or_create_users(headers: dict) -> dict:
    existing = get_existing_users(headers)
    result = {}
    for u in DEMO_USERS:
        uname = u['username']
        if uname in existing:
            print(f'  Using existing user: {existing[uname]["full_name"]}')
            result[uname] = existing[uname]['id']
        else:
            payload = {k: v for k, v in u.items() if k not in ('dev_sn', 'dev_name')}
            resp = httpx.post(f'{BASE}/users/', headers=headers, json=payload)
            resp.raise_for_status()
            uid = resp.json()['id']
            result[uname] = uid
            print(f'  Created user: {u["first_name"]} {u["last_name"]} (id={uid})')
    return result


def get_or_create_devices(headers: dict, user_ids: dict) -> dict:
    existing = {d['dev_sn']: d for d in httpx.get(f'{BASE}/test/devices', headers=headers).json()}
    result = {}
    for u in DEMO_USERS:
        sn = u['dev_sn']
        if sn in existing:
            print(f'  Using existing device: SN={sn}')
            result[u['username']] = str(existing[sn]['id'])
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
    existing = {g['name'] for g in httpx.get(f'{BASE}/groups/', headers=headers).json()}
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
    parser.add_argument('--interval', type=float, default=3.0,   help='Seconds between updates (default: 3)')
    parser.add_argument('--user',     default='admin')
    parser.add_argument('--password', default='admin')
    args = parser.parse_args()

    print('Bee With Me — demo simulator')
    print('─' * 40)

    try:
        headers = login(args.user, args.password)
        print('  Logged in as admin')
    except httpx.HTTPStatusError as e:
        print(f'Login failed: {e}', file=sys.stderr)
        sys.exit(1)

    user_ids = get_or_create_users(headers)
    devices  = get_or_create_devices(headers, user_ids)
    get_or_create_groups(headers, user_ids)

    try:
        run(args.lat, args.lon, args.interval, headers, devices)
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
