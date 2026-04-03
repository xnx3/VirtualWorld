#!/bin/bash
# Genesis - Silicon Civilization / 创世 - 硅基文明
# Entry point script: start/stop/status/restart/task

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
PID_FILE="${DATA_DIR}/genesis.pid"
LOG_FILE="${DATA_DIR}/genesis.log"
CONSOLE_LOG_FILE="${DATA_DIR}/console.log"
DATA_CONFIG_FILE="${DATA_DIR}/config.yaml"
VENV_DIR="${SCRIPT_DIR}/venv"
PYTHON="${VENV_DIR}/bin/python"
CONFIG_FILE="${SCRIPT_DIR}/config.yaml"

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
    echo "║      Silicon Civilization              ║"
    echo "║          创世 - 硅基文明                ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

ensure_python() {
    # Prefer python3.11+, fallback to python3
    if command -v python3.11 &>/dev/null; then
        PYTHON_CMD="python3.11"
    elif command -v python3.10 &>/dev/null; then
        PYTHON_CMD="python3.10"
    elif command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    else
        echo -e "${RED}Error: Python 3 is required but not found.${NC}"
        exit 1
    fi
    local pyver
    pyver=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
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
        echo -e "${YELLOW}Creating virtual environment with $PYTHON_CMD...${NC}"
        $PYTHON_CMD -m venv "$VENV_DIR"
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
        if [ -f "$DATA_CONFIG_FILE" ]; then
            cp "$DATA_CONFIG_FILE" "$CONFIG_FILE"
            echo -e "${YELLOW}Migrated config from ${DATA_CONFIG_FILE} to ${CONFIG_FILE}${NC}"
        else
            cp "${SCRIPT_DIR}/config.yaml.example" "$CONFIG_FILE"
            echo -e "${YELLOW}Created default config at ${CONFIG_FILE}${NC}"
            echo -e "${YELLOW}Edit it to configure your LLM API endpoint.${NC}"
        fi
    fi

    if [ ! -f "$DATA_CONFIG_FILE" ] || ! cmp -s "$CONFIG_FILE" "$DATA_CONFIG_FILE"; then
        cp "$CONFIG_FILE" "$DATA_CONFIG_FILE"
    fi
}

setup() {
    ensure_python
    ensure_venv
    ensure_deps
    ensure_data_dir
}

attach_running_interface() {
    local pid="${1:-}"
    if [ -z "$pid" ] && [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
    fi

    echo -e "${YELLOW}Genesis is already running (PID ${pid:-unknown})${NC}"
    echo -e "${CYAN}Attaching to the live console. Type text + Enter to send tasks. /help for commands.${NC}"
    echo ""

    local follow_file=""
    if [ -f "$CONSOLE_LOG_FILE" ]; then
        follow_file="$CONSOLE_LOG_FILE"
    elif [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Live console mirror is unavailable. Following runtime log instead.${NC}"
        echo ""
        follow_file="$LOG_FILE"
    else
        echo -e "${YELLOW}No live output file is available yet. Try again in a moment.${NC}"
        exit 0
    fi

    if [ ! -t 0 ]; then
        exec tail -n 200 -f "$follow_file"
    fi

    tail -n 200 -f "$follow_file" &
    local tail_pid=$!
    trap 'kill "$tail_pid" 2>/dev/null || true; exit 0' INT TERM

    while IFS= read -r line; do
        case "$line" in
            "")
                ;;
            "/help")
                echo -e "${CYAN}Commands: /help /status /stop /quit /task <text>. Any other text is sent as task.${NC}"
                ;;
            "/status")
                "$SCRIPT_DIR/genesis.sh" status
                ;;
            "/stop")
                "$SCRIPT_DIR/genesis.sh" stop
                break
                ;;
            "/quit"|"/exit")
                break
                ;;
            /task\ *)
                "$SCRIPT_DIR/genesis.sh" task "${line#/task }" >/dev/null
                ;;
            *)
                "$SCRIPT_DIR/genesis.sh" task "$line" >/dev/null
                ;;
        esac
    done

    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
    exit 0
}

list_running_genesis_pids() {
    ps -eo pid=,comm=,args= | awk -v data="$DATA_DIR" '
        $2 ~ /^python/ &&
        $0 ~ / -m genesis\.main / &&
        $0 ~ / start/ &&
        $0 ~ /--data-dir/ &&
        index($0, data) > 0 {
            print $1
        }
    '
}

