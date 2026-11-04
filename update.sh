#!/usr/bin/env bash
# Updates Bee With Me after new code arrived (git pull, or a copy from a USB stick), and is also the
# first run on a new machine: installs the dependencies that changed, backs the database up, applies
# new migrations, then starts the app like start.sh.
#
# Needs the internet only when requirements.txt or package-lock.json changed (or on the first run).
# Everyday starts use ./start.sh, which needs no internet.
#
#   ./update.sh [--project-path DIR] [--skip-containers] [--no-browser]   (the same options as start.sh)

set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start.sh" --update "$@"
