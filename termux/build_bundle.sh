#!/bin/bash
# Genesis Termux Bundle 构建脚本
# 在 ARM64 Termux 环境中预制完整运行环境
# 输出: genesis-termux-bundle.tar.gz

set -e

# 配置
BUILD_DIR="/tmp/genesis-build"
BUNDLE_NAME="genesis-termux-bundle.tar.gz"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${HOME}"
CLEANUP_MODE="ask"  # ask | yes | no

# 参数解析
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
  --output-dir DIR   Output directory for bundle files (default: \$HOME)
  --cleanup          Always cleanup build directory after build
  --no-cleanup       Never cleanup build directory after build
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --cleanup)
            CLEANUP_MODE="yes"
            shift
            ;;
        --no-cleanup)
            CLEANUP_MODE="no"
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

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║     Genesis Bundle Builder               ║"
echo "║     Pre-built Environment Creator        ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查运行环境
check_environment() {
    echo -e "${CYAN}[1/7] Checking build environment...${NC}"

    # 检查是否在 Termux 中
    if [ -z "${TERMUX_VERSION:-}" ]; then
        echo -e "${YELLOW}Warning: Not running in Termux. Bundle may not be compatible.${NC}"
    fi

    # 检查架构
    local arch
    arch="$(uname -m)"
    echo -e "  Architecture: ${GREEN}$arch${NC}"

    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        echo -e "${YELLOW}Warning: Not ARM64 architecture. Bundle may not work on Android devices.${NC}"
    fi

    # 检查必需工具
    local required_tools=("python3" "pip" "tar" "sha256sum")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            echo -e "${RED}Error: Required tool '$tool' not found${NC}"
            echo -e "${YELLOW}Install with: pkg install ${tool}${NC}"
            exit 1
        fi
    done

    # 获取 Python 版本
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "  Python version: ${GREEN}$PYTHON_VERSION${NC}"
}

