#!/bin/bash
# Genesis Termux 一键安装脚本
# 在 Termux 中运行此脚本安装 Genesis 后端

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd -P)"

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║     Genesis Termux Installer            ║"
echo "║     Silicon Civilization Engine          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查存储权限
check_storage() {
    if [ -d ~/storage/downloads ]; then
        return 0
    fi

    echo -e "${YELLOW}Storage permission not granted yet.${NC}"
    echo -e "${CYAN}Requesting storage permission from Termux...${NC}"
    termux-setup-storage >/dev/null 2>&1 || true
    echo -e "${YELLOW}If Android shows a file access dialog, tap Allow. Waiting for storage...${NC}"

    local waited=0
    while [ $waited -lt 30 ]; do
        if [ -d ~/storage/downloads ]; then
            echo -e "${GREEN}Storage permission granted${NC}"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    echo -e "${RED}Failed to get storage permission in time.${NC}"
    echo -e "${YELLOW}Please open Termux once, allow file access, then rerun:${NC}"
    echo -e "  ${CYAN}bash \"$SCRIPT_PATH\"${NC}"
    exit 1
}

find_source_candidate() {
    local candidate="$1"
    if [ -z "$candidate" ]; then
        return 1
    fi
    if [ -d "$candidate" ] && [ -d "$candidate/genesis" ]; then
        echo "$candidate"
        return 0
    fi
    return 1
}

# 查找 Genesis 安装文件
find_source_dir() {
    local candidate

    # 优先检查脚本自身所在目录，兼容 bash /storage/.../install.sh 的执行方式
    candidate=$(find_source_candidate "$SCRIPT_DIR") && {
        echo "$candidate"
        return 0
    }

    # 尝试多个可能的位置
    local paths=(
        "~/storage/downloads/Genesis"
        "/storage/emulated/0/Download/Genesis"
        "/sdcard/Download/Genesis"
        "/storage/emulated/0/Downloads/Genesis"
        "/sdcard/Downloads/Genesis"
    )

    for path in "${paths[@]}"; do
        expanded=$(eval echo "$path")
        candidate=$(find_source_candidate "$expanded") && {
            echo "$candidate"
            return 0
        }
    done

    # 当前目录
    candidate=$(find_source_candidate ".") && {
        echo "$candidate"
        return 0
    }

    return 1
}

