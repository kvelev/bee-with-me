#!/usr/bin/env bash
# Starts the whole Bee With Me stack on Linux: Postgres/PostGIS (Podman or Docker), the
# FastAPI backend, and the Vue frontend - instead of starting each one by hand.
# Linux counterpart of start.ps1.
#
# Like start.ps1, it lives in the project root and uses its own location to
# find the project, so it works wherever the folder is copied to.
#
# Unlike start.ps1, backend and frontend run in THIS terminal (output prefixed
# with [backend] / [frontend]) rather than in new windows - there is no terminal
# emulator that is guaranteed to exist on every distro. Ctrl+C stops both.
#
#   ./start.sh [--project-path DIR] [--skip-containers] [--no-browser]
#
#   --project-path DIR  Path to the project folder (default: this script's folder).
#   --skip-containers  Don't start the database container (database already running). --skip-docker still works.
#   --no-browser        Don't auto-open the frontend once it's up.

set -euo pipefail

PROJECT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_CONTAINERS=0
NO_BROWSER=0

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-path) [[ $# -ge 2 ]] || die '--project-path needs a value'; PROJECT_PATH="$2"; shift 2 ;;
        --skip-containers|--skip-docker) SKIP_CONTAINERS=1; shift ;;
        --no-browser)   NO_BROWSER=1; shift ;;
        -h|--help)      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)              die "Unknown option: $1 (see --help)" ;;
    esac
done

[[ -d "$PROJECT_PATH" ]] || die "Project folder not found: $PROJECT_PATH
Pass the real location with --project-path, e.g.:
  ./start.sh --project-path ~/bee-with-me"
ROOT="$(cd "$PROJECT_PATH" && pwd)"
cd "$ROOT"
step "Using project folder: $ROOT"

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

# A folder path in one comparable form: / separators (repeated ones collapsed), no trailing /, WSL
# /mnt/<drive>/... as <drive>:/..., Git Bash /c/... via cygpath; case-insensitive on Windows (only the
# drive letter elsewhere).
norm_path() {
    local p
    p="$(printf '%s' "$1" | tr '\\' '/' | tr -s '/')"
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) [[ "$p" == /* && ! "$p" =~ ^/mnt/[a-zA-Z](/|$) ]] && p="$(cygpath -m "$p")" ;;
    esac
    while [[ "$p" == */ ]]; do p="${p%/}"; done
    if [[ "$p" =~ ^/mnt/([a-zA-Z])(/.*)?$ ]]; then p="${BASH_REMATCH[1]}:${BASH_REMATCH[2]}"; fi
    if [[ "$p" =~ ^([a-zA-Z]):(.*)$ ]]; then p="$(printf '%s' "${BASH_REMATCH[1]}" | LC_ALL=C tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz'):${BASH_REMATCH[2]}"; fi
    # Git Bash is bash 4+, so ${p,,} is safe here (and lowers non-ASCII letters, unlike tr).
    case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) p="${p,,}" ;; esac
    printf '%s' "$p"
}

# 0 when the old compose-project-"docker" container $1 belongs to this folder: its compose working_dir
# is <root>/docker or its data mount is <root>/data/pgdata. Missing information counts as "not ours".
old_container_is_ours() {
    OLD_WORKDIR="$("$ENGINE" inspect --format '{{ index .Config.Labels `com.docker.compose.project.working_dir` }}' "$1" 2>/dev/null | tr -d '\r' || true)"
    OLD_MOUNT="$("$ENGINE" inspect --format '{{range .Mounts}}{{if eq .Destination `/var/lib/postgresql/data`}}{{.Source}}{{end}}{{end}}' "$1" 2>/dev/null | tr -d '\r' || true)"
    [[ "$OLD_WORKDIR" == "<no value>" ]] && OLD_WORKDIR=""
    if [[ -n "$OLD_WORKDIR" && "$(norm_path "$OLD_WORKDIR")" == "$(norm_path "$ROOT/docker")" ]]; then return 0; fi
    if [[ -n "$OLD_MOUNT" && "$(norm_path "$OLD_MOUNT")" == "$(norm_path "$ROOT/data/pgdata")" ]]; then return 0; fi
    return 1
}

