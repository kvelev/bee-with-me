#!/usr/bin/env bash
# Dumps the Bee With Me database to a timestamped file.
#
# Run it after every operation, and on a schedule between them. The whole record of a
# callout lives in one Docker volume on one machine; this is the only thing standing
# between a disk failure and losing it.
#
#   ./scripts/backup.sh [OUT_DIR] [KEEP]
#
# OUT_DIR should be a USB stick or a second drive — a backup on the same disk as the
# database is not a backup. Defaults to ./backups, KEEP defaults to 30.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/backups}"
KEEP="${2:-30}"

# Read DB settings out of .env so this never drifts from the running config
DB="$(grep -E '^\s*POSTGRES_DB\s*=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- | xargs || echo rescuer_locator)"
USER_NAME="$(grep -E '^\s*POSTGRES_USER\s*=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- | xargs || echo rescuer)"
DB="${DB:-rescuer_locator}"
USER_NAME="${USER_NAME:-rescuer}"

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
TARGET="$OUT_DIR/beewithme_$STAMP.sql"

CONTAINER="$(docker compose -f "$ROOT/docker/docker-compose.yaml" ps -q db)"
if [ -z "$CONTAINER" ]; then
  echo "Database container is not running — start it with: docker compose up -d" >&2
  exit 1
fi

echo "==> Dumping $DB to $TARGET"
docker exec "$CONTAINER" pg_dump -U "$USER_NAME" -d "$DB" > "$TARGET"

if [ ! -s "$TARGET" ]; then
  echo "Dump is empty — check the container logs" >&2
  rm -f "$TARGET"
  exit 1
fi
echo "==> Wrote $(du -h "$TARGET" | cut -f1)"

# Prune old dumps, keeping the most recent $KEEP
ls -1t "$OUT_DIR"/beewithme_*.sql 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
  echo "    pruning $(basename "$old")"
  rm -f "$old"
done

echo
echo "To restore into a running (empty) database:"
echo "  docker exec -i $CONTAINER psql -U $USER_NAME -d $DB < $TARGET"
