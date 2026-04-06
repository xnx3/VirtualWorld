#!/usr/bin/env bash

set -euo pipefail

STATE_DIR="${GS_STATE_DIR:-/var/lib/gs}"
DATA_DIR="${GS_DATA_DIR:-${STATE_DIR}/data}"
CONFIG_PATH="${GS_CONFIG_PATH:-${STATE_DIR}/config.yaml}"
API_HOST="${GS_API_HOST:-0.0.0.0}"
API_PORT="${GS_API_PORT:-19842}"
ENABLE_API="${GS_ENABLE_API:-false}"

mkdir -p "${STATE_DIR}"

if [[ $# -eq 0 ]]; then
    set -- start
fi

COMMAND="$1"
shift || true

ARGS=(
    python
    -m
    genesis.packaged_cli
    --data-dir
    "${DATA_DIR}"
    --config
    "${CONFIG_PATH}"
)

if [[ "${COMMAND}" == "start" && "${ENABLE_API}" == "true" ]]; then
    ARGS+=(
        --api
        --api-host
        "${API_HOST}"
        --api-port
        "${API_PORT}"
    )
fi

ARGS+=("${COMMAND}")
ARGS+=("$@")

exec "${ARGS[@]}"
