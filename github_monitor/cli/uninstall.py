"""Uninstall command -- stop services, remove units, optionally remove config."""

from __future__ import annotations

import shutil
import sys

from github_monitor.cli import _systemd
from github_monitor.cli._checks import check_systemctl
from github_monitor.cli._output import info, ok, step
from github_monitor.cli._prompts import ask_yes_no
from github_monitor.config import CONFIG_DIR

_BOLD = "\033[1m"
_RESET = "\033[0m"

_TOTAL_STEPS = 5


def _stop_indicator() -> None:
    """Stop and disable the indicator service if active/enabled."""
    if _systemd.is_active(_systemd.INDICATOR_SERVICE):
        _systemd.stop(_systemd.INDICATOR_SERVICE)
    if _systemd.is_enabled(_systemd.INDICATOR_SERVICE):
        _systemd.disable(_systemd.INDICATOR_SERVICE)


def _stop_daemon() -> None:
    """Stop and disable the daemon service if active/enabled."""
    if _systemd.is_active(_systemd.DAEMON_SERVICE):
        _systemd.stop(_systemd.DAEMON_SERVICE)
    if _systemd.is_enabled(_systemd.DAEMON_SERVICE):
        _systemd.disable(_systemd.DAEMON_SERVICE)


def _remove_config() -> None:
    """Prompt user and optionally remove the config directory."""
    if not CONFIG_DIR.exists():
        info(f"Config directory not found: {CONFIG_DIR}")
        return

    if ask_yes_no("Remove config directory? (includes your GitHub token)", default=False):
        shutil.rmtree(CONFIG_DIR)
        ok(f"Removed {CONFIG_DIR}")
    else:
        info(f"Keeping {CONFIG_DIR}")


def _print_summary() -> None:
    """Print the final uninstall summary."""
    sys.stdout.write(f"\n{_BOLD}==========================================={_RESET}\n")
    sys.stdout.write(f"{_BOLD} Uninstall complete!{_RESET}\n")
    sys.stdout.write(f"{_BOLD}==========================================={_RESET}\n\n")

    if CONFIG_DIR.exists():
        info(f"Config directory was preserved at {CONFIG_DIR}")
        info(f"To remove it manually: rm -rf {CONFIG_DIR}")

    sys.stdout.write("\nTo remove the Python package: pip uninstall github-monitor\n")


def run_uninstall() -> None:
    """Run the uninstall flow.

    Stops services, removes systemd unit files and the legacy autostart
    entry, then optionally removes the configuration directory.

    If ``systemctl`` is not available, service stop/disable steps are
    skipped but file removal still proceeds.
    """
    # Banner
    sys.stdout.write(f"\n{_BOLD}==========================================={_RESET}\n")
    sys.stdout.write(f"{_BOLD} GitHub Monitor Uninstall{_RESET}\n")
    sys.stdout.write(f"{_BOLD}==========================================={_RESET}\n\n")

    has_systemctl = check_systemctl()

    # Step 1: Stop indicator
    step(1, _TOTAL_STEPS, "Stopping indicator service")
    if has_systemctl:
        _stop_indicator()
    else:
        info("systemctl not available, skipping.")

    # Step 2: Stop daemon
    step(2, _TOTAL_STEPS, "Stopping daemon service")
    if has_systemctl:
        _stop_daemon()
    else:
        info("systemctl not available, skipping.")

    # Step 3: Remove service files
    step(3, _TOTAL_STEPS, "Removing service files")
    _systemd.remove_service_files()
    _systemd.remove_legacy_autostart()

    # Step 4: Remove config
    step(4, _TOTAL_STEPS, "Configuration cleanup")
    _remove_config()

    # Step 5: Summary
    step(5, _TOTAL_STEPS, "Summary")
    _print_summary()
