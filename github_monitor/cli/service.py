"""Service management command -- thin CLI layer over _systemd."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from github_monitor.cli import _checks, _systemd
from github_monitor.cli._output import err

if TYPE_CHECKING:
    from collections.abc import Callable


def _require_systemctl() -> bool:
    """Check that systemctl is available, printing an error if not."""
    if not _checks.check_systemctl():
        err("systemctl is required for service management.")
        return False
    return True


def _has_indicator() -> bool:
    """Check if the indicator service file is installed."""
    return _systemd.service_file_installed(_systemd.INDICATOR_SERVICE)


def _action_install() -> None:
    """Install systemd service files."""
    has_gtk = _checks.check_gtk_indicator()
    _systemd.install_service_files(include_indicator=has_gtk)


def _action_start() -> None:
    """Start the daemon and optionally the indicator."""
    _systemd.start(_systemd.DAEMON_SERVICE)
    if _has_indicator():
        _systemd.start(_systemd.INDICATOR_SERVICE)


def _action_stop() -> None:
    """Stop the indicator (if active) then the daemon."""
    if _has_indicator() and _systemd.is_active(_systemd.INDICATOR_SERVICE):
        _systemd.stop(_systemd.INDICATOR_SERVICE)
    _systemd.stop(_systemd.DAEMON_SERVICE)


def _action_restart() -> None:
    """Restart the daemon and optionally the indicator."""
    _systemd.restart(_systemd.DAEMON_SERVICE)
    if _has_indicator() and _systemd.is_active(_systemd.INDICATOR_SERVICE):
        _systemd.restart(_systemd.INDICATOR_SERVICE)


def _action_status() -> None:
    """Print status for the daemon and optionally the indicator."""
    _systemd.print_status(_systemd.DAEMON_SERVICE)
    if _has_indicator():
        sys.stdout.write("\n")
        _systemd.print_status(_systemd.INDICATOR_SERVICE)


def _action_enable() -> None:
    """Enable the daemon and optionally the indicator for autostart."""
    _systemd.enable(_systemd.DAEMON_SERVICE)
    if _has_indicator():
        _systemd.enable(_systemd.INDICATOR_SERVICE)


def _action_disable() -> None:
    """Disable the indicator (if installed) then the daemon from autostart."""
    if _has_indicator():
        _systemd.disable(_systemd.INDICATOR_SERVICE)
    _systemd.disable(_systemd.DAEMON_SERVICE)


_ACTIONS: dict[str, Callable[[], None]] = {
    "install": _action_install,
    "start": _action_start,
    "stop": _action_stop,
    "restart": _action_restart,
    "status": _action_status,
    "enable": _action_enable,
    "disable": _action_disable,
}


def run_service(action: str) -> None:
    """Execute a service management action.

    Each action checks for ``systemctl`` availability first and exits
    with an error if it is not found.
    """
    if not _require_systemctl():
        sys.exit(1)

    handler = _ACTIONS.get(action)
    if handler is None:
        err(f"Unknown service action: {action}")
        sys.exit(1)

    handler()
