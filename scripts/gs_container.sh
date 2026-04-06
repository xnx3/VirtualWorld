#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKERFILE_PATH="${ROOT_DIR}/docker/gs/Dockerfile"
DEFAULT_RUNTIME_ENV_FILE="${SCRIPT_DIR}/.gs_container.env"

if [[ -f "${DEFAULT_RUNTIME_ENV_FILE}" ]]; then
    # shellcheck disable=SC1090
    . "${DEFAULT_RUNTIME_ENV_FILE}"
fi

IMAGE_TAG="${GS_IMAGE_TAG:-genesis-gs:latest}"
CONTAINER_NAME="${GS_CONTAINER_NAME:-genesis-gs}"
STATE_VOLUME="${GS_STATE_VOLUME:-${CONTAINER_NAME}-state}"
HOST_STATE_DIR="${GS_HOST_STATE_DIR:-}"
API_PORT="${GS_API_PORT:-19842}"
P2P_PORT="${GS_P2P_PORT:-19841}"
DISCOVERY_PORT="${GS_DISCOVERY_PORT:-19840}"
CONTAINER_ENGINE="${GS_CONTAINER_ENGINE:-}"
USE_HOST_NETWORK="${GS_USE_HOST_NETWORK:-false}"
ENV_FILE="${GS_ENV_FILE:-}"
ENABLE_API="${GS_ENABLE_API:-false}"
PYTHON_BASE_IMAGE="${GS_PYTHON_BASE_IMAGE:-public.ecr.aws/docker/library/python:3.11-slim-bookworm}"
APT_MIRROR_URL="${GS_APT_MIRROR_URL:-}"
PIP_INDEX_URL="${GS_PIP_INDEX_URL:-}"
PIP_EXTRA_INDEX_URL="${GS_PIP_EXTRA_INDEX_URL:-}"

usage() {
    cat <<EOF
Usage: $0 <command> [args...]

Commands:
  build              Build the gs container image
  load [archive]     Load an image archive into docker/podman
  save [archive]     Save image to a tar archive
  start              Start the gs container in background
  stop               Stop and remove the gs container
  restart            Restart the gs container
  status             Show gs status from inside the running container
  task <text...>     Send a task to gs
  lang [en|zh]       Show or set language
  logs               Follow container logs
  shell              Open a shell inside the running container

Environment overrides:
  GS_CONTAINER_ENGINE   docker or podman
  GS_IMAGE_TAG          image tag (default: genesis-gs:latest)
  GS_CONTAINER_NAME     container name (default: genesis-gs)
  GS_IMAGE_ARCHIVE      default tar archive used by load/save
  GS_STATE_VOLUME       named volume mounted to /var/lib/gs
  GS_HOST_STATE_DIR     optional host directory mounted instead of the named volume
  GS_API_PORT           host port -> container 19842/tcp
  GS_P2P_PORT           host port -> container 19841/tcp
  GS_DISCOVERY_PORT     host port -> container 19840/udp
  GS_USE_HOST_NETWORK   true to use --network host instead of -p mappings
  GS_ENV_FILE           optional env-file passed to docker/podman run
  GS_ENABLE_API         true to enable the WebSocket API inside the container
  GS_PYTHON_BASE_IMAGE  builder/runtime base image
  GS_APT_MIRROR_URL     optional Debian mirror base URL used during apt-get
  GS_PIP_INDEX_URL      optional pip mirror URL used during image build
  GS_PIP_EXTRA_INDEX_URL optional extra pip index used during image build

Note:
  If ${DEFAULT_RUNTIME_ENV_FILE} exists next to this script, it is loaded
  automatically before applying the defaults above.
  If you change container env/ports/volume settings, use 'restart' so the
  container is recreated with the new runtime arguments.
EOF
}

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
    echo "Error: docker or podman is required." >&2
    exit 1
}

ENGINE="$(resolve_engine)"

container_exists() {
    "${ENGINE}" container inspect "${CONTAINER_NAME}" >/dev/null 2>&1
}

container_running() {
    [[ "$("${ENGINE}" container inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || true)" == "true" ]]
}

image_exists() {
    "${ENGINE}" image inspect "${IMAGE_TAG}" >/dev/null 2>&1
}

ensure_image() {
    if image_exists; then
        return
    fi
    echo "Image ${IMAGE_TAG} not found locally. Building it now..."
    build_image
}

ensure_running() {
    if ! container_running; then
        echo "Error: container ${CONTAINER_NAME} is not running." >&2
        exit 1
    fi
}

exec_flags() {
    if [[ -t 0 && -t 1 ]]; then
        echo "-it"
        return
    fi
    echo "-i"
}

build_image() {
    "${ENGINE}" build \
        -t "${IMAGE_TAG}" \
        --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
        --build-arg "APT_MIRROR_URL=${APT_MIRROR_URL}" \
        --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
        --build-arg "PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}" \
        -f "${DOCKERFILE_PATH}" \
        "${ROOT_DIR}"
}

