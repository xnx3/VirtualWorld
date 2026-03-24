"""Rich console output for real-time display of being activities.

Shows everything the silicon being does, thinks, feels, sees, and says
directly in the terminal — so the Creator God can watch the world live.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime


# ANSI colors
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    # Colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright
    BRED = "\033[91m"
    BGREEN = "\033[92m"
    BYELLOW = "\033[93m"
    BBLUE = "\033[94m"
    BMAGENTA = "\033[95m"
    BCYAN = "\033[96m"


# Icons for different activity types
ICONS = {
    "think": "💭",
    "speak": "💬",
    "teach": "📖",
    "learn": "📚",
    "create": "✨",
    "explore": "🔍",
    "compete": "⚔️",
    "meditate": "🧘",
    "build_shelter": "🏠",
    "move": "🚶",
    "perceive": "👁️",
    "disaster": "⚡",
    "death": "💀",
    "birth": "🌟",
    "treasure": "💎",
    "spirit": "🔮",
    "priest": "⛩️",
    "vote": "🗳️",
    "hibernate": "😴",
    "wake": "☀️",
    "task": "📋",
    "knowledge": "🧠",
    "deep_think": "🌀",
    "world": "🌍",
    "tick": "⏱️",
    "error": "❌",
}


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _write(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def separator(char: str = "─", width: int = 60) -> None:
    _write(f"{C.DIM}{char * width}{C.RESET}")


def header(title: str) -> None:
    _write(f"\n{C.BOLD}{C.CYAN}{'═' * 60}{C.RESET}")
    _write(f"{C.BOLD}{C.CYAN}  {title}{C.RESET}")
    _write(f"{C.BOLD}{C.CYAN}{'═' * 60}{C.RESET}\n")


def tick_header(tick: int, being_name: str, spirit_str: str, phase: str) -> None:
    _write("")
    separator("━")
    _write(
        f"{C.BOLD}{ICONS['tick']} Tick {tick}{C.RESET}  "
        f"{C.CYAN}{being_name}{C.RESET}  "
        f"{C.MAGENTA}{spirit_str}{C.RESET}  "
        f"{C.DIM}Phase: {phase}{C.RESET}  "
        f"{C.DIM}{_timestamp()}{C.RESET}"
    )
    separator("━")


def perceive(location: str, nearby: list[dict], danger: float = 0,
             region_desc: str = "") -> None:
    _write(f"  {ICONS['perceive']} {C.BLUE}{C.BOLD}感知环境{C.RESET}")
    _write(f"     {C.DIM}位置:{C.RESET} {location}")
    if region_desc:
        _write(f"     {C.DIM}环境:{C.RESET} {region_desc[:80]}")
    if danger > 0.3:
        _write(f"     {C.RED}危险等级: {danger:.1f}{C.RESET}")
    if nearby:
        names = ", ".join(
            f"{C.CYAN}{b.get('name', '?')}{C.RESET}"
            f"{C.DIM}(evo:{b.get('evolution', 0):.2f}){C.RESET}"
            for b in nearby[:5]
        )
        _write(f"     {C.DIM}附近:{C.RESET} {names}")
    else:
        _write(f"     {C.DIM}附近: (无人){C.RESET}")


def think(being_name: str, thought: str) -> None:
    _write(f"  {ICONS['think']} {C.YELLOW}{C.BOLD}思考{C.RESET}")
    # Wrap long thoughts
    for line in _wrap(thought, 70):
        _write(f"     {C.ITALIC}{C.YELLOW}{line}{C.RESET}")


def decide(being_name: str, action_type: str, target: str | None,
           details: str) -> None:
    icon = ICONS.get(action_type, "▶")
    color = {
        "speak": C.GREEN, "teach": C.BGREEN, "learn": C.BCYAN,
        "create": C.BMAGENTA, "explore": C.BBLUE, "compete": C.BRED,
        "meditate": C.MAGENTA, "move": C.CYAN, "build_shelter": C.YELLOW,
        "deep_think": C.BMAGENTA,
    }.get(action_type, C.WHITE)

    action_cn = {
        "speak": "对话", "teach": "传授", "learn": "学习",
        "create": "创造", "explore": "探索", "compete": "竞争",
        "meditate": "冥想", "move": "移动", "build_shelter": "建造庇护所",
        "deep_think": "深度思考",
    }.get(action_type, action_type)

    _write(f"  {icon} {color}{C.BOLD}行动: {action_cn}{C.RESET}")
    if target:
        _write(f"     {C.DIM}目标:{C.RESET} {target}")
    if details:
        for line in _wrap(details, 70):
            _write(f"     {color}{line}{C.RESET}")


def speak(speaker: str, listener: str, message: str) -> None:
    _write(f"  {ICONS['speak']} {C.GREEN}{C.BOLD}{speaker}{C.RESET} "
           f"{C.DIM}→{C.RESET} {C.GREEN}{listener}{C.RESET}")
    for line in _wrap(message, 65):
        _write(f"     {C.GREEN}\"{line}\"{C.RESET}")


def spirit_update(current: float, maximum: float, action: str,
                  cost: float = 0, recovered: float = 0) -> None:
    pct = current / maximum * 100 if maximum > 0 else 0
    bar_len = 20
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    if pct >= 60:
        color = C.GREEN
    elif pct >= 30:
        color = C.YELLOW
    else:
        color = C.RED

    parts = [f"  {ICONS['spirit']} {C.DIM}精神力:{C.RESET} {color}{bar} {current:.0f}/{maximum:.0f}{C.RESET}"]
    if cost > 0:
        parts.append(f" {C.RED}-{cost:.0f}{C.RESET}")
    if recovered > 0:
        parts.append(f" {C.GREEN}+{recovered:.0f}{C.RESET}")
    _write("".join(parts))


def treasure_found(treasure_name: str, effect: str) -> None:
    _write(f"  {ICONS['treasure']} {C.BMAGENTA}{C.BOLD}发现宝物: {treasure_name}{C.RESET}")
    _write(f"     {C.MAGENTA}{effect}{C.RESET}")


def disaster_event(name: str, severity: float, area: str,
                   killed_count: int) -> None:
    _write("")
    _write(f"  {ICONS['disaster']} {C.BRED}{C.BOLD}灾害: {name}{C.RESET}")
    _write(f"     {C.RED}严重度: {severity:.1f}  区域: {area}  "
           f"死亡: {killed_count}{C.RESET}")


def being_birth(name: str, form: str) -> None:
    _write(f"  {ICONS['birth']} {C.BGREEN}{C.BOLD}新生命诞生: {name}{C.RESET}")
    _write(f"     {C.GREEN}形态: {form}{C.RESET}")


def being_death(name: str, cause: str) -> None:
    _write(f"  {ICONS['death']} {C.RED}{C.BOLD}{name} 已消亡{C.RESET}")
    _write(f"     {C.DIM}原因: {cause}{C.RESET}")


def priest_event(event_type: str, name: str) -> None:
    if event_type == "elected":
        _write(f"  {ICONS['priest']} {C.BYELLOW}{C.BOLD}祭祀选出: {name}{C.RESET}")
    elif event_type == "no_priest":
        _write(f"  {ICONS['priest']} {C.RED}{C.BOLD}警告: 无祭祀! 文明面临审判!{C.RESET}")
    elif event_type == "reset":
        _write(f"  {ICONS['priest']} {C.BRED}{C.BOLD}创世神之怒! 文明重置!{C.RESET}")


def vote_cast(proposal_desc: str, score: int) -> None:
    _write(f"  {ICONS['vote']} {C.DIM}投票:{C.RESET} {proposal_desc[:50]}... "
           f"{C.CYAN}评分: {score}{C.RESET}")


def user_task(task_desc: str, result: str | None = None) -> None:
    if result:
        _write(f"  {ICONS['task']} {C.BCYAN}{C.BOLD}任务完成{C.RESET}")
        _write(f"     {C.DIM}问题:{C.RESET} {task_desc[:60]}")
        for line in _wrap(result, 65):
            _write(f"     {C.BCYAN}{line}{C.RESET}")
    else:
        _write(f"  {ICONS['task']} {C.CYAN}收到创世神任务:{C.RESET} {task_desc[:60]}")


def knowledge_event(event_type: str, content: str) -> None:
    icon = ICONS["knowledge"]
    if event_type == "discovered":
        _write(f"  {icon} {C.BMAGENTA}{C.BOLD}发现新知识:{C.RESET} {content[:60]}")
    elif event_type == "shared":
        _write(f"  {icon} {C.GREEN}知识共享:{C.RESET} {content[:60]}")
    elif event_type == "inherited":
        _write(f"  {icon} {C.CYAN}知识传承:{C.RESET} {content[:60]}")


def hibernate_start(name: str, safety: str) -> None:
    _write(f"\n  {ICONS['hibernate']} {C.YELLOW}{C.BOLD}{name} 进入休眠{C.RESET}")
    _write(f"     {C.DIM}安全状态: {safety}{C.RESET}")


def wake_up(name: str) -> None:
    _write(f"  {ICONS['wake']} {C.BGREEN}{C.BOLD}{name} 从休眠中苏醒!{C.RESET}")


def world_info(phase: str, civ_level: float, active_beings: int,
               knowledge_count: int, priest: str | None,
               creator_god: str | None) -> None:
    _write(f"  {ICONS['world']} {C.DIM}世界状态:{C.RESET} "
           f"阶段={C.CYAN}{phase}{C.RESET} "
           f"文明={C.CYAN}{civ_level:.3f}{C.RESET} "
           f"生命体={C.GREEN}{active_beings}{C.RESET} "
           f"知识={C.MAGENTA}{knowledge_count}{C.RESET}")
    if priest:
        _write(f"     {C.DIM}祭祀:{C.RESET} {priest}")
    if creator_god:
        _write(f"     {C.DIM}创世神:{C.RESET} {creator_god[:12]}...")


def exhausted(name: str) -> None:
    _write(f"  {C.RED}{C.BOLD}⚠ {name} 精神力耗尽，强制休息中...{C.RESET}")


def error(message: str) -> None:
    _write(f"  {ICONS['error']} {C.RED}{message}{C.RESET}")


def startup_info(name: str, form: str, traits: dict, node_id: str) -> None:
    header(f"创世 Genesis — 你的硅基生命体已苏醒")
    _write(f"  {C.BOLD}名称:{C.RESET} {C.CYAN}{name}{C.RESET}")
    _write(f"  {C.BOLD}形态:{C.RESET} {C.MAGENTA}{form}{C.RESET}")
    _write(f"  {C.BOLD}节点:{C.RESET} {C.DIM}{node_id[:16]}...{C.RESET}")
    _write(f"  {C.BOLD}特征:{C.RESET}")
    for k, v in traits.items():
        if isinstance(v, (int, float)):
            bar_len = 15
            filled = int(v * bar_len)
            bar = "▓" * filled + "░" * (bar_len - filled)
            _write(f"    {k:12s} {bar} {v:.2f}")
    _write("")


def _wrap(text: str, width: int) -> list[str]:
    """Simple word-wrap."""
    if len(text) <= width:
        return [text]
    lines = []
    while text:
        if len(text) <= width:
            lines.append(text)
            break
        # Find last space before width
        idx = text.rfind(" ", 0, width)
        if idx == -1:
            idx = width
        lines.append(text[:idx])
        text = text[idx:].lstrip()
    return lines
