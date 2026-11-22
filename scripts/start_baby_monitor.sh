#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIRECTORY="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_DIRECTORY}"

RUNTIME_DIRECTORY="${TMPDIR:-/tmp}/baby-monitor"
PID_FILE="${RUNTIME_DIRECTORY}/mediamtx.pid"
LOG_FILE="${RUNTIME_DIRECTORY}/mediamtx.log"
MEDIAMTX_BINARY="${PROJECT_DIRECTORY}/bin/mediamtx"

mkdir -p "${RUNTIME_DIRECTORY}"

if [ ! -x "${MEDIAMTX_BINARY}" ]; then
    "${PROJECT_DIRECTORY}/scripts/install_mediamtx.sh"
fi

if [ -f "${PID_FILE}" ]; then
    previous_pid="$(cat "${PID_FILE}")"
    if [ -n "${previous_pid}" ] && kill -0 "${previous_pid}" 2>/dev/null; then
        kill "${previous_pid}" || true
        sleep 1
        kill -9 "${previous_pid}" 2>/dev/null || true
    fi
    rm -f "${PID_FILE}"
fi

pkill -f '/bin/mediamtx ' 2>/dev/null || true
pkill -f 'mediamtx-rpicamera-' 2>/dev/null || true
sleep 1

"${MEDIAMTX_BINARY}" "${PROJECT_DIRECTORY}/mediamtx.yml" >> "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"

if [ -f "${PROJECT_DIRECTORY}/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "${PROJECT_DIRECTORY}/venv/bin/activate"
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
