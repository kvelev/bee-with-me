#!/usr/bin/env bash
# Restores a Bee With Me database dump made by scripts/backup.sh or scripts/backup.ps1.
#
#   ./scripts/restore.sh [--yes] [--force] DUMP_FILE
#
# REPLACES the whole database with the dump. The dump is checked first (pg_restore -l), then
# restored into a side database <db>_restore_<suffix> in a single transaction that stops at the
# first error. Only when that worked is it swapped in: the current database is renamed to
# <db>_before_restore_<UTC stamp> (kept until you drop it) and the side database to <db>. Nothing
# created after the backup (tables, schema_migrations rows) survives; a failed restore leaves the
# current database untouched. Prints the migration status at the end.
#
# Stop the backend first: the script refuses while something listens on port 8000.
#   --yes    don't ask for confirmation
#   --force  restore even though something listens on port 8000 (the backend loses its connections)
#
# Works with Podman (default) or Docker; set CONTAINER_ENGINE to force one.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YES=0
FORCE=0
DUMP=""

die() { echo "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1; shift ;;
    --force)  FORCE=1; shift ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "Unknown option: $1 (see --help)" ;;
    *)  [ -z "$DUMP" ] || die "Only one dump file, please (got '$DUMP' and '$1')"; DUMP="$1"; shift ;;
  esac
done
[ -n "$DUMP" ] || die "Usage: ./scripts/restore.sh [--yes] [--force] DUMP_FILE"
[ -s "$DUMP" ] || die "Dump file not found or empty: $DUMP"

