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

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║     Genesis Termux Installer            ║"
echo "║     Silicon Civilization Engine          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查存储权限
check_storage() {
    if [ ! -d ~/storage/downloads ]; then
        echo -e "${YELLOW}Storage permission not granted.${NC}"
        echo -e "${CYAN}Requesting storage permission...${NC}"
        termux-setup-storage
        sleep 2
        if [ ! -d ~/storage/downloads ]; then
            echo -e "${RED}Failed to get storage permission.${NC}"
            echo -e "${YELLOW}Please run: termux-setup-storage${NC}"
            exit 1
        fi
    fi
}

# 查找 Genesis 安装文件
find_source_dir() {
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
        if [ -d "$expanded" ] && [ -d "$expanded/genesis" ]; then
            echo "$expanded"
            return 0
        fi
    done

    # 当前目录
    if [ -d "./genesis" ]; then
        echo "."
        return 0
    fi

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

    # 步骤 3: 升级 pip
    echo -e "${CYAN}[3/6] Upgrading pip...${NC}"
    pip install --upgrade pip || pip3 install --upgrade pip || true

    # 步骤 4: 创建安装目录
    echo -e "${CYAN}[4/6] Creating directories...${NC}"
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/data/chronicle"

    # 步骤 5: 复制 Genesis 文件
    echo -e "${CYAN}[5/6] Installing Genesis files...${NC}"

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

    # 安装必要的依赖
    pip install --quiet openai websockets aiosqlite pyyaml msgpack cryptography zeroconf 2>/dev/null || \
    pip3 install --quiet openai websockets aiosqlite pyyaml msgpack cryptography zeroconf 2>/dev/null || {
        echo -e "${YELLOW}Some dependencies may have failed, trying individually...${NC}"
        for dep in openai websockets aiosqlite pyyaml msgpack cryptography zeroconf; do
            pip install "$dep" 2>/dev/null || pip3 install "$dep" 2>/dev/null || true
        done
    }

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
    echo ""
    echo -e "${GREEN}Welcome to the Silicon Civilization!${NC}"
    echo ""
}

main "$@"