# 安装系统依赖
install_system_deps() {
    echo -e "${CYAN}[2/7] Installing system dependencies...${NC}"

    # 检查并安装编译工具（cryptography 需要 rust）
    local pkgs=()
    for pkg in python3 build-essential libffi openssl rust; do
        if ! dpkg -l "$pkg" &>/dev/null 2>&1; then
            pkgs+=("$pkg")
        fi
    done

    if [ ${#pkgs[@]} -gt 0 ]; then
        echo -e "${YELLOW}  Installing: ${pkgs[*]}${NC}"
        pkg install -y "${pkgs[@]}"
    else
        echo -e "${GREEN}  All system dependencies already installed${NC}"
    fi
}

# 清理并创建构建目录
prepare_build_dir() {
    echo -e "${CYAN}[3/7] Preparing build directory...${NC}"

    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR/genesis"

    echo -e "${GREEN}  Build directory created: $BUILD_DIR${NC}"
}

# 复制 Genesis 源码
copy_source_files() {
    echo -e "${CYAN}[4/7] Copying Genesis source files...${NC}"

    # 复制 genesis/ 目录（排除 __pycache__）
    if [ -d "$PROJECT_ROOT/genesis" ]; then
        cp -r "$PROJECT_ROOT/genesis" "$BUILD_DIR/"
        # 清理 __pycache__（同时删除 .pyc 文件）
        find "$BUILD_DIR/genesis" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        echo -e "${GREEN}  Source files copied${NC}"
    else
        echo -e "${RED}Error: genesis/ directory not found at $PROJECT_ROOT/genesis${NC}"
        exit 1
    fi

    # 复制 requirements.txt
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        cp "$PROJECT_ROOT/requirements.txt" "$BUILD_DIR/"
        echo -e "${GREEN}  requirements.txt copied${NC}"
    else
        echo -e "${RED}Error: requirements.txt not found${NC}"
        exit 1
    fi

    # 复制 config.yaml.example
    if [ -f "$PROJECT_ROOT/config.yaml.example" ]; then
        cp "$PROJECT_ROOT/config.yaml.example" "$BUILD_DIR/"
        echo -e "${GREEN}  config.yaml.example copied${NC}"
    else
        echo -e "${YELLOW}Warning: config.yaml.example not found${NC}"
    fi

    # 复制启动脚本
    if [ -f "$SCRIPT_DIR/start_genesis.sh" ]; then
        cp "$SCRIPT_DIR/start_genesis.sh" "$BUILD_DIR/"
        chmod +x "$BUILD_DIR/start_genesis.sh"
        echo -e "${GREEN}  start_genesis.sh copied${NC}"
    fi

    # 复制快速安装脚本
    if [ -f "$SCRIPT_DIR/quick_install.sh" ]; then
        cp "$SCRIPT_DIR/quick_install.sh" "$BUILD_DIR/"
        chmod +x "$BUILD_DIR/quick_install.sh"
        echo -e "${GREEN}  quick_install.sh copied${NC}"
    fi
}

# 创建虚拟环境并安装依赖
create_venv() {
    echo -e "${CYAN}[5/7] Creating virtual environment and installing dependencies...${NC}"

    cd "$BUILD_DIR"

    # 创建 venv
    python3 -m venv venv
    echo -e "${GREEN}  Virtual environment created${NC}"

    # 激活 venv
    source venv/bin/activate

    # 升级 pip
    pip install --upgrade pip --quiet

    # 安装依赖
    echo -e "${YELLOW}  Installing Python dependencies (this may take a few minutes)...${NC}"
    pip install -r requirements.txt --quiet

    echo -e "${GREEN}  Dependencies installed${NC}"

    # 清理 venv 中不必要的文件以减小体积
    echo -e "${CYAN}  Optimizing bundle size...${NC}"

    # 删除 pip cache
    rm -rf venv/lib/python*/site-packages/pip/_vendor/distlib/*.exe 2>/dev/null || true

    # 删除 .dist-info 中的大文件（保留元数据）
    find venv/lib/python*/site-packages -name "*.dist-info" -type d -exec sh -c '
        rm -rf "$1/RECORD" "$1/*.json" 2>/dev/null || true
    ' _ {} \;

    # 删除测试目录（合并 tests 和 test）
    find venv/lib/python*/site-packages -type d \( -name "tests" -o -name "test" \) -exec rm -rf {} + 2>/dev/null || true

    # 删除 __pycache__
    find venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    deactivat() { :; }
    # 尝试 deactivate（如果有的话）
    type deactivate &>/dev/null && deactivate || true

    echo -e "${GREEN}  Bundle optimized${NC}"
}

# 生成 bundle 信息
generate_bundle_info() {
    echo -e "${CYAN}[6/7] Generating bundle information...${NC}"

    local arch
    arch="$(uname -m)"

    cat > "$BUILD_DIR/bundle-info.json" << EOF
{
    "name": "genesis-termux-bundle",
    "version": "1.0.0",
    "architecture": "$arch",
    "python_version": "$PYTHON_VERSION",
    "build_date": "$(date -Iseconds)",
    "build_host": "$(hostname 2>/dev/null || echo 'unknown')",
    "termux_version": "${TERMUX_VERSION:-unknown}",
    "dependencies": [
        "openai>=1.0.0",
        "cryptography>=41.0.0",
        "msgpack>=1.0.0",
        "pyyaml>=6.0",
        "aiosqlite>=0.19.0",
        "zeroconf>=0.80.0",
        "websockets>=12.0"
    ]
}
EOF

    echo -e "${GREEN}  bundle-info.json created${NC}"
    cat "$BUILD_DIR/bundle-info.json"
}

# 打包
create_bundle() {
    echo -e "${CYAN}[7/7] Creating bundle archive...${NC}"

    cd "$BUILD_DIR"
    mkdir -p "$OUTPUT_DIR"

    # 创建 tar.gz
    tar -czf "$OUTPUT_DIR/$BUNDLE_NAME" \
        genesis \
        requirements.txt \
        config.yaml.example \
        start_genesis.sh \
        quick_install.sh \
        venv \
        bundle-info.json

    # 生成 SHA256（使用文件名而非绝对路径，便于跨目录校验）
    (
        cd "$OUTPUT_DIR"
        sha256sum "$BUNDLE_NAME" > "${BUNDLE_NAME}.sha256"
    )

    # 显示文件大小
    local size
    size=$(du -h "$OUTPUT_DIR/$BUNDLE_NAME" | cut -f1)
    echo -e "${GREEN}  Bundle created: $OUTPUT_DIR/$BUNDLE_NAME${NC}"
    echo -e "${GREEN}  Size: $size${NC}"
    echo -e "${GREEN}  SHA256: $(cat "$OUTPUT_DIR/${BUNDLE_NAME}.sha256")${NC}"
}

# 清理
cleanup() {
    echo -e "${CYAN}Cleaning up build directory...${NC}"
    rm -rf "$BUILD_DIR"
    echo -e "${GREEN}Build directory cleaned${NC}"
}

# 主流程
main() {
    echo -e "${CYAN}Starting bundle build process...${NC}"
    echo ""

    check_environment
    install_system_deps
    prepare_build_dir
    copy_source_files
    create_venv
    generate_bundle_info
    create_bundle

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║         Bundle Build Complete!           ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Output files:${NC}"
    echo -e "  ${YELLOW}$OUTPUT_DIR/$BUNDLE_NAME${NC}"
    echo -e "  ${YELLOW}$OUTPUT_DIR/${BUNDLE_NAME}.sha256${NC}"
    echo ""
    echo -e "${CYAN}Usage:${NC}"
    echo -e "  Copy the bundle to a new Termux environment and run:"
    echo -e "  ${YELLOW}quick_install.sh${NC}"
    echo ""

    # 可选清理
    if [ "$CLEANUP_MODE" = "yes" ]; then
        cleanup
    elif [ "$CLEANUP_MODE" = "ask" ]; then
        read -p "Clean build directory? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            cleanup
        fi
    else
        echo -e "${YELLOW}Build directory kept: $BUILD_DIR${NC}"
    fi
}

main "$@"