# Container engine: Podman first, Docker as the alternative. Override with CONTAINER_ENGINE.
ENGINE="${CONTAINER_ENGINE:-}"
if [ -z "$ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then ENGINE=podman
  elif command -v docker >/dev/null 2>&1; then ENGINE=docker
  else die "Neither podman nor docker was found on PATH."
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

# The swap renames databases in SQL: plain lower-case names only, short enough for the
# _before_restore_<stamp> name to stay within PostgreSQL's 63-character limit. The letters are spelled
# out: under a UTF-8 locale a range like a-z can also match upper-case letters.
LOWER='abcdefghijklmnopqrstuvwxyz'
NAME_RE="^[${LOWER}_][${LOWER}0123456789_]*\$"
[[ "$DB" =~ $NAME_RE && ${#DB} -le 33 ]]   || die "POSTGRES_DB '$DB': restore supports database names of up to 33 lower-case letters, digits and _ only."
case "$DB" in
  postgres|template0|template1|template_postgis) die "POSTGRES_DB '$DB' is a system database - restore never replaces it. Set POSTGRES_DB to the app's database." ;;
esac
RESTORE_DB="${DB}_restore_$(printf '%04x%04x' "$RANDOM" "$RANDOM")"

# Git Bash/MSYS on Windows: keep container paths (/tmp/...) as they are, hand the engine a Windows path.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) export MSYS_NO_PATHCONV=1; DUMP="$(cygpath -m "$DUMP")" ;;
esac

# Find the db container by its compose labels (project + service), like the backup script.
CONTAINER="$("$ENGINE" ps -q --filter 'label=com.docker.compose.project=bee-with-me' --filter 'label=com.docker.compose.service=db' | head -n1)"
[ -n "$CONTAINER" ] || die "Database container is not running - start it with: $ENGINE compose -p bee-with-me -f docker/docker-compose.yaml up -d"

# The backend must not write into the database while it is replaced.
if (exec 3<>/dev/tcp/127.0.0.1/8000) 2>/dev/null; then
  if [ $FORCE -eq 1 ]; then
    echo "WARNING: something is listening on port 8000 (the backend?) - restoring anyway (--force)." >&2
  else
    die "Something is listening on port 8000 - stop the backend first (Ctrl+C in its terminal), or pass --force."
  fi
fi

if [ $YES -eq 0 ]; then
  echo "This REPLACES database '$DB' in container $CONTAINER with $DUMP."
  read -r -p "Type yes to continue: " answer
  [ "$answer" = yes ] || die "Not restored."
fi

IN_CONTAINER="/tmp/beewithme_restore_$(date +%Y%m%d%H%M%S)_$$_$RANDOM.dump"
# The side database exists only between createdb and the swap; any failure in between drops it.
RESTORE_CREATED=0
drop_restore_db() {
  [ "$RESTORE_CREATED" = 1 ] || return 0
  "$ENGINE" exec "$CONTAINER" dropdb --if-exists --force -U "$USER_NAME" "$RESTORE_DB" >/dev/null 2>&1 || true
}
# Always remove the temp dump inside the container (and a half-restored side database), also when a step fails.
trap '"$ENGINE" exec "$CONTAINER" rm -f "$IN_CONTAINER" >/dev/null 2>&1 || true; drop_restore_db' EXIT
"$ENGINE" cp "$DUMP" "$CONTAINER:$IN_CONTAINER"

# 1. Is this a dump pg_restore can read at all? Checked before any database is touched.
if ! "$ENGINE" exec "$CONTAINER" pg_restore -l "$IN_CONTAINER" >/dev/null; then
  if [ "$(LC_ALL=C head -c 5 "$DUMP")" != PGDMP ]; then
    echo "$DUMP is not a pg_dump custom-format dump - it looks like a plain SQL dump (beewithme_*.sql from" >&2
    echo "1.7.1 or earlier), which pg_restore cannot read. Load it into a scratch database with psql, check it," >&2
    echo "then turn it into a .dump and restore that with this script. Only restore dumps you made yourself:" >&2
    echo 'psql runs as the database superuser and runs any \! shell command in the file.' >&2
    echo "  $ENGINE exec $CONTAINER createdb -U $USER_NAME -O $USER_NAME ${DB}_from_sql" >&2
    echo "  $ENGINE exec -i $CONTAINER psql -v ON_ERROR_STOP=1 -1 -U $USER_NAME -d ${DB}_from_sql < \"$DUMP\"" >&2
    echo "  $ENGINE exec $CONTAINER pg_dump -Fc -U $USER_NAME -d ${DB}_from_sql -f /tmp/from_sql.dump" >&2
    echo "  $ENGINE cp $CONTAINER:/tmp/from_sql.dump ./from_sql.dump" >&2
  fi
  die "pg_restore cannot read $DUMP - nothing restored, database '$DB' was not changed."
fi

# 2. Restore into the side database; the live database stays as it is until this has worked.
echo "==> Restoring into $RESTORE_DB ($ENGINE); '$DB' is not touched until that has worked"
"$ENGINE" exec "$CONTAINER" dropdb --if-exists --force -U "$USER_NAME" "$RESTORE_DB"   # leftover of an interrupted run
RESTORE_CREATED=1
"$ENGINE" exec "$CONTAINER" createdb -U "$USER_NAME" -O "$USER_NAME" "$RESTORE_DB" \
  || die "createdb $RESTORE_DB failed - database '$DB' was not changed."
if ! "$ENGINE" exec "$CONTAINER" pg_restore --exit-on-error --single-transaction --no-owner -U "$USER_NAME" -d "$RESTORE_DB" "$IN_CONTAINER"; then
  die "pg_restore failed - nothing restored, database '$DB' was not changed (the side database $RESTORE_DB is dropped)."
fi

# 3. Swap: one transaction renames the current database away and the restored one into its place.
KEPT_DB="${DB}_before_restore_$(date -u +%Y%m%d%H%M%S)"
EXISTS="$("$ENGINE" exec "$CONTAINER" psql -U "$USER_NAME" -d postgres -Atc "SELECT count(*) FROM pg_database WHERE datname = '$DB'" | tr -d '\r')"
if [ "$EXISTS" = 1 ]; then
  SWAP_SQL="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid(); ALTER DATABASE $DB RENAME TO $KEPT_DB; ALTER DATABASE $RESTORE_DB RENAME TO $DB;"
else
  KEPT_DB=""
  SWAP_SQL="ALTER DATABASE $RESTORE_DB RENAME TO $DB;"
fi
echo "==> Swapping $RESTORE_DB in as $DB"
"$ENGINE" exec "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$USER_NAME" -d postgres -c "$SWAP_SQL" >/dev/null \
  || die "Swapping the restored database in failed - database '$DB' was not changed (is something still connected to it?)."
RESTORE_CREATED=0
echo "==> Restored $DUMP into $DB"
if [ -n "$KEPT_DB" ]; then
  echo "The database as it was before the restore is kept as $KEPT_DB. Once the restored data is verified, drop it with:"
  echo "  $ENGINE exec $CONTAINER dropdb -U $USER_NAME $KEPT_DB"
fi

# Show where the restored database stands (pending migrations are applied by the next start).
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/.venv/Scripts/python.exe"
if [ -x "$PY" ]; then
  echo "==> python -m backend.db.migrate status"
  set +e
  ( cd "$ROOT" && "$PY" -m backend.db.migrate status )
  echo "    (exit $?: 0 up to date, 10 pending - applied by the next start, 2 database newer than the app)"
  set -e
else
  echo "No .venv found - check the state later with: python -m backend.db.migrate status"
fi
