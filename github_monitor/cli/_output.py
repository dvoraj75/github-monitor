from __future__ import annotations

import sys

_GREEN = "\033[0;32m"
_YELLOW = "\033[1;33m"
_RED = "\033[0;31m"
_BLUE = "\033[0;34m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


_SUPPORTS_STDOUT_COLOR = sys.stdout.isatty()
_SUPPORTS_STDERR_COLOR = sys.stderr.isatty()


def _fmt(code: str, text: str, *, stderr: bool = False) -> str:
    if _SUPPORTS_STDERR_COLOR if stderr else _SUPPORTS_STDOUT_COLOR:
        return f"{code}{text}{_RESET}"
    return text


def info(msg: str) -> None:
    sys.stdout.write(f"{_fmt(_BLUE, '[INFO]')} {msg}\n")


def ok(msg: str) -> None:
    sys.stdout.write(f"{_fmt(_GREEN, '[OK]')} {msg}\n")


def warn(msg: str) -> None:
    sys.stderr.write(f"{_fmt(_YELLOW, '[WARN]', stderr=True)} {msg}\n")


def err(msg: str) -> None:
    sys.stderr.write(f"{_fmt(_RED, '[ERR]', stderr=True)} {msg}\n")


def step(num: int, total: int, msg: str) -> None:
    sys.stdout.write(f"{_fmt(_BLUE, f'[{num}/{total}]')} {msg}\n")