# 主安装流程
main() {
    echo -e "${CYAN}Checking environment...${NC}"

    # 检查存储权限
    check_storage

    # 查找源目录
    echo -e "${CYAN}Looking for Genesis files...${NC}"
    SOURCE_DIR=$(find_source_dir)

    if [ -z "$SOURCE_DIR" ]; then
        echo -e "${RED}Cannot find Genesis installation files!${NC}"
        echo -e "${YELLOW}Please ensure files are in:${NC}"
        echo "  ~/storage/downloads/Genesis/"
        echo ""
        echo -e "${CYAN}Or run from the directory containing genesis folder:${NC}"
        echo "  bash install.sh"
        exit 1
    fi

    echo -e "${GREEN}Found Genesis files at: $SOURCE_DIR${NC}"

    INSTALL_DIR="${HOME}/genesis"

    # 步骤 1: 更新包管理器
    echo -e "${CYAN}[1/6] Updating package manager...${NC}"
    pkg update -y || true

    # 步骤 2: 安装 Python 和依赖
    echo -e "${CYAN}[2/6] Installing Python and build tools...${NC}"
    pkg install -y python3 python-tkinter build-essential libffi openssl rust || {
        echo -e "${YELLOW}Some packages may have failed, continuing...${NC}"
    }

    # 步骤 3: 检查 pip（Termux 禁止直接升级系统 pip）
    echo -e "${CYAN}[3/6] Checking pip...${NC}"
    if python3 -m pip --version >/dev/null 2>&1; then
        echo -e "${GREEN}pip is available${NC}"
    else
        echo -e "${RED}pip is not available. Please reinstall Python in Termux and retry.${NC}"
        exit 1
    fi

    # 步骤 4: 创建安装目录
    echo -e "${CYAN}[4/6] Creating directories...${NC}"
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/data/chronicle"

    # 步骤 5: 复制 Genesis 文件
    echo -e "${CYAN}[5/6] Installing Genesis files...${NC}"

    # 清理旧源码，避免遗留文件影响升级
    if [ -d "$INSTALL_DIR/genesis" ]; then
        rm -rf "$INSTALL_DIR/genesis"
    fi

    # 复制 genesis 源代码
    if [ -d "$SOURCE_DIR/genesis" ]; then
        echo "  Copying genesis source..."
        cp -r "$SOURCE_DIR/genesis" "$INSTALL_DIR/"
    fi

    # 复制启动脚本
    if [ -f "$SOURCE_DIR/start_genesis.sh" ]; then
        echo "  Installing start script..."
        cp "$SOURCE_DIR/start_genesis.sh" "$INSTALL_DIR/"
        chmod 755 "$INSTALL_DIR/start_genesis.sh"
    fi

    # 复制 requirements.txt，供启动脚本自动自愈 venv
    if [ -f "$SOURCE_DIR/requirements.txt" ]; then
        echo "  Installing requirements file..."
        cp "$SOURCE_DIR/requirements.txt" "$INSTALL_DIR/"
    fi

    # 复制配置模板
    if [ -f "$SOURCE_DIR/config.yaml.example" ]; then
        echo "  Installing config template..."
        cp "$SOURCE_DIR/config.yaml.example" "$INSTALL_DIR/data/"

        # 创建默认配置文件
        if [ ! -f "$INSTALL_DIR/data/config.yaml" ]; then
            cp "$SOURCE_DIR/config.yaml.example" "$INSTALL_DIR/data/config.yaml"
        fi
    fi

    # 步骤 6: 安装 Python 依赖
    echo -e "${CYAN}[6/6] Installing Python dependencies...${NC}"
    cd "$INSTALL_DIR"

    # 完整安装统一使用隔离 venv，避免污染系统 Python
    if [ -d "$INSTALL_DIR/venv" ]; then
        rm -rf "$INSTALL_DIR/venv"
    fi
    python3 -m venv "$INSTALL_DIR/venv"
    VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"

    # venv 内升级 pip 是允许的，不影响 Termux 系统 pip
    "$VENV_PYTHON" -m pip install --upgrade pip --quiet >/dev/null 2>&1 || true

    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        "$VENV_PYTHON" -m pip install --quiet -r "$INSTALL_DIR/requirements.txt" || {
            echo -e "${YELLOW}requirements.txt install failed, trying individually...${NC}"
            for dep in openai websockets aiosqlite pyyaml msgpack cryptography zeroconf; do
                "$VENV_PYTHON" -m pip install "$dep" 2>/dev/null || true
            done
        }
    else
        echo -e "${YELLOW}requirements.txt not found, falling back to built-in dependency list...${NC}"
        for dep in openai websockets aiosqlite pyyaml msgpack cryptography zeroconf; do
            "$VENV_PYTHON" -m pip install "$dep" 2>/dev/null || true
        done
    fi

    # 完成
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        Installation Complete!            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Genesis installed to:${NC} $INSTALL_DIR"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo -e "  1. ${YELLOW}Configure API:${NC} nano $INSTALL_DIR/data/config.yaml"
    echo -e "  2. ${YELLOW}Start service:${NC} $INSTALL_DIR/start_genesis.sh"
    echo -e "  3. ${YELLOW}API endpoint:${NC} ws://127.0.0.1:19842"
    echo -e "  4. ${YELLOW}Tip:${NC} If you launched this from the Android app, just return to the app and wait for auto-start."
    echo ""
    echo -e "${GREEN}Welcome to the Silicon Civilization!${NC}"
    echo ""
}

main "$@"
