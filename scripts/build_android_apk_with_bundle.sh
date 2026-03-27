#!/bin/bash
# 一键构建 Android APK（可选预构建并植入 Termux 后端 bundle）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FLUTTER_DIR="$ROOT_DIR/client/flutter"
TERMUX_DIR="$ROOT_DIR/termux"

BUNDLE_FILE=""
SKIP_BUNDLE_BUILD=false
BUILD_MODE="release"
SPLIT_PER_ABI=false

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
  --bundle-file PATH     Use an existing genesis-termux-bundle.tar.gz
  --skip-bundle-build    Skip building bundle (use existing bundle if present)
  --debug                Build debug APK (default: release)
  --release              Build release APK
  --split-per-abi        Build split-per-abi APKs
  -h, --help             Show this help

Examples:
  $0
  $0 --bundle-file /path/to/genesis-termux-bundle.tar.gz
  $0 --skip-bundle-build --release
EOF
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: command not found: $1"
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bundle-file)
            BUNDLE_FILE="$2"
            shift 2
            ;;
        --skip-bundle-build)
            SKIP_BUNDLE_BUILD=true
            shift
            ;;
        --debug)
            BUILD_MODE="debug"
            shift
            ;;
        --release)
            BUILD_MODE="release"
            shift
            ;;
        --split-per-abi)
            SPLIT_PER_ABI=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

require_cmd flutter
require_cmd sha256sum

BUNDLE_TARGET="$TERMUX_DIR/genesis-termux-bundle.tar.gz"
BUNDLE_SHA_TARGET="$TERMUX_DIR/genesis-termux-bundle.tar.gz.sha256"

if [[ -n "$BUNDLE_FILE" ]]; then
    if [[ ! -f "$BUNDLE_FILE" ]]; then
        echo "Error: bundle file not found: $BUNDLE_FILE"
        exit 1
    fi

    echo "Using provided bundle: $BUNDLE_FILE"
    cp -f "$BUNDLE_FILE" "$BUNDLE_TARGET"

    if [[ -f "${BUNDLE_FILE}.sha256" ]]; then
        cp -f "${BUNDLE_FILE}.sha256" "$BUNDLE_SHA_TARGET"
    else
        (
            cd "$TERMUX_DIR"
            sha256sum "$(basename "$BUNDLE_TARGET")" > "$(basename "$BUNDLE_SHA_TARGET")"
        )
    fi
elif [[ "$SKIP_BUNDLE_BUILD" == false ]]; then
    echo "Building Termux bundle..."
    "$TERMUX_DIR/build_bundle.sh" --output-dir "$TERMUX_DIR" --cleanup
fi

if [[ -f "$BUNDLE_TARGET" ]]; then
    echo "Bundle ready: $BUNDLE_TARGET"
else
    echo "Warning: bundle not found, APK will fallback to full install mode"
fi

echo "Building Flutter APK ($BUILD_MODE)..."
cd "$FLUTTER_DIR"
flutter pub get

if [[ "$BUILD_MODE" == "release" ]]; then
    if [[ "$SPLIT_PER_ABI" == true ]]; then
        flutter build apk --release --split-per-abi
    else
        flutter build apk --release
    fi
else
    flutter build apk --debug
fi

echo "Build completed."

APK_OUTPUT_DIR="$FLUTTER_DIR/build/app/outputs/flutter-apk"
echo "APK outputs:"
ls -lh "$APK_OUTPUT_DIR"/app-*.apk

if command -v unzip >/dev/null 2>&1; then
    DEFAULT_APK="$APK_OUTPUT_DIR/app-${BUILD_MODE}.apk"
    if [[ -f "$DEFAULT_APK" ]]; then
        echo ""
        echo "Verifying key embedded assets in $(basename "$DEFAULT_APK"):"
        unzip -l "$DEFAULT_APK" | grep -E "assets/(genesis/|install\.sh|start_genesis\.sh|quick_install\.sh|termux-.*\.apk|genesis-termux-bundle\.tar\.gz)" || true
    fi
fi
