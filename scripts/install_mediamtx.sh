#!/usr/bin/env bash
set -euo pipefail

MEDIAMTX_VERSION="v1.21.4"
PROJECT_DIRECTORY="$(cd "$(dirname "$0")/.." && pwd)"
BINARY_DIRECTORY="${PROJECT_DIRECTORY}/bin"
ARCHIVE_NAME="mediamtx_${MEDIAMTX_VERSION}_linux_arm64.tar.gz"
DOWNLOAD_URL="https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/${ARCHIVE_NAME}"

mkdir -p "${BINARY_DIRECTORY}"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

curl -fL --retry 3 -o "${temporary_directory}/${ARCHIVE_NAME}" "${DOWNLOAD_URL}"
tar -xzf "${temporary_directory}/${ARCHIVE_NAME}" -C "${temporary_directory}" mediamtx
install -m 755 "${temporary_directory}/mediamtx" "${BINARY_DIRECTORY}/mediamtx"

echo "Installed MediaMTX ${MEDIAMTX_VERSION} to ${BINARY_DIRECTORY}/mediamtx"
