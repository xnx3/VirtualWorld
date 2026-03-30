#!/bin/bash
# Genesis Termux 启动脚本
# 用于在 Termux 环境中启动 Genesis 后端服务

set -e

GENESIS_DIR="${HOME}/genesis"
DATA_DIR="${GENESIS_DIR}/data"
LOG_FILE="${DATA_DIR}/genesis.log"
VENV_DIR="${GENESIS_DIR}/venv"
REQUIREMENTS_FILE="${GENESIS_DIR}/requirements.txt"
SYSTEM_PYTHON=""
PYTHON=""
LAST_MISSING_DEPS=""

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

# 检查安装文件
check_genesis_files() {
    if [ ! -d "$GENESIS_DIR/genesis" ]; then
        echo -e "${RED}Genesis source files not found at $GENESIS_DIR/genesis${NC}"
        echo -e "${YELLOW}Please run install.sh or quick_install.sh first.${NC}"
        exit 1
    fi

    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        echo -e "${RED}requirements.txt not found at $REQUIREMENTS_FILE${NC}"
        echo -e "${YELLOW}Automatic venv repair requires requirements.txt. Please reinstall Genesis.${NC}"
        exit 1
    fi
}

ensure_system_python() {
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}Python 3 not found. Installing...${NC}"
        pkg install -y python3
    fi

    SYSTEM_PYTHON="python3"

    if ! "$SYSTEM_PYTHON" -m pip --version >/dev/null 2>&1; then
        echo -e "${RED}pip is not available in Termux Python. Please reinstall python3 and retry.${NC}"
        exit 1
    fi

    echo -e "${GREEN}System Python ready: $($SYSTEM_PYTHON --version)${NC}"
}

python_minor_version() {
    local python_bin="$1"
    "$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "unknown"
}

check_python_modules() {
    local python_bin="$1"
    local deps_import=("openai" "websockets" "aiosqlite" "yaml" "msgpack" "cryptography" "zeroconf")
    local deps_pip=("openai" "websockets" "aiosqlite" "pyyaml" "msgpack" "cryptography" "zeroconf")
    local missing=()

    for i in "${!deps_import[@]}"; do
        local dep_import="${deps_import[$i]}"
        local dep_pip="${deps_pip[$i]}"
        if ! "$python_bin" -c "import $dep_import" 2>/dev/null; then
            missing+=("$dep_pip")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        LAST_MISSING_DEPS="${missing[*]}"
        return 1
    fi

    LAST_MISSING_DEPS=""
    return 0
}

ensure_build_dependencies() {
    echo -e "${CYAN}Ensuring build dependencies for Python runtime repair...${NC}"
    pkg install -y python3 build-essential libffi openssl rust || {
        echo -e "${RED}Failed to install build dependencies required for venv repair.${NC}"
        exit 1
    }
}

rebuild_venv() {
    local reason="$1"
    local venv_python="$VENV_DIR/bin/python3"

    echo -e "${YELLOW}$reason${NC}"
    echo -e "${CYAN}Rebuilding Genesis venv automatically...${NC}"

    ensure_build_dependencies

    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi

    "$SYSTEM_PYTHON" -m venv "$VENV_DIR"

    if [ ! -x "$venv_python" ]; then
        echo -e "${RED}Failed to create venv Python at $venv_python${NC}"
        exit 1
    fi

    "$venv_python" -m pip install --upgrade pip --quiet >/dev/null 2>&1 || true
    "$venv_python" -m pip install --prefer-binary -r "$REQUIREMENTS_FILE"

    if ! check_python_modules "$venv_python"; then
        echo -e "${RED}venv repair finished but dependencies are still missing: $LAST_MISSING_DEPS${NC}"
        exit 1
    fi

    PYTHON="$venv_python"
    echo -e "${GREEN}Using repaired venv Python: $($PYTHON --version)${NC}"
}

# 检查 Python
check_python() {
    check_genesis_files
    ensure_system_python

    local system_python_version
    local venv_python="$VENV_DIR/bin/python3"
    local venv_python_version

    system_python_version="$(python_minor_version "$SYSTEM_PYTHON")"

    if [ ! -x "$venv_python" ]; then
        rebuild_venv "Bundled venv not found. Creating a local runtime now..."
        return
    fi

    venv_python_version="$(python_minor_version "$venv_python")"
    if [ "$venv_python_version" = "unknown" ]; then
        rebuild_venv "Bundled venv Python cannot start. Recreating runtime..."
        return
    fi

    if [ "$system_python_version" != "unknown" ] && [ "$venv_python_version" != "$system_python_version" ]; then
        rebuild_venv "Bundled venv Python ($venv_python_version) differs from system Python ($system_python_version). Recreating runtime..."
        return
    fi

    if ! check_python_modules "$venv_python"; then
        rebuild_venv "Bundled venv is missing dependencies: $LAST_MISSING_DEPS"
        return
    fi

    PYTHON="$venv_python"
    echo -e "${GREEN}Using bundled venv Python: $($PYTHON --version)${NC}"
}

# 检查依赖
check_deps() {
    if ! check_python_modules "$PYTHON"; then
        echo -e "${YELLOW}Missing dependencies detected: $LAST_MISSING_DEPS${NC}"
        echo -e "${CYAN}Repairing active Python environment...${NC}"
        "$PYTHON" -m pip install --prefer-binary -r "$REQUIREMENTS_FILE"

        if ! check_python_modules "$PYTHON"; then
            echo -e "${RED}Dependencies are still missing after repair: $LAST_MISSING_DEPS${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}All dependencies installed${NC}"
}

# 启动服务
start_service() {
    echo -e "${GREEN}Starting Genesis API server on port 19842...${NC}"

    mkdir -p "$DATA_DIR"
    echo -e "${CYAN}Log file:${NC} $LOG_FILE"

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
