#!/bin/bash
# Genesis Termux 启动脚本
# 用于在 Termux 环境中启动 Genesis 后端服务

set -e

GENESIS_DIR="${HOME}/genesis"
DATA_DIR="${GENESIS_DIR}/data"
LOG_FILE="${DATA_DIR}/genesis.log"
PYTHON=""  # Will be set by check_python()

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║         Genesis for Termux               ║"
echo "║     Silicon Civilization Engine          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 Python
check_python() {
    # 优先使用 venv Python
    if [ -f "$GENESIS_DIR/venv/bin/python3" ]; then
        PYTHON="$GENESIS_DIR/venv/bin/python3"
        echo -e "${GREEN}Using venv Python: $($PYTHON --version)${NC}"
        return
    fi

    # 回退到系统 Python
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}Python 3 not found. Installing...${NC}"
        pkg install -y python3
    fi
    PYTHON="python3"
    echo -e "${GREEN}Using system Python: $($PYTHON --version)${NC}"
}

# 检查依赖
check_deps() {
    # 注意: pyyaml 的 import 名称是 yaml，不是 pyyaml
    local deps_import=("openai" "websockets" "aiosqlite" "yaml" "msgpack" "cryptography" "zeroconf")
    local deps_pip=("openai" "websockets" "aiosqlite" "pyyaml" "msgpack" "cryptography" "zeroconf")
    local missing=()

    for i in "${!deps_import[@]}"; do
        local dep_import="${deps_import[$i]}"
        local dep_pip="${deps_pip[$i]}"
        if ! "$PYTHON" -c "import $dep_import" 2>/dev/null; then
            missing+=("$dep_pip")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${YELLOW}Installing missing dependencies: ${missing[*]}${NC}"
        "$PYTHON" -m pip install "${missing[@]}"
    fi
    echo -e "${GREEN}All dependencies installed${NC}"
}

# 启动服务
start_service() {
    echo -e "${GREEN}Starting Genesis API server on port 19842...${NC}"

    mkdir -p "$DATA_DIR"

    cd "$GENESIS_DIR"

    # 启动 Genesis 并开启 API
    "$PYTHON" -m genesis.main start \
        --data-dir "$DATA_DIR" \
        --api \
        --api-host 127.0.0.1 \
        --api-port 19842
}

# 主逻辑
main() {
    echo -e "${CYAN}Checking environment...${NC}"
    check_python
    check_deps

    echo ""
    echo -e "${CYAN}Starting Genesis backend...${NC}"
    start_service
}

main "$@"
