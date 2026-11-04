#!/usr/bin/env bash
# Stub backup.sh for the start-script tests: logs its arguments, fails when BWM_STUB_BACKUP_FAIL=1,
# otherwise writes a marker like the real script so start.sh can name the dump.
set -euo pipefail
echo "backup $*" >> "$BWM_STUB_LOG"
[ "${BWM_STUB_BACKUP_FAIL:-}" != 1 ] || { echo 'stub backup failed' >&2; exit 1; }
out="${*: -1}"
echo "backup-state dir_existed=$([ -d "$out" ] && echo 1 || echo 0)" >> "$BWM_STUB_LOG"
mkdir -p "$out"
printf '{"dump": "beewithme_stub.dump"}\n' > "$out/last-backup.json"
echo 'STUB BACKUP DONE'
