#!/usr/bin/env bash
# Dumps the Bee With Me database to a timestamped file.
#
# Run it after every operation, and on a schedule between them. The whole record of a
# callout lives in one Docker volume on one machine; this is the only thing standing
# between a disk failure and losing it.
#
#   ./scripts/backup.sh [--container ID] [OUT_DIR] [KEEP]
#
# --container ID dumps that container instead of the one found by its compose labels (project
# bee-with-me, service db); the start scripts use it to back up an older install (project "docker").
#
# OUT_DIR should be a USB stick or a second drive — a backup on the same disk as the
# database is not a backup. Defaults to ./backups, KEEP defaults to 30.
#
# Works with Podman (default) or Docker; set CONTAINER_ENGINE to force one. Dumps are pg_dump custom format (.dump); restore with scripts/restore.sh, which runs pg_restore (hint printed at the end).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_OVERRIDE=""
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --container) [ $# -ge 2 ] || { echo "--container needs a value" >&2; exit 1; }; CONTAINER_OVERRIDE="$2"; shift 2 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
OUT_DIR="${POSITIONAL[0]:-}"
# An empty or blank OUT_DIR means ./backups (the same as backup.ps1 -OutDir '').
[[ "$OUT_DIR" =~ ^[[:space:]]*$ ]] && OUT_DIR="$ROOT/backups"
KEEP="${POSITIONAL[1]:-30}"
if ! [[ "$KEEP" =~ ^[0-9]+$ ]] || [ "$((10#$KEEP))" -lt 1 ]; then
  echo "Keep must be a whole number of at least 1 (got '$KEEP'): it is how many dumps stay in the folder." >&2
  exit 1
fi
KEEP="$((10#$KEEP))"

# Container engine: Podman first, Docker as the alternative. Override with CONTAINER_ENGINE.
ENGINE="${CONTAINER_ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE=podman
  elif command -v docker >/dev/null 2>&1; then ENGINE=docker
  else echo "Neither podman nor docker was found on PATH." >&2; exit 1
  fi
fi

# .env value of $1 (or $2 when unset/empty): surrounding quotes, a trailing CR and an inline
# " # comment" are not part of the value; a leading `export ` (lower case only, like python-dotenv)
# is accepted; keys match in any case (like the backend's settings and the PowerShell scripts).
env_value() {
  local line value key="" upper lower i LC_ALL=C
  # the key as a pattern that matches it in any case ([pP][oO]...), without grep -i (which would also
  # accept EXPORT) and without locale-dependent ranges
  # (tr, not ${c^^}/${c,,}: macOS ships bash 3.2 as /bin/bash, which has no case modifiers)
  upper="$(printf '%s' "$1" | LC_ALL=C tr 'abcdefghijklmnopqrstuvwxyz' 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')"
  lower="$(printf '%s' "$1" | LC_ALL=C tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz')"
  for ((i = 0; i < ${#1}; i++)); do key+="[${upper:i:1}${lower:i:1}]"; done
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?$key[[:space:]]*=" "$ROOT/.env" 2>/dev/null | tail -n1 || true)"
  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#"${value%%[![:space:]]*}"}"
  case "$value" in
    \"*) value="${value#\"}"; value="${value%%\"*}" ;;
    \'*) value="${value#\'}"; value="${value%%\'*}" ;;
    *)   value="${value%%[[:space:]]#*}"; value="${value%"${value##*[![:space:]]}"}" ;;
  esac
  printf '%s' "${value:-$2}"
}

# Read DB settings out of .env so this never drifts from the running config
# A process environment variable wins over the file (the same precedence as the backend's settings).
DB="${POSTGRES_DB:-$(env_value POSTGRES_DB rescuer_locator)}"
USER_NAME="${POSTGRES_USER:-$(env_value POSTGRES_USER rescuer)}"

# Git Bash/MSYS on Windows: stop it rewriting container paths (/tmp/...) into Windows paths,
# and give the engine the output folder as a Windows path it understands.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) export MSYS_NO_PATHCONV=1; OUT_DIR="$(cygpath -m "$OUT_DIR")" ;;
esac

# Dumps hold every position and name of a callout: readable by this user only.
umask 077
case "$(uname -s)" in
  MINGW*|MSYS*)
    echo "NOTE: under Git Bash the file modes (umask 077, chmod 600) are not enforced on NTFS - the dumps" >&2
    echo "      inherit the folder's Windows permissions. On Windows use scripts/backup.ps1, which restricts" >&2
    echo "      the dump folder to this user." >&2 ;;
esac
# The folder has to be one this user can write to. With rootful Docker the compose bind mount
# ../data/pgdata makes the daemon create data/ as root:root, so data/backups cannot be made afterwards;
# the start scripts create it first, and this stops with the fix instead of a bare mkdir error.
if ! mkdir -p "$OUT_DIR" 2>/dev/null || [ ! -d "$OUT_DIR" ] || [ ! -w "$OUT_DIR" ]; then
  echo "Cannot write to the backup folder $OUT_DIR - nothing was dumped." >&2
  case "$OUT_DIR" in
    "$ROOT"/data|"$ROOT"/data/*)
      echo "Rootful Docker creates data/ as root. Make it yours once (data/pgdata stays owned by the container):" >&2
      echo "  sudo mkdir -p \"$ROOT/data/backups\" && sudo chown \"$(id -un)\" \"$ROOT/data\" \"$ROOT/data/backups\"" >&2 ;;
    *)
      echo "Make that folder writable for $(id -un), or pass another folder as OUT_DIR." >&2 ;;
  esac
  exit 1
fi
# Random suffix: two runs in the same second never share a file name (here or in the container).
# LC_ALL=C: the digits and the Gregorian year whatever the locale (th_TH would print the Buddhist year).
STAMP="$(LC_ALL=C date +%Y-%m-%d_%H%M%S)_$(printf '%04x%04x' "$RANDOM" "$RANDOM")"
FINAL="$OUT_DIR/beewithme_$STAMP.dump"
# TARGET is the .partial file until the dump has been validated, then it is renamed to FINAL.
PARTIAL="$FINAL.partial"
TARGET="$PARTIAL"

# Find the db container by its compose labels (project + service): works for podman and docker
# compose alike, and never picks another compose project's `db` service.
# --container overrides the lookup (upgrade from an older install, see start.sh).
CONTAINER="$CONTAINER_OVERRIDE"
[ -n "$CONTAINER" ] || CONTAINER="$("$ENGINE" ps -q --filter 'label=com.docker.compose.project=bee-with-me' --filter 'label=com.docker.compose.service=db' | head -n1)"
if [ -z "$CONTAINER" ]; then
  echo "Database container is not running - start it with: $ENGINE compose -p bee-with-me -f docker/docker-compose.yaml up -d" >&2
  exit 1
fi

# Custom format (-Fc): binary and compressed; written inside the container, then copied out.
IN_CONTAINER="/tmp/beewithme_$STAMP.dump"
# Always remove the temp dump inside the container, also when the dump or the copy fails; a partial
# dump is never left behind looking like a backup (after the rename it no longer exists).
trap '"$ENGINE" exec "$CONTAINER" rm -f "$IN_CONTAINER" >/dev/null 2>&1 || true; rm -f "$PARTIAL"' EXIT

# State for the backup marker (last-backup.json, see below), read just before the dump: which server
# this is and which migrations it has. The backend migrates only after a backup of this exact state.
psql_at() { "$ENGINE" exec "$CONTAINER" psql -U "$USER_NAME" -d "$DB" -Atc "$1" | tr -d '\r'; }
CREATED_AT="$(LC_ALL=C date -u +%Y-%m-%dT%H:%M:%SZ)"
SYSTEM_ID="$(psql_at 'SELECT system_identifier FROM pg_control_system()')"
[[ "$SYSTEM_ID" =~ ^[0-9]+$ ]] || { echo "Could not read the database's system_identifier ($SYSTEM_ID)" >&2; exit 1; }
DATABASE="$(psql_at 'SELECT current_database()')"
# written into JSON below as it is: no quotes, backslashes or control characters
case "$DATABASE" in
  ''|*'"'*|*'\'*|*[[:cntrl:]]*) echo "Unexpected database name: $DATABASE" >&2; exit 1 ;;
esac
APPLIED=""
if [ "$(psql_at "SELECT to_regclass('public.schema_migrations') IS NOT NULL")" = t ]; then
  APPLIED="$(psql_at 'SELECT version FROM schema_migrations ORDER BY version' | paste -sd, -)"
fi
[[ "$APPLIED" =~ ^[0-9,]*$ ]] || { echo "Unexpected schema_migrations versions: $APPLIED" >&2; exit 1; }

echo "==> Dumping $DB to $FINAL ($ENGINE)"
"$ENGINE" exec "$CONTAINER" pg_dump -Fc -U "$USER_NAME" -d "$DB" -f "$IN_CONTAINER"
# A dump pg_restore cannot list is no backup: check it before it counts as one.
"$ENGINE" exec "$CONTAINER" pg_restore -l "$IN_CONTAINER" >/dev/null \
  || { echo "pg_restore -l cannot read the dump - not kept as a backup" >&2; exit 1; }
EXPECTED="$("$ENGINE" exec "$CONTAINER" stat -c %s "$IN_CONTAINER" | tr -d '\r')"
if ! "$ENGINE" cp "$CONTAINER:$IN_CONTAINER" "$TARGET"; then
  # Docker Desktop's cp fails on a container with a single-file bind mount ("mkdirat
  # docker-entrypoint-initdb.d/schema.sql: file exists" - older installs mounted schema.sql). Stream the
  # dump instead: exec without -t is binary-safe, and the size check below catches a short copy.
  echo "NOTE: $ENGINE cp failed - streaming the dump out of the container instead" >&2
  "$ENGINE" exec "$CONTAINER" cat "$IN_CONTAINER" > "$TARGET"
fi
chmod 600 "$TARGET"   # the engine copies the container file's mode (0644)

if [ ! -s "$TARGET" ] || [ "$(wc -c < "$TARGET" | tr -d ' ')" != "$EXPECTED" ]; then
  echo "The copied dump is empty or incomplete - check the container logs" >&2
  exit 1   # the EXIT trap removes the partial file
fi
mv -f "$TARGET" "$FINAL"
TARGET="$FINAL"
echo "==> Wrote $(du -h "$TARGET" | cut -f1)"

# Backup marker next to the dump: the backend applies pending migrations only when the marker in
# data/backups (BACKUP_MARKER_PATH) is of this server and database, in its current state, under 24 h
# old, and its dump is there.
MARKER="$OUT_DIR/last-backup.json"
APPLIED_JSON="$(printf '%s' "$APPLIED" | awk -F, '{ for (i = 1; i <= NF; i++) printf "%s\"%s\"", (i > 1 ? ", " : ""), $i }')"
printf '{"system_identifier": "%s", "database": "%s", "applied": [%s], "dump": "%s", "created_at": "%s"}\n' \
  "$SYSTEM_ID" "$DATABASE" "$APPLIED_JSON" "$(basename "$TARGET")" "$CREATED_AT" > "$MARKER.tmp"
mv -f "$MARKER.tmp" "$MARKER"
echo "==> Marker $MARKER"

# Prune old dumps (only *.dump: .dump.partial and older plain .sql dumps are left alone). The dump just
# written always stays (the marker names it), whatever the other files' times say; of the others, the
# newest KEEP - 1 stay.
ls -1t "$OUT_DIR"/beewithme_*.dump 2>/dev/null | FRESH="$TARGET" awk '$0 != ENVIRON["FRESH"]' \
  | tail -n "+$KEEP" | while read -r old; do
  echo "    pruning $(basename "$old")"
  rm -f "$old"
done

echo
echo "To restore (replaces the whole database; stop the backend first):"
echo "  \"$ROOT/scripts/restore.sh\" \"$TARGET\""
