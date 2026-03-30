#!/bin/bash
# Genesis Termux 快速安装脚本
# 解压预制 bundle，实现一键快速部署
# 用法: ./quick_install.sh [--force] [--from-url <url>]

set -e

# 配置
INSTALL_DIR="${HOME}/genesis"
BUNDLE_NAME="genesis-termux-bundle.tar.gz"
SHARED_STORAGE="${HOME}/storage/downloads/Genesis"
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd -P)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 参数解析
FORCE_INSTALL=false
BUNDLE_URL=""
BUNDLE_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_INSTALL=true
            shift
            ;;
        --from-url)
            BUNDLE_URL="$2"
            shift 2
            ;;
        --bundle)
            BUNDLE_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --force         Force reinstall even if already installed"
            echo "  --from-url URL  Download bundle from URL"
            echo "  --bundle FILE   Use specified bundle file"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║     Genesis Quick Installer              ║"
echo "║     One-Click Deployment                 ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

ensure_storage_access() {
    if [ -d "${HOME}/storage/downloads" ]; then
        return 0
    fi

    echo -e "${YELLOW}Shared storage is not ready yet.${NC}"
    echo -e "${CYAN}Requesting storage permission from Termux...${NC}"
    termux-setup-storage >/dev/null 2>&1 || true
    echo -e "${YELLOW}If Android shows a file access dialog, tap Allow. Waiting for storage...${NC}"

    local waited=0
    while [ $waited -lt 30 ]; do
        if [ -d "${HOME}/storage/downloads" ]; then
            echo -e "${GREEN}  Storage permission granted${NC}"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    echo -e "${RED}Storage permission is still unavailable.${NC}"
    echo -e "${YELLOW}Please open Termux once, allow file access, then rerun:${NC}"
    echo -e "  ${CYAN}bash \"$SCRIPT_PATH\"${NC}"
    exit 1
}

# 步骤 1: 检查 Python
check_python() {
    echo -e "${CYAN}[1/5] Checking Python...${NC}"

    if ! command -v python3 &>/dev/null; then
        echo -e "${YELLOW}Python 3 not found. Installing...${NC}"
        pkg install -y python3
    fi

    SYSTEM_PYTHON=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}  System Python: $SYSTEM_PYTHON${NC}"
}

# 步骤 2: 查找 bundle 文件
find_bundle() {
    echo -e "${CYAN}[2/5] Locating bundle file...${NC}"

    # 如果指定了文件
    if [ -n "$BUNDLE_FILE" ] && [ -f "$BUNDLE_FILE" ]; then
        BUNDLE_PATH="$BUNDLE_FILE"
        echo -e "${GREEN}  Using specified bundle: $BUNDLE_PATH${NC}"
        return 0
    fi

    # 如果需要从 URL 下载
    if [ -n "$BUNDLE_URL" ]; then
        echo -e "${YELLOW}  Downloading bundle from: $BUNDLE_URL${NC}"
        BUNDLE_PATH="/tmp/$BUNDLE_NAME"
        if command -v curl &>/dev/null; then
            curl -L -o "$BUNDLE_PATH" "$BUNDLE_URL"
        elif command -v wget &>/dev/null; then
            wget -O "$BUNDLE_PATH" "$BUNDLE_URL"
        else
            echo -e "${RED}Error: Neither curl nor wget available${NC}"
            exit 1
        fi
        echo -e "${GREEN}  Bundle downloaded${NC}"
        return 0
    fi

    # 优先检查脚本所在目录，兼容 bash /storage/.../quick_install.sh
    if [ -f "$SCRIPT_DIR/$BUNDLE_NAME" ]; then
        BUNDLE_PATH="$SCRIPT_DIR/$BUNDLE_NAME"
        echo -e "${GREEN}  Found bundle next to script: $BUNDLE_PATH${NC}"
        return 0
    fi

    ensure_storage_access

    # 查找本地 bundle
    local search_paths=(
        "$SHARED_STORAGE/$BUNDLE_NAME"
        "/storage/emulated/0/Download/Genesis/$BUNDLE_NAME"
        "$(pwd)/$BUNDLE_NAME"
        "${HOME}/$BUNDLE_NAME"
        "/sdcard/Download/Genesis/$BUNDLE_NAME"
    )

    for path in "${search_paths[@]}"; do
        if [ -f "$path" ]; then
            BUNDLE_PATH="$path"
            echo -e "${GREEN}  Found bundle: $BUNDLE_PATH${NC}"
            return 0
        fi
    done

    echo -e "${RED}Error: Bundle file not found${NC}"
    echo -e "${YELLOW}Searched locations:${NC}"
    for path in "${search_paths[@]}"; do
        echo -e "  ${YELLOW}- $path${NC}"
    done
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo -e "  0. In Termux, run ${YELLOW}termux-setup-storage${NC} and tap Allow"
    echo -e "  1. Copy bundle to one of the locations above"
    echo -e "  2. Use ${YELLOW}--from-url <url>${NC} to download"
    echo -e "  3. Use ${YELLOW}--bundle <file>${NC} to specify bundle path"
    exit 1
}

