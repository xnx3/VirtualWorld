#!/bin/bash
# Genesis Flutter App 构建脚本
# 用于在本地构建 APK

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Genesis Flutter App Build Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查 Flutter
echo -e "${YELLOW}Checking Flutter...${NC}"
if ! command -v flutter &> /dev/null; then
    echo -e "${RED}Error: Flutter not found!${NC}"
    echo "Please install Flutter: https://docs.flutter.dev/get-started/install"
    exit 1
fi

FLUTTER_VERSION=$(flutter --version | head -1)
echo -e "${GREEN}✓ Flutter: $FLUTTER_VERSION${NC}"

# 检查 Android SDK
echo -e "${YELLOW}Checking Android SDK...${NC}"
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    echo -e "${RED}Error: ANDROID_HOME not set!${NC}"
    echo "Please install Android Studio or Android SDK"
    exit 1
fi
echo -e "${GREEN}✓ Android SDK: ${ANDROID_HOME:-$ANDROID_SDK_ROOT}${NC}"

# 接受 Android 许可
echo -e "${YELLOW}Accepting Android licenses...${NC}"
flutter doctor --android-licenses 2>/dev/null || true

# 获取依赖
echo -e "${YELLOW}Getting dependencies...${NC}"
flutter pub get

# 构建 APK
echo -e "${YELLOW}Building APK...${NC}"
flutter build apk --release

# 检查结果
APK_PATH="build/app/outputs/flutter-apk/app-release.apk"
if [ -f "$APK_PATH" ]; then
    APK_SIZE=$(du -h "$APK_PATH" | cut -f1)
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Build Success!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "APK Path: ${YELLOW}$APK_PATH${NC}"
    echo -e "APK Size: ${YELLOW}$APK_SIZE${NC}"
    echo ""
    echo "You can install it on your Android device:"
    echo "  adb install $APK_PATH"
    echo ""
else
    echo -e "${RED}Build failed! APK not found.${NC}"
    exit 1
fi