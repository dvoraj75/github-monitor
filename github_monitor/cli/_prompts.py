from __future__ import annotations

import sys

from ._output import err, warn


def _read_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        sys.stderr.write("\n")
        err("End of input reached (non-interactive environment?).")
        sys.exit(1)


def ask_string(prompt: str, *, default: str | None = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = _read_input(f"{prompt}{suffix}: ").strip()
        if not value:
            if default is not None:
                return default
            if required:
                warn("A value is required.")
                continue
        return value


def ask_yes_no(prompt: str, *, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        value = _read_input(f"{prompt} {hint} ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        warn("Please answer y/yes or n/no.")


def ask_int(prompt: str, *, default: int, minimum: int) -> int:
    while True:
        value = _read_input(f"{prompt} [{default}]: ").strip()
        if not value:
            return default
        try:
            result = int(value)
        except ValueError:
            warn("Please enter a valid number.")
            continue
        if result < minimum:
            warn(f"Value must be at least {minimum}.")
            continue
        return result


def ask_list(prompt: str, *, default: list[str] | None = None) -> list[str]:
    default_display = ", ".join(default) if default else ""
    suffix = f" [{default_display}]" if default else ""
    value = _read_input(f"{prompt}{suffix}: ").strip()
    if not value:
        return default if default is not None else []
    return [item.strip() for item in value.split(",") if item.strip()]
