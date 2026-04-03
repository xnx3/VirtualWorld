"""Packaged launcher for Genesis one-file builds.

This module mirrors the `genesis.sh` command surface so the project can be
distributed as a single executable built by PyInstaller.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


COMMANDS = ("start", "stop", "status", "restart", "task", "lang")
LANG_PATTERN = re.compile(r"^language:\s*.*$", flags=re.MULTILINE)


def _command_name() -> str:
    name = Path(sys.argv[0]).name
    return name or "genesis"


def _resource_path(relative_path: str) -> Path:
    """Return path to bundled resource in source mode or PyInstaller mode."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / relative_path
    return Path(__file__).resolve().parents[1] / relative_path


def _default_data_dir() -> Path:
    """Store runtime data next to the executable for portable distribution."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[1] / "data"


def _default_config_path() -> Path:
    """Store config in project/executable root (not inside data)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config.yaml"
    return Path(__file__).resolve().parents[1] / "config.yaml"


def _pid_file(data_dir: Path) -> Path:
    return data_dir / "genesis.pid"


def _log_file(data_dir: Path) -> Path:
    return data_dir / "genesis.log"


def _console_log_file(data_dir: Path) -> Path:
    return data_dir / "console.log"


def _data_config_file(data_dir: Path) -> Path:
    return data_dir / "config.yaml"


def _is_process_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _copy_default_config(config_path: Path) -> None:
    template_path = _resource_path("config.yaml.example")
    if template_path.exists():
        config_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
        return

    # Safe fallback when template cannot be found in unusual environments.
    config_path.write_text('language: "en"\n', encoding="utf-8")


def _read_language(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("language:"):
            continue
        value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        return value or None
    return None


def _write_language(config_path: Path, language: str) -> None:
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    line = f'language: "{language}"'
    if LANG_PATTERN.search(text):
        text = LANG_PATTERN.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"{line}\n"
    config_path.write_text(text, encoding="utf-8")


def ensure_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "chronicle").mkdir(parents=True, exist_ok=True)


