#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELPER_SCRIPT="${ROOT_DIR}/scripts/gs_container.sh"
BUNDLE_SCRIPT="${ROOT_DIR}/scripts/build_gs_container_bundle.sh"

IMAGE_TAG="${GS_IMAGE_TAG:-genesis-gs:latest}"
BUILD_BUNDLE=false
OUTPUT_DIR=""

usage() {
    cat <<EOF
Usage: $0 [options]

One-command rebuild for the latest gs container image after Python code changes.

Options:
  --bundle           Also create an offline deployment bundle after building the image
  --image-tag TAG    Image tag to build (default: genesis-gs:latest)
  --output-dir DIR   Output directory for the bundle when --bundle is used
  -h, --help         Show this help

Examples:
  bash scripts/build_latest_gs_image.sh
  bash scripts/build_latest_gs_image.sh --bundle

  GS_APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn \\
  GS_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \\
  bash scripts/build_latest_gs_image.sh --bundle
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bundle)
            BUILD_BUNDLE=true
            shift
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
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

GS_IMAGE_TAG="${IMAGE_TAG}" bash "${HELPER_SCRIPT}" build

if [[ "${BUILD_BUNDLE}" == "true" ]]; then
    bundle_args=(--skip-image-build --image-tag "${IMAGE_TAG}")
    if [[ -n "${OUTPUT_DIR}" ]]; then
        bundle_args+=(--output-dir "${OUTPUT_DIR}")
    fi
    GS_IMAGE_TAG="${IMAGE_TAG}" bash "${BUNDLE_SCRIPT}" "${bundle_args[@]}"
fi

echo "Latest gs image is ready: ${IMAGE_TAG}"
if [[ "${BUILD_BUNDLE}" == "true" ]]; then
    echo "Offline bundle was generated as well."
fi