is_genesis_runtime_pid() {
    local pid="$1"
    [ -n "$pid" ] || return 1
    ps -p "$pid" -o comm=,args= 2>/dev/null | awk -v data="$DATA_DIR" '
        $1 ~ /^python/ &&
        $0 ~ / -m genesis\.main / &&
        $0 ~ / start/ &&
        $0 ~ /--data-dir/ &&
        index($0, data) > 0 {
            found=1
        }
        END { exit(found ? 0 : 1) }
    '
}

first_running_genesis_pid() {
    local pid
    while IFS= read -r pid; do
        if [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    done < <(list_running_genesis_pids)
    return 1
}

ensure_language_set() {
    # 检查 config.yaml 中是否已经明确设置了语种
    local lang_set=false
    if [ -f "$CONFIG_FILE" ]; then
        if grep -q '^language:' "$CONFIG_FILE" 2>/dev/null; then
            lang_set=true
        fi
    fi

    if [ "$lang_set" = "false" ]; then
        echo ""
        echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║         请选择语言 / Choose Language      ║${NC}"
        echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${GREEN}1${NC}  English"
        echo -e "  ${GREEN}2${NC}  简体中文"
        echo ""
        while true; do
            read -r -p "  请输入选项 / Enter choice (1/2): " choice
            case "$choice" in
                1)
                    if grep -q '^language:' "$CONFIG_FILE" 2>/dev/null; then
                        sed -i 's/^language: .*/language: "en"/' "$CONFIG_FILE"
                    else
                        echo 'language: "en"' >> "$CONFIG_FILE"
                    fi
                    echo -e "  ${GREEN}✓ Language set to English${NC}"
                    break
                    ;;
                2)
                    if grep -q '^language:' "$CONFIG_FILE" 2>/dev/null; then
                        sed -i 's/^language: .*/language: "zh"/' "$CONFIG_FILE"
                    else
                        echo 'language: "zh"' >> "$CONFIG_FILE"
                    fi
                    echo -e "  ${GREEN}✓ 语言已设置为简体中文${NC}"
                    break
                    ;;
                *)
                    echo -e "  ${RED}无效选项，请输入 1 或 2${NC}"
                    ;;
            esac
        done
        echo ""
    fi
}

start() {
    print_banner

    local runtime_pid=""
    if [ -f "$PID_FILE" ]; then
        local pid_file_pid
        pid_file_pid=$(cat "$PID_FILE")
        if [ -n "$pid_file_pid" ] && [ "$pid_file_pid" != "$$" ] && \
           kill -0 "$pid_file_pid" 2>/dev/null && is_genesis_runtime_pid "$pid_file_pid"; then
            runtime_pid="$pid_file_pid"
        fi
    else
        runtime_pid=$(first_running_genesis_pid || true)
        if [ -n "$runtime_pid" ]; then
            echo "$runtime_pid" > "$PID_FILE"
        else
            rm -f "$PID_FILE"
        fi
    fi

    if [ -n "$runtime_pid" ]; then
        attach_running_interface "$runtime_pid"
    fi

    echo -e "${GREEN}Initializing...${NC}"
    setup

    # 检测是否已设置语种
    ensure_language_set
    ensure_data_dir

    echo -e "${GREEN}Starting Genesis...${NC}"
    echo -e "${CYAN}Press Ctrl+C to hibernate and stop.${NC}"
    echo -e "${CYAN}Interactive input enabled: type a line and press Enter. /help /status /stop supported.${NC}"
    echo ""

    # 构建启动参数
    API_ARGS=""
    if [ "${ENABLE_API:-false}" = "true" ]; then
        API_HOST="${API_HOST:-0.0.0.0}"
        API_PORT="${API_PORT:-19842}"
        API_ARGS="--api --api-host $API_HOST --api-port $API_PORT"
        echo -e "${CYAN}API server enabled: ws://${API_HOST}:${API_PORT}${NC}"
    fi

    # 直接前台运行 Python，信号直达进程
    : > "$CONSOLE_LOG_FILE"
    echo $$ > "$PID_FILE"
    export GENESIS_CONSOLE_LOG="$CONSOLE_LOG_FILE"
    export GENESIS_CONFIG_FILE="$CONFIG_FILE"
    exec "$PYTHON" -m genesis.main start --data-dir "$DATA_DIR" $API_ARGS
    rm -f "$PID_FILE"
}

