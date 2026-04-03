#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_NAME="${ARTIFACT_NAME:-genesis-run}"
BUILD_DIR="${ROOT_DIR}/build"
DIST_DIR="${ROOT_DIR}/dist"
ROOT_SPEC_FILE="${ROOT_DIR}/${ARTIFACT_NAME}.spec"
BUILD_VENV_DIR="${ROOT_DIR}/.build/onefile-venv"

detect_python() {
    if command -v python3.11 >/dev/null 2>&1; then
        echo "python3.11"
        return
    fi
    if command -v python3.10 >/dev/null 2>&1; then
        echo "python3.10"
        return
    fi
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi
    echo ""
}

PYTHON_CMD="$(detect_python)"
if [[ -z "${PYTHON_CMD}" ]]; then
    echo "Error: Python 3.10+ is required."
    exit 1
fi

PY_VERSION="$("${PYTHON_CMD}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [[ "${PY_MAJOR}" -lt 3 || ( "${PY_MAJOR}" -eq 3 && "${PY_MINOR}" -lt 10 ) ]]; then
    echo "Error: Python 3.10+ required, found ${PY_VERSION}."
    exit 1
fi

echo "Using ${PYTHON_CMD} (${PY_VERSION})"
mkdir -p "${ROOT_DIR}/.build"

if [[ ! -d "${BUILD_VENV_DIR}" ]]; then
    "${PYTHON_CMD}" -m venv "${BUILD_VENV_DIR}"
fi

VENV_PYTHON="${BUILD_VENV_DIR}/bin/python"
VENV_PIP="${BUILD_VENV_DIR}/bin/pip"
VENV_PYINSTALLER="${BUILD_VENV_DIR}/bin/pyinstaller"

echo "Installing build dependencies into ${BUILD_VENV_DIR}"
"${VENV_PYTHON}" -m pip install --upgrade pip >/dev/null
"${VENV_PIP}" install -q -r "${ROOT_DIR}/requirements.txt" pyinstaller

echo "Cleaning previous build outputs"
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
rm -f "${ROOT_SPEC_FILE}"

DATA_SEP=":"
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OSTYPE:-}" == win32* ]]; then
    DATA_SEP=";"
fi

echo "Building one-file executable..."
"${VENV_PYINSTALLER}" \
    --noconfirm \
    --clean \
    --onefile \
    --name "${ARTIFACT_NAME}" \
    --distpath "${DIST_DIR}" \
    --specpath "${BUILD_DIR}" \
    --add-data "${ROOT_DIR}/config.yaml.example${DATA_SEP}." \
    "${ROOT_DIR}/genesis/packaged_cli.py"

# Keep repository root clean even if PyInstaller behavior changes.
rm -f "${ROOT_SPEC_FILE}"

echo ""
echo "Build completed."
echo "Executable: ${DIST_DIR}/${ARTIFACT_NAME}"
echo ""
echo "Run locally:"
echo "  ${DIST_DIR}/${ARTIFACT_NAME} start"
echo ""
echo "Share this single file to another machine with the same OS/CPU architecture."
