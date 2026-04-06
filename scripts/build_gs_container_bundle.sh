#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELPER_SCRIPT="${ROOT_DIR}/scripts/gs_container.sh"
INSTALL_SCRIPT_TEMPLATE="${ROOT_DIR}/scripts/install_gs_container_bundle.sh"

OUTPUT_DIR="${GS_BUNDLE_OUTPUT_DIR:-${ROOT_DIR}/dist}"
BUNDLE_FILE="${GS_BUNDLE_FILE:-}"
BUNDLE_NAME="${GS_BUNDLE_NAME:-genesis-gs-container-bundle.tar.gz}"
IMAGE_ARCHIVE_NAME="${GS_BUNDLE_IMAGE_ARCHIVE_NAME:-genesis-gs-image.tar}"
IMAGE_TAG="${GS_IMAGE_TAG:-genesis-gs:latest}"
SKIP_IMAGE_BUILD=false

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --output-dir DIR      Output directory for the final bundle
  --bundle-file FILE    Final bundle path (overrides --output-dir and name)
  --image-tag TAG       Image tag to export into the bundle
  --skip-image-build    Reuse an existing local image instead of rebuilding it
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --bundle-file)
            BUNDLE_FILE="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --skip-image-build)
            SKIP_IMAGE_BUILD=true
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

if [[ -z "${BUNDLE_FILE}" ]]; then
    mkdir -p "${OUTPUT_DIR}"
    BUNDLE_FILE="${OUTPUT_DIR}/${BUNDLE_NAME}"
else
    mkdir -p "$(dirname "${BUNDLE_FILE}")"
fi

if [[ ! -f "${HELPER_SCRIPT}" ]]; then
    echo "Error: helper script not found: ${HELPER_SCRIPT}" >&2
    exit 1
fi

if [[ ! -f "${INSTALL_SCRIPT_TEMPLATE}" ]]; then
    echo "Error: install script template not found: ${INSTALL_SCRIPT_TEMPLATE}" >&2
    exit 1
fi

bundle_root_name="$(basename "${BUNDLE_FILE}")"
bundle_root_name="${bundle_root_name%.tar.gz}"
bundle_root_name="${bundle_root_name%.tgz}"
bundle_root_name="${bundle_root_name%.tar}"
bundle_root_name="${bundle_root_name:-genesis-gs-container-bundle}"

work_dir="$(mktemp -d /tmp/gs_container_bundle.XXXXXX)"
bundle_dir="${work_dir}/${bundle_root_name}"

cleanup() {
    rm -rf "${work_dir}"
}
trap cleanup EXIT

mkdir -p "${bundle_dir}"

if [[ "${SKIP_IMAGE_BUILD}" != "true" ]]; then
    GS_IMAGE_TAG="${IMAGE_TAG}" bash "${HELPER_SCRIPT}" build
fi

GS_IMAGE_TAG="${IMAGE_TAG}" bash "${HELPER_SCRIPT}" save "${bundle_dir}/${IMAGE_ARCHIVE_NAME}"

cp "${HELPER_SCRIPT}" "${bundle_dir}/gs_container.sh"
chmod +x "${bundle_dir}/gs_container.sh"

cp "${INSTALL_SCRIPT_TEMPLATE}" "${bundle_dir}/install.sh"
chmod +x "${bundle_dir}/install.sh"

created_at_utc="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

cat > "${bundle_dir}/README.txt" <<EOF
gs Container Bundle

1. Copy this bundle tar.gz to the target server.
2. Extract it:
   tar -xzf $(basename "${BUNDLE_FILE}")
3. Enter the extracted directory:
   cd ${bundle_root_name}
4. Install and start gs:
   bash install.sh

Common commands after installation:
  bash gs_container.sh status
  bash gs_container.sh logs
  bash gs_container.sh stop
  bash gs_container.sh start

If you want data in a host directory instead of the default named volume:
  GS_HOST_STATE_DIR=/srv/gs bash install.sh
EOF

cat > "${bundle_dir}/bundle-info.json" <<EOF
{
  "name": "genesis-gs-container-bundle",
  "created_at_utc": "${created_at_utc}",
  "image_tag": "${IMAGE_TAG}",
  "image_archive": "${IMAGE_ARCHIVE_NAME}",
  "entrypoint": "python -m genesis.packaged_cli",
  "install_command": "bash install.sh"
}
EOF

tar -C "${work_dir}" -czf "${BUNDLE_FILE}" "${bundle_root_name}"

if command -v sha256sum >/dev/null 2>&1; then
    (
        cd "$(dirname "${BUNDLE_FILE}")"
        sha256sum "$(basename "${BUNDLE_FILE}")" > "$(basename "${BUNDLE_FILE}").sha256"
    )
fi

echo "Bundle created: ${BUNDLE_FILE}"
if [[ -f "${BUNDLE_FILE}.sha256" ]]; then
    echo "SHA256 file: ${BUNDLE_FILE}.sha256"
fi
echo "Remote install:"
echo "  tar -xzf $(basename "${BUNDLE_FILE}")"
echo "  cd ${bundle_root_name}"
echo "  bash install.sh"
