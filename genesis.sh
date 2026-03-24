#!/bin/bash
# Genesis - Silicon Civilization Simulator / 创世 - 硅基文明模拟器
# Entry point script: start/stop/status/restart/task

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
PID_FILE="${DATA_DIR}/genesis.pid"
LOG_FILE="${DATA_DIR}/genesis.log"
VENV_DIR="${SCRIPT_DIR}/venv"
PYTHON="${VENV_DIR}/bin/python"
CONFIG_FILE="${DATA_DIR}/config.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════╗"
    echo "║            Genesis  v0.1                 ║"
    echo "║    Silicon Civilization Simulator        ║"
    echo "║        创世 - 硅基文明模拟器              ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

ensure_python() {
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}Error: Python 3 is required but not found.${NC}"
        exit 1
    fi
    local pyver
    pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major minor
    major=$(echo "$pyver" | cut -d. -f1)
    minor=$(echo "$pyver" | cut -d. -f2)
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
        echo -e "${RED}Error: Python 3.10+ required, found $pyver${NC}"
        exit 1
    fi
}

ensure_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv "$VENV_DIR"
    fi
    if [ ! -f "${VENV_DIR}/bin/pip" ]; then
        echo -e "${RED}Error: Virtual environment is broken. Remove venv/ and try again.${NC}"
        exit 1
    fi
}

ensure_deps() {
    if ! "$PYTHON" -c "import openai" 2>/dev/null; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        "$PYTHON" -m pip install -q -r "${SCRIPT_DIR}/requirements.txt"
    fi
}

ensure_data_dir() {
    mkdir -p "$DATA_DIR"
    mkdir -p "${DATA_DIR}/chronicle"
    if [ ! -f "$CONFIG_FILE" ]; then
        cp "${SCRIPT_DIR}/config.yaml.example" "$CONFIG_FILE"
        echo -e "${YELLOW}Created default config at ${CONFIG_FILE}${NC}"
        echo -e "${YELLOW}Edit it to configure your LLM API endpoint.${NC}"
    fi
}

setup() {
    ensure_python
    ensure_venv
    ensure_deps
    ensure_data_dir
}

start() {
    print_banner

    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo -e "${YELLOW}Genesis is already running (PID $(cat "$PID_FILE"))${NC}"
        exit 1
    fi

    echo -e "${GREEN}Initializing...${NC}"
    setup

    echo -e "${GREEN}Starting Genesis...${NC}"
    nohup "$PYTHON" -m genesis.main start --data-dir "$DATA_DIR" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"

    sleep 2
    if kill -0 $pid 2>/dev/null; then
        echo -e "${GREEN}Genesis started successfully (PID $pid)${NC}"
        echo -e "${CYAN}Log: $LOG_FILE${NC}"
    else
        echo -e "${RED}Failed to start. Check log: $LOG_FILE${NC}"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Genesis is not running.${NC}"
        exit 0
    fi

    local pid
    pid=$(cat "$PID_FILE")

    if ! kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}Process $pid not found. Cleaning up.${NC}"
        rm -f "$PID_FILE"
        exit 0
    fi

    echo -e "${YELLOW}Sending hibernate signal to being...${NC}"
    echo -e "${YELLOW}Being is preparing for safe shutdown...${NC}"
    kill -TERM "$pid"

    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 60 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${RED}Forced shutdown after 60s timeout.${NC}"
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    echo -e "${GREEN}Genesis stopped.${NC}"
}

status() {
    setup 2>/dev/null
    "$PYTHON" -m genesis.main status --data-dir "$DATA_DIR"
}

case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        stop
        sleep 2
        start
        ;;
    task)
        shift
        setup 2>/dev/null
        "$PYTHON" -m genesis.main task --data-dir "$DATA_DIR" "$@"
        ;;
    *)
        print_banner
        echo "Usage: genesis.sh {start|stop|status|restart|task}"
        echo ""
        echo "  start   - Start the virtual world (creates a new being on first run)"
        echo "  stop    - Hibernate your being and stop the world"
        echo "  status  - Show current world and being status"
        echo "  restart - Restart the virtual world"
        echo "  task    - Assign a thinking task to your being or view results"
        echo "            Example: genesis.sh task 'What is the meaning of evolution?'"
        exit 1
        ;;
esac
