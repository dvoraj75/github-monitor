"""Setup command -- interactive config wizard and service installation."""

from __future__ import annotations

import sys

from github_monitor.cli import _checks, _systemd
from github_monitor.cli._output import info, ok, step
from github_monitor.cli._prompts import ask_int, ask_list, ask_string, ask_yes_no
from github_monitor.config import CONFIG_DIR, CONFIG_PATH

_BOLD = "\033[1m"
_RESET = "\033[0m"

_CONFIG_TEMPLATE = """\
# GitHub personal access token
# Required scopes: repo (for private repos) or public_repo (public only)
github_token = "{token}"

# Your GitHub username
github_username = "{username}"

# Polling interval in seconds (default: 300 = 5 minutes)
poll_interval = {poll_interval}

# Optional: filter to specific repos (owner/name format)
# If empty, monitors all repos where you have review requests
repos = {repos_toml}
"""


def _format_repos_toml(repos: list[str]) -> str:
    """Format a list of repo strings as a TOML inline array literal."""
    if not repos:
        return "[]"
    quoted = ", ".join(f'"{r}"' for r in repos)
    return f"[{quoted}]"


def _write_config(token: str, username: str, poll_interval: int, repos: list[str]) -> None:
    """Write the config file to CONFIG_PATH with restricted permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = _CONFIG_TEMPLATE.format(
        token=token,
        username=username,
        poll_interval=poll_interval,
        repos_toml=_format_repos_toml(repos),
    )
    CONFIG_PATH.write_text(content, encoding="utf-8")
    CONFIG_PATH.chmod(0o600)
    ok(f"Config written to {CONFIG_PATH} (permissions: 600)")


def _config_wizard() -> None:
    """Run the interactive config wizard."""
    if CONFIG_PATH.exists() and not ask_yes_no("Config file already exists. Overwrite?", default=False):
        info("Keeping existing config.")
        return

    sys.stdout.write("\n")
    info("Let's configure github-monitor.")
    info("You'll need a GitHub personal access token with 'repo' scope.")
    info("Create one at: https://github.com/settings/tokens")
    sys.stdout.write("\n")

    token = ask_string("GitHub personal access token", required=True)
    username = ask_string("GitHub username", required=True)
    poll_interval = ask_int("Poll interval in seconds", default=300, minimum=30)
    repos = ask_list("Filter to specific repos (comma-separated owner/repo, leave empty for all)")

    _write_config(token, username, poll_interval, repos)


def _start_or_restart(service: str) -> None:
    """Start a service, or restart it if already active."""
    if _systemd.is_active(service):
        _systemd.restart(service)
    else:
        _systemd.start(service)


def _install_and_start_services(*, has_gtk: bool, step_install: int, step_start: int, total: int) -> None:
    """Install, enable, and start systemd services."""
    step(step_install, total, "Installing systemd services")
    _systemd.install_service_files(include_indicator=has_gtk)

    step(step_start, total, "Enabling and starting services")
    _systemd.enable(_systemd.DAEMON_SERVICE)
    _start_or_restart(_systemd.DAEMON_SERVICE)

    if has_gtk:
        _systemd.enable(_systemd.INDICATOR_SERVICE)
        _start_or_restart(_systemd.INDICATOR_SERVICE)


def _print_summary(*, has_gtk: bool, has_systemctl: bool) -> None:
    """Print the final summary with config path and useful commands."""
    sys.stdout.write(f"\n{_BOLD}==========================================={_RESET}\n")
    sys.stdout.write(f"{_BOLD} Setup complete!{_RESET}\n")
    sys.stdout.write(f"{_BOLD}==========================================={_RESET}\n\n")

    info(f"Config: {CONFIG_PATH}")

    if has_systemctl:
        sys.stdout.write("\nUseful commands:\n")
        sys.stdout.write("  systemctl --user status github-monitor       # check status\n")
        sys.stdout.write("  systemctl --user reload github-monitor       # reload config\n")
        sys.stdout.write("  systemctl --user restart github-monitor      # full restart\n")
        sys.stdout.write("  journalctl --user -u github-monitor -f       # follow logs\n")
        if has_gtk:
            sys.stdout.write("  systemctl --user status github-monitor-indicator   # indicator status\n")
            sys.stdout.write("  systemctl --user restart github-monitor-indicator  # restart indicator\n")
            sys.stdout.write("  journalctl --user -u github-monitor-indicator -f   # indicator logs\n")


def run_setup(*, config_only: bool = False, service_only: bool = False) -> None:
    """Run the setup wizard.

    With no flags, runs the full setup: dependency checks, config wizard,
    service installation, and enable+start.

    ``config_only``  -- only create the config file, skip service steps.
    ``service_only`` -- only install and start services, skip config wizard.
    """
    # Banner
    sys.stdout.write(f"\n{_BOLD}==========================================={_RESET}\n")
    sys.stdout.write(f"{_BOLD} GitHub Monitor Setup{_RESET}\n")
    sys.stdout.write(f"{_BOLD}==========================================={_RESET}\n\n")

    # Compute total steps based on mode
    if config_only:
        total = 3  # checks, config, summary
    elif service_only:
        total = 4  # checks, install, start, summary
    else:
        total = 5  # checks, config, install, start, summary

    current = 1

    # Step: Dependency checks
    step(current, total, "Checking dependencies")
    _checks.check_notify_send()
    _checks.check_dbus_session()
    has_gtk = _checks.check_gtk_indicator()

    has_systemctl = True
    if not config_only:
        has_systemctl = _checks.check_systemctl()
    current += 1

    # Step: Config wizard (skipped for --service-only)
    if not service_only:
        step(current, total, "Configuring github-monitor")
        _config_wizard()
        current += 1

    # Steps: Install + enable/start services (skipped for --config-only or missing systemctl)
    if not config_only and has_systemctl:
        _install_and_start_services(
            has_gtk=has_gtk,
            step_install=current,
            step_start=current + 1,
            total=total,
        )
        current += 2

    # Summary
    step(current, total, "Summary")
    _print_summary(has_gtk=has_gtk, has_systemctl=has_systemctl and not config_only)