# Returns 0 once something is listening on localhost:$1 (bash /dev/tcp - no nc needed)
port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# -- .env ------------------------------------------------------------------------
# A random 64-character key (48 random bytes, base64) for a new install; never printed.
# openssl first; when it is missing or fails, /dev/urandom + base64. Sets NEW_KEY; KEY_TRIED names what was attempted.
new_secret_key() {
    local key=''
    KEY_TRIED=''
    NEW_KEY=''
    if command -v openssl >/dev/null 2>&1; then
        KEY_TRIED='openssl'
        key="$(openssl rand -base64 48 2>/dev/null | tr -d '\r\n' || true)"
    fi
    if [[ ${#key} -lt 48 ]]; then
        KEY_TRIED="${KEY_TRIED:+$KEY_TRIED, then }/dev/urandom + base64"
        key="$(head -c 48 /dev/urandom 2>/dev/null | base64 2>/dev/null | tr -d '\r\n' || true)"
    fi
    NEW_KEY="$key"
}

if [[ ! -f "$ROOT/.env" ]]; then
    step 'No .env found - copying .env.example with a new random SECRET_KEY'
    new_secret_key   # sets NEW_KEY and KEY_TRIED (no subshell: both must reach this shell)
    [[ ${#NEW_KEY} -ge 48 ]] \
        || die "Could not generate a random SECRET_KEY (tried: ${KEY_TRIED:-nothing}; none gave a usable key) - .env was not created. Install openssl (or base64 and a readable /dev/urandom) and run this script again."
    # The example's SECRET_KEY line gets the random value (a line that is not there is added); every other
    # line is copied as it is. The file is private to this user (umask 077). An existing .env is never touched.
    # The temp file is made by mktemp next to the target (always 0600, a fresh name: a stale file of an earlier
    # run is never reused, so it cannot lend its old mode); a trap removes it on any exit or signal.
    ENV_TMP=''
    trap 'rm -f "$ENV_TMP"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    ENV_TMP="$(umask 077; mktemp "$ROOT/.env.new.XXXXXX")" || die 'Could not create a temporary file for .env - nothing was written.'
    ( umask 077
      BWM_NEW_KEY="$NEW_KEY" awk '
          match($0, /^[ \t]*(export[ \t]+)?[sS][eE][cC][rR][eE][tT]_[kK][eE][yY][ \t]*=/) {
              cr = ($0 ~ /\r$/) ? "\r" : ""
              print substr($0, 1, RLENGTH) ENVIRON["BWM_NEW_KEY"] cr
              found = 1; next
          }
          { print }
          END { if (!found) print "SECRET_KEY=" ENVIRON["BWM_NEW_KEY"] }
      ' "$ROOT/.env.example" > "$ENV_TMP" ) \
        && mv -f "$ENV_TMP" "$ROOT/.env" \
        || die 'Could not create .env from .env.example.'   # the EXIT trap removes the temp file
    trap - EXIT INT TERM
    ENV_TMP=''
    unset NEW_KEY
    warn 'Edit .env with real values (POSTGRES_PASSWORD, HID_VENDOR_ID/HID_PRODUCT_ID, ...) before relying on this for anything but a quick test. SECRET_KEY was generated for you.'
fi

# -- Database container (Podman first, Docker as the alternative) --------------------
ENGINE="${CONTAINER_ENGINE:-}"
if [[ -z "$ENGINE" ]]; then
    if command -v podman >/dev/null 2>&1; then ENGINE=podman
    elif command -v docker >/dev/null 2>&1; then ENGINE=docker
    fi
fi

if [[ $SKIP_CONTAINERS -eq 0 ]]; then
    [[ -n "$ENGINE" ]] \
        || die 'Neither podman nor docker was found on PATH. Install Podman (https://podman.io) or Docker, or re-run with --skip-containers if the database is already running elsewhere.'
    if ! "$ENGINE" info >/dev/null 2>&1; then
        if [[ "$ENGINE" == podman ]]; then
            die "Podman is installed but not usable by $(whoami). Rootless podman needs no daemon; check 'podman info' for the error (on macOS/Windows: podman machine start)."
        fi
        die "Docker is installed but not usable by $(whoami). Either the daemon isn't running
  (sudo systemctl start docker) or you're not in the docker group
  (sudo usermod -aG docker $(whoami), then log out and back in)."
    fi

    # Podman on macOS/Windows runs in a VM: named volume + host network for Postgres
    # (see docker/docker-compose.podman-machine.yaml for why). Native-Linux Podman uses the base file.
    COMPOSE_FILES=(-f "$ROOT/docker/docker-compose.yaml")
    case "$(uname -s)" in
        Darwin|MINGW*|MSYS*|CYGWIN*)
            [[ "$ENGINE" == podman ]] && COMPOSE_FILES+=(-f "$ROOT/docker/docker-compose.podman-machine.yaml") ;;
    esac

    # The override keeps Postgres in a named volume, so database files already in data/pgdata (bind mount of
    # the base file: Docker, or native Podman) would be left behind and the database would start empty.
    if [[ " ${COMPOSE_FILES[*]} " == *podman-machine* && -e "$ROOT/data/pgdata/PG_VERSION" ]]; then
        STAMP="$(LC_ALL=C date +%Y%m%d-%H%M%S)"
        die "This folder already has database files in data/pgdata (made with Docker, or Podman without a VM), but Podman here would
start the database on its own named volume (bee-with-me_pgdata), which is empty: your data would look gone. Nothing was started.
To keep using data/pgdata, choose Docker:
  CONTAINER_ENGINE=docker \"$ROOT/start.sh\"
To move to Podman instead (nothing is deleted):
(1) back up with Docker, not Podman (write down the dump file name it prints: step (4) restores that file), then stop the Docker stack:
  CONTAINER_ENGINE=docker \"$ROOT/scripts/backup.sh\" \"$ROOT/data/backups\"
  cd \"$ROOT\" && docker compose -p bee-with-me -f docker/docker-compose.yaml stop
(2) rename data/pgdata out of the way (it becomes $ROOT/data/pgdata.docker-$STAMP):
  mv -n \"$ROOT/data/pgdata\" \"$ROOT/data/pgdata.docker-$STAMP\"
(3) start again with Podman (the Docker choice is cleared):
  unset CONTAINER_ENGINE; \"$ROOT/start.sh\"
(4) stop the backend (Ctrl+C in that window), then restore the dump from step (1) (not a newer file: step (3) makes a dump of the empty Podman database):
  \"$ROOT/scripts/restore.sh\" \"$ROOT/data/backups/<the dump from step (1)>\""
    fi

    # data/backups is made now, as this user: rootful Docker would create data/ as root through the bind
    # mount of data/pgdata, and the backup before a migration could not write there any more.
    # The dumps hold personal data: the folder is 0700 (a new one is made with umask 077; an existing one of
    # ours is tightened; one owned by someone else is left as it is, the write check below decides).
    if mkdir -p "$ROOT/data" 2>/dev/null; then
        ( umask 077; mkdir -p "$ROOT/data/backups" ) 2>/dev/null || true
        if [[ -O "$ROOT/data/backups" ]]; then chmod 700 "$ROOT/data/backups" 2>/dev/null || true; fi
    fi
    if [[ ! -d "$ROOT/data/backups" || ! -w "$ROOT/data/backups" ]]; then
        die "Cannot write to the backup folder $ROOT/data/backups - not starting, so the database is never migrated without a backup.
If Docker created data/ as root, make it yours once (data/pgdata stays owned by the container):
  sudo mkdir -p \"$ROOT/data/backups\" && sudo chown \"\$(id -un)\" \"$ROOT/data\" \"$ROOT/data/backups\""
    fi

    # Upgrade from 1.7.1 or earlier: the stack ran as compose project "docker" (docker-db-1) on the
    # same port and, on the base file, the same data folder. Back that database up, then stop the old
    # project (no -v: data/pgdata stays and the new project reuses it), before the new one starts.
    # Only when that container belongs to THIS folder: another folder's copy or another app's "docker"
    # project is never stopped (see old_container_is_ours).
    OLD_DB="$("$ENGINE" ps -q --filter 'label=com.docker.compose.project=docker' --filter 'label=com.docker.compose.service=db' | head -n1)"
    OLD_DUMP=""
    if [[ -n "$OLD_DB" ]] && ! old_container_is_ours "$OLD_DB"; then
        die "A database container of compose project 'docker' (container $OLD_DB) is running, but it does not
belong to this folder ($ROOT): it is from another folder or another app
(working_dir '${OLD_WORKDIR:-unknown}', data '${OLD_MOUNT:-unknown}'). It probably holds port 5432, so
nothing was stopped and Bee With Me is not started. If it is an older Bee With Me install whose data
you want here, back it up, stop it yourself, then start this one and restore the dump:
  \"$ROOT/scripts/backup.sh\" --container $OLD_DB \"$ROOT/data/backups\"
  $ENGINE stop $OLD_DB
  \"$ROOT/start.sh\"   then, with the backend stopped:   \"$ROOT/scripts/restore.sh\" \"$ROOT/data/backups/<the new dump>\"
Otherwise stop that app (or move one of them to another port) and start again."
    fi
    if [[ -n "$OLD_DB" ]]; then
        step "Found the database of an older install (compose project 'docker', container $OLD_DB): backing it up, then stopping it"
        "$ROOT/scripts/backup.sh" --container "$OLD_DB" "$ROOT/data/backups" \
            || die 'Backup of the old database failed - not continuing; the old install is left running.'
        OLD_DUMP="$ROOT/data/backups/$(sed -n 's/.*"dump": *"\([^"]*\)".*/\1/p' "$ROOT/data/backups/last-backup.json")"
        "$ENGINE" compose -p docker -f "$ROOT/docker/docker-compose.yaml" down \
            || die "$ENGINE compose -p docker down failed - stop the old containers (docker-db-1, docker-tiles-1) yourself, then re-run."
    fi

    step "Starting database ($ENGINE compose -p bee-with-me up -d)"
    "$ENGINE" compose -p bee-with-me "${COMPOSE_FILES[@]}" up -d

    step 'Waiting for Postgres to accept connections'
    PG_PORT="$(env_value POSTGRES_PORT 5432)"
    [[ "$PG_PORT" =~ ^[0-9]+$ ]] || PG_PORT=5432

    ready=0
    for _ in $(seq 60); do
        if port_open "$PG_PORT"; then ready=1; break; fi
        sleep 1
    done
    [[ $ready -eq 1 ]] \
        || warn "Postgres didn't come up on port $PG_PORT within 60s - continuing anyway. Check: $ENGINE compose -f docker/docker-compose.yaml -p bee-with-me logs"

    if [[ -n "$OLD_DUMP" && " ${COMPOSE_FILES[*]} " == *podman-machine* ]]; then
        # With the podman-machine override the old data is in the volume docker_pgdata, not data/pgdata:
        # the new database (volume bee-with-me_pgdata) is empty. Don't start the backend on it.
        die "The old install kept its data in the Podman volume docker_pgdata; the new database (volume bee-with-me_pgdata) starts empty, so the backend is not started. Restore the backup just taken into it, then start again:
  \"$ROOT/scripts/restore.sh\" \"$OLD_DUMP\"
  \"$ROOT/start.sh\"
(The volume docker_pgdata is left as it was.)"
    fi
fi

# -- Python venv + backend deps ---------------------------------------------------
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    step 'Creating Python virtual environment (.venv)'
    PY="$(command -v python3 || command -v python || true)"
    [[ -n "$PY" ]] || die 'Python was not found on PATH (tried "python3" and "python"). Install Python 3.11+ and re-run.'
    "$PY" -m venv "$ROOT/.venv" \
        || die "Failed to create the virtual environment at $ROOT/.venv. On Debian/Ubuntu the venv module is a separate package: sudo apt install python3-venv"
fi

step 'Installing/checking backend dependencies'
if ! "$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/backend/requirements.txt"; then
    # Offline laptops still start with what is installed; a missing package shows up when the backend starts.
    warn 'pip install failed (offline?) - continuing with the packages already in .venv.'
fi

# -- Database migrations: back up first if any are pending ---------------------------
if [[ $SKIP_CONTAINERS -eq 0 ]]; then
    step 'Checking database migrations'
    # Exit 3 means Postgres isn't accepting connections yet (slow after a reboot or
    # `podman machine start`): retry for up to 90 s rather than let the backend migrate later
    # without the backup this check exists for. Any other code is final at once.
    mig_deadline=$((SECONDS + 90))
    # BWM_MIGRATE_WAIT_S: shorter deadline for the script tests (backend/tests/test_scripts_behaviour.py)
    if [[ "${BWM_MIGRATE_WAIT_S:-}" =~ ^[0-9]+$ ]]; then mig_deadline=$((SECONDS + BWM_MIGRATE_WAIT_S)); fi
    while :; do
        set +e
        ( cd "$ROOT" && "$ROOT/.venv/bin/python" -m backend.db.migrate status )
        mig=$?
        set -e
        [[ $mig -eq 3 && $SECONDS -lt $mig_deadline ]] || break
        warn 'Database not reachable yet - retrying in 3 s'
        sleep 3
    done
    case "$mig" in
        0)  ;;
        10) step 'Migrations pending - taking a backup first (data/backups)'
            "$ROOT/scripts/backup.sh" "$ROOT/data/backups" \
                || die 'Backup failed - not starting, so the database is never migrated without a backup.' ;;
        1)  die 'Not starting: the migration files are invalid: see the message above.' ;;
        2)  die 'The database is newer than this version of Bee With Me. Update the app (git pull) instead of starting an older one.' ;;
        *)  die "Could not check database migrations (database not reachable?) - not starting, so the database is never migrated without a backup. Check: $ENGINE compose -f docker/docker-compose.yaml -p bee-with-me logs" ;;
    esac
fi

# BWM_START_DRY_RUN=1 (script tests): stop after the database and migration decisions.
if [[ "${BWM_START_DRY_RUN:-}" == 1 ]]; then
    echo 'DRY RUN: would start backend and frontend'
    exit 0
fi

# -- Frontend deps ------------------------------------------------------------------
command -v node >/dev/null 2>&1 || die 'Node.js was not found on PATH. Install Node.js 24 LTS and re-run.'
command -v npm >/dev/null 2>&1 || die 'npm was not found on PATH. Install Node.js 24 LTS and re-run.'
# Floor matches "engines" in frontend/package.json; .npmrc engine-strict enforces it for npm too.
node -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit(a > 22 || (a === 22 && b >= 12) ? 0 : 1)' \
    || die "Node.js $(node -v) is too old (need 22.12+). Install Node.js 24 LTS and re-run."
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    step 'Installing frontend dependencies (first run only - this can take a minute)'
    (cd "$ROOT/frontend" && npm install)
fi

# -- USB HID gateway permissions ---------------------------------------------------
# On Linux, /dev/hidraw* is root-only by default. Without a udev rule the backend
# runs fine but never sees the gateway - worth a loud hint rather than silence.
if ! grep -rqsi 'hidraw' /etc/udev/rules.d/ 2>/dev/null; then
    warn 'No udev rule for hidraw found - the backend may not be able to open the USB gateway as a normal user.
  Fix once with (VID/PID from .env, without the 0x prefix, lowercase):
    echo '"'"'KERNEL=="hidraw*", ATTRS{idVendor}=="0acd", ATTRS{idProduct}=="faaf", MODE="0660", GROUP="plugdev"'"'"' | sudo tee /etc/udev/rules.d/99-bee-gateway.rules
    sudo usermod -aG plugdev "$USER"
    sudo udevadm control --reload-rules && sudo udevadm trigger
  then unplug and replug the gateway and log out and in again (group change). Not world-writable on purpose.
  No plugdev group on your distro (Fedora, Arch)? Use TAG+="uaccess" instead of GROUP/MODE (the logged-in user gets access).'
fi

# -- Backend + frontend (this terminal) ---------------------------------------------
# On Ctrl+C / exit, kill the whole process group: uvicorn and npm/vite
# both spawn children that would otherwise be orphaned and keep the ports busy.
trap 'trap - INT TERM EXIT; echo; step "Stopping backend and frontend"; kill 0 2>/dev/null; wait 2>/dev/null' INT TERM EXIT

step 'Starting backend (uvicorn)'
( cd "$ROOT" && exec "$ROOT/.venv/bin/uvicorn" backend.main:app ) 2>&1 \
    | sed -u 's/^/[backend]  /' &

step 'Starting frontend (vite)'
( cd "$ROOT/frontend" && exec npm run dev ) 2>&1 \
    | sed -u 's/^/[frontend] /' &

if [[ $NO_BROWSER -eq 0 ]] && command -v xdg-open >/dev/null 2>&1; then
    (
        for _ in $(seq 60); do
            if port_open 5173; then xdg-open 'http://localhost:5173' >/dev/null 2>&1; exit 0; fi
            sleep 1
        done
    ) &
fi

echo
printf '\033[32m%s\033[0m\n' 'Bee With Me is starting up:'
echo '  Backend:  http://localhost:8000  (API docs at /docs)'
echo '  Frontend: http://localhost:5173'
echo
printf '\033[90m%s\033[0m\n' 'Press Ctrl+C to stop backend and frontend.'
printf '\033[90m%s\033[0m\n' 'The database keeps running in its container until you stop it yourself:'
printf '\033[90m%s\033[0m\n' "  ${ENGINE:-podman} compose -p bee-with-me -f docker/docker-compose.yaml down"
echo

wait