# 步骤 3: 验证 bundle
verify_bundle() {
    echo -e "${CYAN}[3/5] Verifying bundle...${NC}"

    # 检查 SHA256（如果存在）
    local sha256_file="${BUNDLE_PATH}.sha256"
    if [ -f "$sha256_file" ]; then
        if command -v sha256sum &>/dev/null; then
            echo -e "${YELLOW}  Verifying SHA256 checksum...${NC}"
            local expected_hash
            local actual_hash
            expected_hash="$(awk 'NR==1 {print $1}' "$sha256_file")"
            actual_hash="$(sha256sum "$BUNDLE_PATH" | awk '{print $1}')"

            if [ -n "$expected_hash" ] && [ "$expected_hash" = "$actual_hash" ]; then
                echo -e "${GREEN}  Checksum verified${NC}"
            else
                echo -e "${RED}Error: Checksum verification failed${NC}"
                echo -e "${YELLOW}The bundle may be corrupted. Try downloading again.${NC}"
                exit 1
            fi
        else
            echo -e "${YELLOW}  sha256sum not found, skipping checksum verification${NC}"
        fi
    else
        echo -e "${YELLOW}  No SHA256 file found, skipping checksum verification${NC}"
    fi

    # 显示 bundle 信息（直接提取，避免两次 tar 操作）
    echo -e "${YELLOW}  Bundle info:${NC}"
    tar -xzf "$BUNDLE_PATH" -O bundle-info.json 2>/dev/null | head -20 || echo -e "${YELLOW}  (No bundle info available)${NC}"
}

# 步骤 4: 安装
install_bundle() {
    echo -e "${CYAN}[4/5] Installing Genesis...${NC}"

    # 检查是否已安装
    if [ -d "$INSTALL_DIR" ] && [ "$FORCE_INSTALL" = false ]; then
        echo -e "${YELLOW}  Genesis already installed at $INSTALL_DIR${NC}"
        echo -e "${YELLOW}  Use --force to reinstall${NC}"
        exit 0
    fi

    # 备份现有数据目录
    if [ -d "$INSTALL_DIR/data" ]; then
        echo -e "${YELLOW}  Backing up existing data directory...${NC}"
        mv "$INSTALL_DIR/data" "${INSTALL_DIR}.data.bak"
    fi

    # 删除旧安装
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}  Removing existing installation...${NC}"
        rm -rf "$INSTALL_DIR"
    fi

    # 创建安装目录
    mkdir -p "$INSTALL_DIR"

    # 解压 bundle
    echo -e "${YELLOW}  Extracting bundle (this may take a moment)...${NC}"
    tar -xzf "$BUNDLE_PATH" -C "$INSTALL_DIR" --strip-components=0

    # 恢复数据目录
    if [ -d "${INSTALL_DIR}.data.bak" ]; then
        mv "${INSTALL_DIR}.data.bak" "$INSTALL_DIR/data"
    fi

    # 创建数据目录（如果不存在）
    mkdir -p "$INSTALL_DIR/data"

    # 复制默认配置（如果不存在）
    if [ ! -f "$INSTALL_DIR/data/config.yaml" ] && [ -f "$INSTALL_DIR/config.yaml.example" ]; then
        cp "$INSTALL_DIR/config.yaml.example" "$INSTALL_DIR/data/config.yaml"
        echo -e "${GREEN}  Default config created${NC}"
    fi

    echo -e "${GREEN}  Installation complete${NC}"
}