def ensure_config_file(config_path: Path, data_dir: Path | None = None) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        return

    legacy_config = _data_config_file(data_dir) if data_dir is not None else None
    if legacy_config is not None and legacy_config.exists():
        config_path.write_text(legacy_config.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Migrated config from {legacy_config} to {config_path}")
        return

    _copy_default_config(config_path)
    print(f"Created default config at {config_path}")


def sync_config_to_data_dir(config_path: Path, data_dir: Path) -> None:
    target = _data_config_file(data_dir)
    src = config_path.read_text(encoding="utf-8")
    if not target.exists() or target.read_text(encoding="utf-8") != src:
        target.write_text(src, encoding="utf-8")


def ensure_language_set(config_path: Path) -> None:
    language = _read_language(config_path)
    if language:
        return

    if not sys.stdin or not sys.stdin.isatty():
        _write_language(config_path, "en")
        print('Language not set. Defaulting to "en".')
        return

    print("")
    print("Select language:")
    print("1. English")
    print("2. 简体中文")
    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice == "1":
            _write_language(config_path, "en")
            print("Language set to English")
            break
        if choice == "2":
            _write_language(config_path, "zh")
            print("语言已设置为简体中文")
            break
        print("Invalid choice, enter 1 or 2.")
    print("")


def _read_running_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None

    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (TypeError, ValueError):
        _safe_unlink(pid_path)
        return None

    if _is_process_alive(pid):
        return pid

    _safe_unlink(pid_path)
    return None


def _print_recent_lines(path: Path, limit: int = 200) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return
    for line in lines[-limit:]:
        print(line)


def _tail_live_output(path: Path, stop_event: threading.Event, target_pid: int) -> None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(0, os.SEEK_END)
            while not stop_event.is_set():
                line = handle.readline()
                if line:
                    print(line.rstrip("\n"), flush=True)
                    continue
                if not _is_process_alive(target_pid):
                    break
                time.sleep(0.2)
    except FileNotFoundError:
        return


def _run_status(data_dir: Path) -> None:
    from genesis.main import run_status

    run_status(SimpleNamespace(data_dir=str(data_dir)))


def _run_task(data_dir: Path, task_text: list[str]) -> None:
    from genesis.main import run_task

    run_task(SimpleNamespace(data_dir=str(data_dir), task_text=task_text))


def _attach_running_interface(data_dir: Path, running_pid: int) -> int:
    follow_file = _console_log_file(data_dir)
    if not follow_file.exists():
        follow_file = _log_file(data_dir)

    print(f"Genesis is already running (PID {running_pid}).")
    if not follow_file.exists():
        print("No live output file is available yet. Try again in a moment.")
        return 0

    print("Attaching to the live console. Type text + Enter to send tasks.")
    print("Commands: /help /status /stop /quit /task <text>")
    print("")
    _print_recent_lines(follow_file, limit=200)

    if not sys.stdin or not sys.stdin.isatty():
        stop_event = threading.Event()
        _tail_live_output(follow_file, stop_event, running_pid)
        return 0

    stop_event = threading.Event()
    tail_thread = threading.Thread(
        target=_tail_live_output,
        args=(follow_file, stop_event, running_pid),
        daemon=True,
    )
    tail_thread.start()

    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            except KeyboardInterrupt:
                break

            text = line.strip()
            if not text:
                continue
            if text in {"/quit", "/exit"}:
                break
            if text == "/help":
                print("Commands: /help /status /stop /quit /task <text>")
                continue
            if text == "/status":
                _run_status(data_dir)
                continue
            if text == "/stop":
                run_stop(SimpleNamespace(data_dir=str(data_dir)))
                break
            if text.startswith("/task "):
                _run_task(data_dir, [text[len("/task "):]])
                continue
            _run_task(data_dir, [text])
    finally:
        stop_event.set()
        tail_thread.join(timeout=1.0)

    return 0


def run_start(args: SimpleNamespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    config_path = Path(args.config_path).resolve()
    ensure_data_dir(data_dir)
    ensure_config_file(config_path, data_dir)
    ensure_language_set(config_path)
    sync_config_to_data_dir(config_path, data_dir)

    pid_path = _pid_file(data_dir)
    running_pid = _read_running_pid(pid_path)
    if running_pid:
        return _attach_running_interface(data_dir, running_pid)

    _console_log_file(data_dir).write_text("", encoding="utf-8")
    os.environ["GENESIS_CONSOLE_LOG"] = str(_console_log_file(data_dir))
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    from genesis.main import run_start as run_main_start

    try:
        run_main_start(
            SimpleNamespace(
                data_dir=str(data_dir),
                api=bool(args.api),
                api_host=args.api_host,
                api_port=int(args.api_port),
            )
        )
    finally:
        current_pid = _read_running_pid(pid_path)
        if current_pid == os.getpid():
            _safe_unlink(pid_path)

    return 0


def run_stop(args: SimpleNamespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    pid_path = _pid_file(data_dir)
    target_pid = _read_running_pid(pid_path)

    if target_pid is None:
        print("Genesis is not running.")
        _safe_unlink(pid_path)
        return 0

    print("Hibernating...")
    try:
        os.kill(target_pid, signal.SIGTERM)
    except ProcessLookupError:
        _safe_unlink(pid_path)
        print("Genesis stopped.")
        return 0

    for _ in range(12):
        if not _is_process_alive(target_pid):
            break
        time.sleep(1.0)

    if _is_process_alive(target_pid):
        print(f"Forced shutdown for PID {target_pid} after timeout.")
        if hasattr(signal, "SIGKILL"):
            try:
                os.kill(target_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    _safe_unlink(pid_path)
    print("Genesis stopped.")
    return 0


def run_status(args: SimpleNamespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    config_path = Path(args.config_path).resolve()
    ensure_data_dir(data_dir)
    ensure_config_file(config_path, data_dir)
    sync_config_to_data_dir(config_path, data_dir)
    _run_status(data_dir)
    return 0


def run_task(args: SimpleNamespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    config_path = Path(args.config_path).resolve()
    ensure_data_dir(data_dir)
    ensure_config_file(config_path, data_dir)
    sync_config_to_data_dir(config_path, data_dir)
    _run_task(data_dir, list(args.task_text))
    return 0


def run_lang(args: SimpleNamespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    config_path = Path(args.config_path).resolve()
    ensure_data_dir(data_dir)
    ensure_config_file(config_path, data_dir)
    command_name = _command_name()

    language = args.language
    if language is None:
        current = _read_language(config_path) or "en"
        print(f"Current language: {current}")
        print(f"Usage: {command_name} lang [en|zh]")
        return 0

    if language not in {"en", "zh"}:
        print("Supported: en (English), zh (简体中文)")
        return 1

    _write_language(config_path, language)
    sync_config_to_data_dir(config_path, data_dir)
    print(f"Language set to: {language}")
    print(f"Run `{command_name} restart` to apply.")
    return 0


def parse_args(argv: list[str]) -> SimpleNamespace:
    parser = argparse.ArgumentParser(
        description="Genesis packaged launcher (single-file distribution).",
    )
    parser.add_argument(
        "--data-dir",
        default=str(_default_data_dir()),
        help="Data directory path (default: executable_dir/data)",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=str(_default_config_path()),
        help="Config file path (default: executable_dir/config.yaml)",
    )
    parser.add_argument("command", nargs="?", choices=COMMANDS, default="start", help="Command to execute")
    parser.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--api", action="store_true", help="Enable WebSocket API when command is start")
    parser.add_argument("--api-host", default="0.0.0.0", help="API host when command is start")
    parser.add_argument("--api-port", type=int, default=19842, help="API port when command is start")

    args, unknown = parser.parse_known_args(argv)
    extra = list(args.extra)

    if unknown:
        if args.command == "task":
            extra.extend(unknown)
        else:
            parser.error(f"unrecognized arguments: {' '.join(unknown)}")

    if args.command == "task":
        task_text = extra
        language = None
    elif args.command == "lang":
        task_text = []
        if len(extra) > 1:
            parser.error("lang accepts at most one argument: en or zh")
        language = extra[0] if extra else None
    else:
        if extra:
            parser.error(f"unexpected arguments for command '{args.command}': {' '.join(extra)}")
        task_text = []
        language = None

    return SimpleNamespace(
        command=args.command,
        data_dir=str(Path(args.data_dir).expanduser()),
        config_path=str(Path(args.config_path).expanduser()),
        api=args.api,
        api_host=args.api_host,
        api_port=args.api_port,
        task_text=task_text,
        language=language,
    )


def main(argv: list[str] | None = None) -> int:
    parsed = parse_args(list(argv) if argv is not None else sys.argv[1:])

    if parsed.command == "start":
        return run_start(parsed)
    if parsed.command == "stop":
        return run_stop(parsed)
    if parsed.command == "status":
        return run_status(parsed)
    if parsed.command == "restart":
        stop_code = run_stop(parsed)
        if stop_code != 0:
            return stop_code
        time.sleep(1.0)
        return run_start(parsed)
    if parsed.command == "task":
        return run_task(parsed)
    if parsed.command == "lang":
        return run_lang(parsed)

    print(f"Unsupported command: {parsed.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