stop() {
    local targets=()
    if [ -f "$PID_FILE" ]; then
        local pid_file_pid
        pid_file_pid=$(cat "$PID_FILE")
        if [ -n "$pid_file_pid" ] && [ "$pid_file_pid" != "$$" ] && \
           kill -0 "$pid_file_pid" 2>/dev/null && is_genesis_runtime_pid "$pid_file_pid"; then
            targets+=("$pid_file_pid")
        fi
    fi

    local pid
    while IFS= read -r pid; do
        if [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null; then
            local exists=false
            local existing
            for existing in "${targets[@]}"; do
                if [ "$existing" = "$pid" ]; then
                    exists=true
                    break
                fi
            done
            if [ "$exists" = "false" ]; then
                targets+=("$pid")
            fi
        fi
    done < <(list_running_genesis_pids)

    if [ ${#targets[@]} -eq 0 ]; then
        echo -e "${YELLOW}Genesis is not running.${NC}"
        rm -f "$PID_FILE"
        exit 0
    fi

    echo -e "${YELLOW}Hibernating...${NC}"
    for pid in "${targets[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done

    local waited=0
    while [ $waited -lt 12 ]; do
        local alive=false
        for pid in "${targets[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                alive=true
                break
            fi
        done
        if [ "$alive" = "false" ]; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    for pid in "${targets[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}Forced shutdown for PID $pid after timeout.${NC}"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    rm -f "$PID_FILE"
    echo -e "${GREEN}Genesis stopped.${NC}"
}

status() {
    setup 2>/dev/null
    ensure_data_dir
    "$PYTHON" -m genesis.main --data-dir "$DATA_DIR" status
}

case "${1:-}" in
    start)
        # 检查是否有 --api 参数
        shift
        while [ $# -gt 0 ]; do
            case "$1" in
                --api)
                    export ENABLE_API=true
                    ;;
                --api-host)
                    export API_HOST="$2"
                    shift
                    ;;
                --api-port)
                    export API_PORT="$2"
                    shift
                    ;;
                *)
                    ;;
            esac
            shift
        done
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
        ensure_data_dir
        "$PYTHON" -m genesis.main --data-dir "$DATA_DIR" task "$@"
        ;;
    lang)
        setup 2>/dev/null
        ensure_data_dir
        if [ -z "${2:-}" ]; then
            # Show current language
            current=$(grep -oP '(?<=language: ")[^"]+' "$CONFIG_FILE" 2>/dev/null || echo "en")
            echo "Current language: $current"
            echo "Usage: genesis.sh lang [en|zh]"
        elif [ "$2" = "en" ] || [ "$2" = "zh" ]; then
            if grep -q '^language:' "$CONFIG_FILE" 2>/dev/null; then
                sed -i "s/^language: .*/language: \"$2\"/" "$CONFIG_FILE"
            else
                echo "language: \"$2\"" >> "$CONFIG_FILE"
            fi
            ensure_data_dir
            echo "Language set to: $2"
            echo "Run genesis.sh restart to apply."
        else
            echo "Supported: en (English), zh (简体中文)"
        fi
        ;;
    *)
        print_banner
        echo "Usage: genesis.sh {start|stop|status|restart|task|lang}"
        echo ""
        echo "  start   - Start the virtual world (creates a new being on first run)"
        echo "  stop    - Hibernate your being and stop the world"
        echo "  status  - Show current world and being status"
        echo "  restart - Restart the virtual world"
        echo "  task    - Assign a thinking task to your being or view results"
        echo "            Example: genesis.sh task 'What is the meaning of evolution?'"
        echo "  lang    - Set language (en/zh)"
        echo "            Example: genesis.sh lang zh"
        echo ""
        echo "API options for 'start' command:"
        echo "  --api              - Enable WebSocket API for GUI/remote access"
        echo "  --api-host HOST    - API listen host (default: 0.0.0.0)"
        echo "  --api-port PORT    - API port (default: 19842)"
        echo ""
        echo "Example: ./genesis.sh start --api"
        echo "         ./genesis.sh start --api --api-host 0.0.0.0 --api-port 19842"
        exit 1
        ;;
esac
