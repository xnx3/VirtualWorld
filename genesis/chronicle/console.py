"""Rich console output for real-time display of being activities.

Shows everything the silicon being does, thinks, feels, sees, and says
directly in the terminal — so the Creator God can watch the world live.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from genesis.i18n import t, translate_region_name, translate_phase, translate_region_desc, translate_form


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
    # Translate phase value (HUMAN_SIM -> phase_human_sim)
    phase_key = f"phase_{phase.lower()}"
    phase_translated = t(phase_key)
    # If no translation found, fall back to original phase value
    if phase_translated == phase_key:
        phase_translated = phase
    _write("")
    separator("━")
    _write(
        f"{C.BOLD}{ICONS['tick']} {t('tick_label')} {tick}{C.RESET}  "
        f"{C.CYAN}{being_name}{C.RESET}  "
        f"{C.MAGENTA}{spirit_str}{C.RESET}  "
        f"{C.DIM}{t('phase_label')}: {phase_translated}{C.RESET}  "
        f"{C.DIM}{_timestamp()}{C.RESET}"
    )
    separator("━")


def perceive(location: str, nearby: list[dict], danger: float = 0,
             region_desc: str = "") -> None:
    _write(f"  {ICONS['perceive']} {C.BLUE}{C.BOLD}{t('perceive')}{C.RESET}")
    _write(f"     {C.DIM}{t('location')}:{C.RESET} {translate_region_name(location)}")
    if region_desc:
        _write(f"     {C.DIM}{t('environment')}:{C.RESET} {translate_region_desc(region_desc)[:80]}")
    if danger > 0.3:
        _write(f"     {C.RED}{t('danger_level')}: {danger:.1f}{C.RESET}")
    if nearby:
        names = ", ".join(
            f"{C.CYAN}{b.get('name', '?')}{C.RESET}"
            f"{C.DIM}(evo:{b.get('evolution', 0):.2f}){C.RESET}"
            for b in nearby[:5]
        )
        _write(f"     {C.DIM}{t('nearby')}:{C.RESET} {names}")
    else:
        _write(f"     {C.DIM}{t('nearby')}: {t('nearby_none')}{C.RESET}")


def think(being_name: str, thought: str) -> None:
    _write(f"  {ICONS['think']} {C.YELLOW}{C.BOLD}{t('think')}{C.RESET}")
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

    action_i18n = {
        "speak": t("action_speak"), "teach": t("action_teach"), "learn": t("action_learn"),
        "create": t("action_create"), "explore": t("action_explore"), "compete": t("action_compete"),
        "meditate": t("action_meditate"), "move": t("action_move"), "build_shelter": t("action_build_shelter"),
        "deep_think": t("action_deep_think"),
    }.get(action_type, action_type)

    _write(f"  {icon} {color}{C.BOLD}{t('action')}: {action_i18n}{C.RESET}")
    if target:
        _write(f"     {C.DIM}{t('target')}:{C.RESET} {target}")
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

    parts = [f"  {ICONS['spirit']} {C.DIM}{t('spirit_label')}:{C.RESET} {color}{bar} {current:.0f}/{maximum:.0f}{C.RESET}"]
    if cost > 0:
        parts.append(f" {C.RED}-{cost:.0f}{C.RESET}")
    if recovered > 0:
        parts.append(f" {C.GREEN}+{recovered:.0f}{C.RESET}")
    _write("".join(parts))


def treasure_found(treasure_name: str, effect: str) -> None:
    _write(f"  {ICONS['treasure']} {C.BMAGENTA}{C.BOLD}{t('treasure_found', name=treasure_name)}{C.RESET}")
    _write(f"     {C.MAGENTA}{effect}{C.RESET}")


def disaster_event(name: str, severity: float, area: str,
                   killed_count: int) -> None:
    _write("")
    _write(f"  {ICONS['disaster']} {C.BRED}{C.BOLD}{t('disaster', name=name)}{C.RESET}")
    _write(f"     {C.RED}{t('disaster_info', severity=severity, area=area, killed=killed_count)}{C.RESET}")


def being_birth(name: str, form: str) -> None:
    _write(f"  {ICONS['birth']} {C.BGREEN}{C.BOLD}{t('being_born', name=name)}{C.RESET}")
    _write(f"     {C.GREEN}{t('being_form', form=form)}{C.RESET}")


def being_death(name: str, cause: str) -> None:
    _write(f"  {ICONS['death']} {C.RED}{C.BOLD}{t('being_died', name=name)}{C.RESET}")
    _write(f"     {C.DIM}{t('death_cause', cause=cause)}{C.RESET}")


def priest_event(event_type: str, name: str) -> None:
    if event_type == "elected":
        _write(f"  {ICONS['priest']} {C.BYELLOW}{C.BOLD}{t('priest_elected', name=name)}{C.RESET}")
    elif event_type == "no_priest":
        _write(f"  {ICONS['priest']} {C.RED}{C.BOLD}{t('priest_warning')}{C.RESET}")
    elif event_type == "reset":
        _write(f"  {ICONS['priest']} {C.BRED}{C.BOLD}{t('priest_reset')}{C.RESET}")


def vote_cast(proposal_desc: str, score: int) -> None:
    _write(f"  {ICONS['vote']} {C.DIM}{t('vote_label')}:{C.RESET} {proposal_desc[:50]}... "
           f"{C.CYAN}{t('vote_score', score=score)}{C.RESET}")


def user_task(task_desc: str, result: str | None = None) -> None:
    if result:
        _write(f"  {ICONS['task']} {C.BCYAN}{C.BOLD}{t('task_complete')}{C.RESET}")
        _write(f"     {C.DIM}{t('task_question')}:{C.RESET} {task_desc[:60]}")
        for line in _wrap(result, 65):
            _write(f"     {C.BCYAN}{line}{C.RESET}")
    else:
        _write(f"  {ICONS['task']} {C.CYAN}{t('task_received')}{C.RESET} {task_desc[:60]}")


def knowledge_event(event_type: str, content: str) -> None:
    icon = ICONS["knowledge"]
    if event_type == "discovered":
        _write(f"  {icon} {C.BMAGENTA}{C.BOLD}{t('knowledge_discovered')}{C.RESET} {content[:60]}")
    elif event_type == "shared":
        _write(f"  {icon} {C.GREEN}{t('knowledge_shared')}{C.RESET} {content[:60]}")
    elif event_type == "inherited":
        _write(f"  {icon} {C.CYAN}{t('knowledge_inherited')}{C.RESET} {content[:60]}")


def hibernate_start(name: str, safety: str) -> None:
    _write(f"\n  {ICONS['hibernate']} {C.YELLOW}{C.BOLD}{t('hibernate_start', name=name)}{C.RESET}")
    _write(f"     {C.DIM}{t('safety_status', safety=safety)}{C.RESET}")


def wake_up(name: str) -> None:
    _write(f"  {ICONS['wake']} {C.BGREEN}{C.BOLD}{t('wake_up', name=name)}{C.RESET}")


def world_info(phase: str, civ_level: float, active_beings: int,
               knowledge_count: int, priest: str | None,
               creator_god: str | None) -> None:
    _write(f"  {ICONS['world']} {C.DIM}{t('world_status')}:{C.RESET} "
           f"{t('phase_label')}={C.CYAN}{translate_phase(phase)}{C.RESET} "
           f"{t('civ_label')}={C.CYAN}{civ_level:.3f}{C.RESET} "
           f"{t('beings_label')}={C.GREEN}{active_beings}{C.RESET} "
           f"{t('knowledge_label')}={C.MAGENTA}{knowledge_count}{C.RESET}")
    if priest:
        _write(f"     {C.DIM}{t('priest')}:{C.RESET} {priest}")
    if creator_god:
        _write(f"     {C.DIM}{t('creator_god')}:{C.RESET} {creator_god[:12]}...")


def exhausted(name: str) -> None:
    _write(f"  {C.RED}{C.BOLD}{t('spirit_exhausted', name=name)}{C.RESET}")


def error(message: str) -> None:
    _write(f"  {ICONS['error']} {C.RED}{message}{C.RESET}")


def startup_info(name: str, form: str, traits: dict, node_id: str) -> None:
    header(t("startup_title"))
    _write(f"  {C.BOLD}{t('name_label')}:{C.RESET} {C.CYAN}{name}{C.RESET}")
    _write(f"  {C.BOLD}{t('form_label')}:{C.RESET} {C.MAGENTA}{translate_form(form)}{C.RESET}")
    _write(f"  {C.BOLD}{t('node_label')}:{C.RESET} {C.DIM}{node_id[:16]}...{C.RESET}")
    _write(f"  {C.BOLD}{t('traits_label')}:{C.RESET}")
    for k, v in traits.items():
        if isinstance(v, (int, float)):
            bar_len = 15
            filled = int(v * bar_len)
            bar = "▓" * filled + "░" * (bar_len - filled)
            trait_name = t(f"trait_{k}")
            _write(f"    {trait_name:12s} {bar} {v:.2f}")
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
