#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd -P)"
HELPER_SCRIPT="${SCRIPT_DIR}/gs_container.sh"
RUNTIME_ENV_FILE="${SCRIPT_DIR}/.gs_container.env"

IMAGE_ARCHIVE="${GS_IMAGE_ARCHIVE:-${SCRIPT_DIR}/genesis-gs-image.tar}"
IMAGE_TAG="${GS_IMAGE_TAG:-genesis-gs:latest}"
CONTAINER_ENGINE="${GS_CONTAINER_ENGINE:-}"
CONTAINER_NAME="${GS_CONTAINER_NAME:-genesis-gs}"
STATE_VOLUME="${GS_STATE_VOLUME:-}"
HOST_STATE_DIR="${GS_HOST_STATE_DIR:-}"
API_PORT="${GS_API_PORT:-19842}"
P2P_PORT="${GS_P2P_PORT:-19841}"
DISCOVERY_PORT="${GS_DISCOVERY_PORT:-19840}"
ENABLE_API="${GS_ENABLE_API:-false}"
USE_HOST_NETWORK="${GS_USE_HOST_NETWORK:-false}"
START_AFTER_LOAD=true

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --engine ENGINE          docker or podman
  --archive FILE           Image archive to load (default: ./genesis-gs-image.tar)
  --image-tag TAG          Image tag expected after load
  --container-name NAME    Container name (default: genesis-gs)
  --state-volume NAME      Named volume for /var/lib/gs
  --host-state-dir DIR     Host directory for /var/lib/gs instead of a named volume
  --api-port PORT          Host port for container 19842/tcp
  --p2p-port PORT          Host port for container 19841/tcp
  --discovery-port PORT    Host port for container 19840/udp
  --enable-api             Enable the optional WebSocket API
  --host-network           Use host networking instead of -p mappings
  --no-start               Only load the image; do not start the container
  -h, --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine)
            CONTAINER_ENGINE="$2"
            shift 2
            ;;
        --archive)
            IMAGE_ARCHIVE="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --container-name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --state-volume)
            STATE_VOLUME="$2"
            shift 2
            ;;
        --host-state-dir)
            HOST_STATE_DIR="$2"
            shift 2
            ;;
        --api-port)
            API_PORT="$2"
            shift 2
            ;;
        --p2p-port)
            P2P_PORT="$2"
            shift 2
            ;;
        --discovery-port)
            DISCOVERY_PORT="$2"
            shift 2
            ;;
        --enable-api)
            ENABLE_API=true
            shift
            ;;
        --host-network)
            USE_HOST_NETWORK=true
            shift
            ;;
        --no-start)
            START_AFTER_LOAD=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -z "${STATE_VOLUME}" ]]; then
    STATE_VOLUME="${CONTAINER_NAME}-state"
fi

if [[ ! -f "${IMAGE_ARCHIVE}" ]]; then
    echo "Error: image archive not found: ${IMAGE_ARCHIVE}" >&2
    exit 1
fi

if [[ ! -f "${HELPER_SCRIPT}" ]]; then
    echo "Error: helper script not found: ${HELPER_SCRIPT}" >&2
    exit 1
fi

resolve_engine() {
    if [[ -n "${CONTAINER_ENGINE}" ]]; then
        echo "${CONTAINER_ENGINE}"
        return
    fi
    if command -v docker >/dev/null 2>&1; then
        echo "docker"
        return
    fi
    if command -v podman >/dev/null 2>&1; then
        echo "podman"
        return
    fi
    echo "Error: docker or podman is required on the target server." >&2
    exit 1
}

normalize_loaded_image_tag() {
    local localhost_tag
    if "${ENGINE}" image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
        return
    fi

    localhost_tag="localhost/${IMAGE_TAG}"
    if "${ENGINE}" image inspect "${localhost_tag}" >/dev/null 2>&1; then
        "${ENGINE}" tag "${localhost_tag}" "${IMAGE_TAG}"
    fi
}

write_runtime_env() {
    {
        printf 'GS_CONTAINER_ENGINE=%q\n' "${ENGINE}"
        printf 'GS_IMAGE_TAG=%q\n' "${IMAGE_TAG}"
        printf 'GS_CONTAINER_NAME=%q\n' "${CONTAINER_NAME}"
        printf 'GS_STATE_VOLUME=%q\n' "${STATE_VOLUME}"
        printf 'GS_HOST_STATE_DIR=%q\n' "${HOST_STATE_DIR}"
        printf 'GS_API_PORT=%q\n' "${API_PORT}"
        printf 'GS_P2P_PORT=%q\n' "${P2P_PORT}"
        printf 'GS_DISCOVERY_PORT=%q\n' "${DISCOVERY_PORT}"
        printf 'GS_ENABLE_API=%q\n' "${ENABLE_API}"
        printf 'GS_USE_HOST_NETWORK=%q\n' "${USE_HOST_NETWORK}"
    } > "${RUNTIME_ENV_FILE}"
}

ENGINE="$(resolve_engine)"

write_runtime_env

GS_CONTAINER_ENGINE="${ENGINE}" \
GS_IMAGE_TAG="${IMAGE_TAG}" \
bash "${HELPER_SCRIPT}" load "${IMAGE_ARCHIVE}"

normalize_loaded_image_tag

if [[ "${START_AFTER_LOAD}" == "true" ]]; then
    GS_CONTAINER_ENGINE="${ENGINE}" \
    GS_IMAGE_TAG="${IMAGE_TAG}" \
    GS_CONTAINER_NAME="${CONTAINER_NAME}" \
    GS_STATE_VOLUME="${STATE_VOLUME}" \
    GS_HOST_STATE_DIR="${HOST_STATE_DIR}" \
    GS_API_PORT="${API_PORT}" \
    GS_P2P_PORT="${P2P_PORT}" \
    GS_DISCOVERY_PORT="${DISCOVERY_PORT}" \
    GS_ENABLE_API="${ENABLE_API}" \
    GS_USE_HOST_NETWORK="${USE_HOST_NETWORK}" \
    bash "${HELPER_SCRIPT}" start
fi

echo "Runtime settings saved to: ${RUNTIME_ENV_FILE}"
echo "Next commands:"
echo "  bash gs_container.sh status"
echo "  bash gs_container.sh logs"
echo "  bash gs_container.sh stop"