# 步骤 5: 验证安装
verify_installation() {
    echo -e "${CYAN}[5/5] Verifying installation...${NC}"

    # 读取 bundle 信息
    if [ -f "$INSTALL_DIR/bundle-info.json" ]; then
        echo -e "${GREEN}  Bundle info:${NC}"
        cat "$INSTALL_DIR/bundle-info.json" | head -10
    fi

    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        echo -e "${GREEN}  requirements.txt ready for automatic venv repair${NC}"
    else
        echo -e "${YELLOW}  requirements.txt not found, automatic venv repair will be limited${NC}"
    fi

    # 检查 venv Python
    local venv_python="$INSTALL_DIR/venv/bin/python3"
    if [ -f "$venv_python" ]; then
        echo -e "${GREEN}  venv Python found${NC}"

        # 检查版本兼容性
        VENV_PYTHON=$("$venv_python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "unknown")

        if [ "$VENV_PYTHON" != "unknown" ] && [ "$VENV_PYTHON" != "$SYSTEM_PYTHON" ]; then
            echo -e "${YELLOW}Warning: venv Python ($VENV_PYTHON) differs from system Python ($SYSTEM_PYTHON)${NC}"
            echo -e "${YELLOW}The first start will automatically rebuild the venv if needed.${NC}"
        else
            echo -e "${GREEN}  Python version compatible: $VENV_PYTHON${NC}"
        fi

        # 验证关键依赖
        echo -e "${YELLOW}  Verifying dependencies...${NC}"
        local deps=("openai" "websockets" "aiosqlite" "yaml" "msgpack" "cryptography" "zeroconf")
        local failed=()

        for dep in "${deps[@]}"; do
            if ! "$venv_python" -c "import $dep" 2>/dev/null; then
                failed+=("$dep")
            fi
        done

        if [ ${#failed[@]} -gt 0 ]; then
            echo -e "${YELLOW}  Some dependencies not available in venv: ${failed[*]}${NC}"
            echo -e "${YELLOW}  start_genesis.sh will automatically repair the venv on first start${NC}"
        else
            echo -e "${GREEN}  All dependencies verified${NC}"
        fi
    else
        echo -e "${YELLOW}  venv not found, start_genesis.sh will create one automatically${NC}"
    fi

    # 检查启动脚本
    if [ -f "$INSTALL_DIR/start_genesis.sh" ]; then
        chmod +x "$INSTALL_DIR/start_genesis.sh"
        echo -e "${GREEN}  Start script ready${NC}"
    fi

    # 检查源码
    if [ -d "$INSTALL_DIR/genesis" ]; then
        echo -e "${GREEN}  Genesis source files present${NC}"
    fi
}

# 显示完成信息
show_complete() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║       Installation Complete!             ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Installation directory:${NC}"
    echo -e "  ${YELLOW}$INSTALL_DIR${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo -e "  1. Edit config (optional):"
    echo -e "     ${YELLOW}nano $INSTALL_DIR/data/config.yaml${NC}"
    echo ""
    echo -e "  2. Start Genesis service manually if needed:"
    echo -e "     ${YELLOW}$INSTALL_DIR/start_genesis.sh${NC}"
    echo ""
    echo -e "  3. If this was launched from the Android app, you can now return to the app and wait for automatic startup."
    echo ""
    echo -e "  4. Connect from Flutter app to:"
    echo -e "     ${YELLOW}ws://127.0.0.1:19842${NC}"
    echo ""
}

# 主流程
main() {
    check_python
    find_bundle
    verify_bundle
    install_bundle
    verify_installation
    show_complete
}

main "$@"
