#!/bin/bash
# Genesis Termux 一键安装脚本
# 在 Termux 中运行此脚本安装 Genesis 后端

set -e

GENESIS_REPO="${1:-.}"
INSTALL_DIR="${HOME}/genesis"

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

# 步骤 1: 更新包管理器
echo -e "${CYAN}[1/5] Updating package manager...${NC}"
pkg update -y

# 步骤 2: 安装 Python 和依赖
echo -e "${CYAN}[2/5] Installing Python and build tools...${NC}"
pkg install -y python3 python-tkinter build-essential libffi openssl rust

# 步骤 3: 升级 pip
echo -e "${CYAN}[3/5] Upgrading pip...${NC}"
pip install --upgrade pip

# 步骤 4: 复制 Genesis 文件
echo -e "${CYAN}[4/5] Installing Genesis files...${NC}"
mkdir -p "$INSTALL_DIR"
cp -r "$GENESIS_REPO/genesis" "$INSTALL_DIR/"
cp -r "$GENESIS_REPO/requirements.txt" "$INSTALL_DIR/"
cp -r "$GENESIS_REPO/config.yaml.example" "$INSTALL_DIR/"
cp -r "$GENESIS_REPO/termux/start_genesis.sh" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/start_genesis.sh"

# 步骤 5: 安装 Python 依赖
echo -e "${CYAN}[5/5] Installing Python dependencies...${NC}"
cd "$INSTALL_DIR"
pip install -r requirements.txt

# 完成
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        Installation Complete!            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo -e "  1. Edit config: ${YELLOW}nano ${INSTALL_DIR}/data/config.yaml${NC}"
echo -e "  2. Start service: ${YELLOW}${INSTALL_DIR}/start_genesis.sh${NC}"
echo -e "  3. API will be available at: ${YELLOW}ws://127.0.0.1:19842${NC}"
echo ""