default_archive_path() {
    local safe_tag
    safe_tag="${IMAGE_TAG//\//_}"
    safe_tag="${safe_tag//:/_}"
    echo "${ROOT_DIR}/dist/${safe_tag}.tar"
}

load_image() {
    local archive
    archive="${1:-${GS_IMAGE_ARCHIVE:-$(default_archive_path)}}"

    if [[ ! -f "${archive}" ]]; then
        echo "Error: image archive not found: ${archive}" >&2
        exit 1
    fi

    "${ENGINE}" load -i "${archive}"
}

save_image() {
    local archive
    ensure_image
    archive="${1:-${GS_IMAGE_ARCHIVE:-$(default_archive_path)}}"

    mkdir -p "$(dirname "${archive}")"
    "${ENGINE}" save -o "${archive}" "${IMAGE_TAG}"
    echo "Saved image archive: ${archive}"
}

start_container() {
    ensure_image

    if container_running; then
        echo "Container ${CONTAINER_NAME} is already running."
        return
    fi

    if container_exists; then
        "${ENGINE}" start "${CONTAINER_NAME}" >/dev/null
        echo "Container ${CONTAINER_NAME} started."
        return
    fi

    local state_mount state_desc
    if [[ -n "${HOST_STATE_DIR}" ]]; then
        mkdir -p "${HOST_STATE_DIR}"
        state_mount="${HOST_STATE_DIR}:/var/lib/gs"
        if [[ "${ENGINE}" == "podman" ]]; then
            state_mount="${state_mount}:Z"
        fi
        state_desc="Host state directory: ${HOST_STATE_DIR}"
    else
        state_mount="${STATE_VOLUME}:/var/lib/gs"
        state_desc="State volume: ${STATE_VOLUME}"
    fi

    local args=(
        run
        -d
        --name
        "${CONTAINER_NAME}"
        --restart
        unless-stopped
        -e
        "GS_ENABLE_API=${ENABLE_API}"
        -v
        "${state_mount}"
    )

    if [[ -n "${ENV_FILE}" ]]; then
        args+=(--env-file "${ENV_FILE}")
    fi

    if [[ "${USE_HOST_NETWORK}" == "true" ]]; then
        args+=(--network host)
    else
        args+=(
            -p "${DISCOVERY_PORT}:19840/udp"
            -p "${P2P_PORT}:19841/tcp"
            -p "${API_PORT}:19842/tcp"
        )
        if [[ "${ENGINE}" == "docker" ]]; then
            args+=(--add-host host.docker.internal:host-gateway)
        fi
    fi

    args+=("${IMAGE_TAG}" start)

    "${ENGINE}" "${args[@]}" >/dev/null

    echo "Container ${CONTAINER_NAME} started."
    echo "${state_desc}"
    if [[ "${USE_HOST_NETWORK}" == "true" ]]; then
        echo "Networking: host"
    else
        echo "Ports: UDP ${DISCOVERY_PORT}->19840, TCP ${P2P_PORT}->19841, TCP ${API_PORT}->19842"
    fi
}

stop_container() {
    if ! container_exists; then
        echo "Container ${CONTAINER_NAME} does not exist."
        return
    fi

    if container_running; then
        "${ENGINE}" exec -i "${CONTAINER_NAME}" gs stop >/dev/null 2>&1 || true
        "${ENGINE}" stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    fi

    "${ENGINE}" rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    echo "Container ${CONTAINER_NAME} stopped and removed."
}

status_container() {
    ensure_running
    "${ENGINE}" exec $(exec_flags) "${CONTAINER_NAME}" gs status
}

task_container() {
    ensure_running
    if [[ $# -eq 0 ]]; then
        echo "Error: task text is required." >&2
        exit 1
    fi
    "${ENGINE}" exec $(exec_flags) "${CONTAINER_NAME}" gs task "$@"
}

lang_container() {
    ensure_running
    "${ENGINE}" exec $(exec_flags) "${CONTAINER_NAME}" gs lang "$@"
}

logs_container() {
    ensure_running
    "${ENGINE}" logs -f "${CONTAINER_NAME}"
}

shell_container() {
    ensure_running
    "${ENGINE}" exec $(exec_flags) "${CONTAINER_NAME}" bash
}

COMMAND="${1:-}"
if [[ -z "${COMMAND}" ]]; then
    usage
    exit 1
fi
shift || true

case "${COMMAND}" in
    build)
        build_image
        ;;
    load)
        load_image "$@"
        ;;
    save)
        save_image "$@"
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    restart)
        stop_container
        start_container
        ;;
    status)
        status_container
        ;;
    task)
        task_container "$@"
        ;;
    lang)
        lang_container "$@"
        ;;
    logs)
        logs_container
        ;;
    shell)
        shell_container
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: ${COMMAND}" >&2
        usage
        exit 1
        ;;
esac
