from __future__ import annotations

import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

from github_monitor.cli._output import ok, warn

SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
DAEMON_SERVICE = "github-monitor.service"
INDICATOR_SERVICE = "github-monitor-indicator.service"
_LEGACY_AUTOSTART = Path.home() / ".config" / "autostart" / "github-monitor-indicator.desktop"

# Placeholders in bundled .service templates that are substituted with
# the actual executable paths at install time.  This ensures the service
# files work regardless of whether the package was installed globally
# (``~/.local/bin``) or inside a virtualenv / uv project.
_DAEMON_EXEC_PLACEHOLDER = "@@GITHUB_MONITOR_EXEC@@"
_INDICATOR_EXEC_PLACEHOLDER = "@@GITHUB_MONITOR_INDICATOR_EXEC@@"


def _resolve_exec(name: str) -> str:
    """Resolve the absolute path to an executable.

    Uses ``shutil.which`` to find the executable that is currently on
    ``$PATH``.  This correctly handles virtualenv, ``uv`` and
    ``pip install --user`` installs.

    Raises ``FileNotFoundError`` if the executable cannot be found.
    """
    path = shutil.which(name)
    if path is None:
        msg = f"Could not find '{name}' on PATH — is the package installed?"
        raise FileNotFoundError(msg)
    return str(Path(path).resolve())


def _read_service_file(name: str) -> str:
    """Read a bundled service file from the package data."""
    return files("github_monitor.cli.systemd").joinpath(name).read_text(encoding="utf-8")


def _run_systemctl(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run a systemctl --user command and return the result."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        check=False,
        capture_output=True,
    )


def install_service_files(*, include_indicator: bool = False) -> None:
    """Install bundled service files to the user systemd directory.

    Resolves the actual executable paths at install time and substitutes
    them into the service file templates so the services work regardless
    of how the package was installed (virtualenv, ``uv``, ``pip``, etc.).

    When reinstalling over existing files, any previously enabled services
    are disabled first and re-enabled after the new files are in place.
    This ensures that ``WantedBy=`` symlinks are updated to match the new
    service file content (systemd's ``daemon-reload`` alone does not move
    existing enable symlinks).
    """
    SERVICE_DIR.mkdir(parents=True, exist_ok=True)

    # Remember which services were enabled so we can re-enable them after
    # overwriting the files.  This is necessary because changing the
    # WantedBy= directive requires a disable+enable cycle to update the
    # symlinks in the target's .wants/ directory.
    services_to_install = [DAEMON_SERVICE]
    if include_indicator:
        services_to_install.append(INDICATOR_SERVICE)

    previously_enabled: list[str] = []
    for svc in services_to_install:
        if (SERVICE_DIR / svc).exists() and is_enabled(svc):
            previously_enabled.append(svc)
            _run_systemctl("disable", svc)

    daemon_exec = _resolve_exec("github-monitor")
    content = _read_service_file(DAEMON_SERVICE).replace(_DAEMON_EXEC_PLACEHOLDER, daemon_exec)
    (SERVICE_DIR / DAEMON_SERVICE).write_text(content, encoding="utf-8")
    ok(f"Installed {DAEMON_SERVICE}")

    if include_indicator:
        indicator_exec = _resolve_exec("github-monitor-indicator")
        content = _read_service_file(INDICATOR_SERVICE).replace(_INDICATOR_EXEC_PLACEHOLDER, indicator_exec)
        (SERVICE_DIR / INDICATOR_SERVICE).write_text(content, encoding="utf-8")
        ok(f"Installed {INDICATOR_SERVICE}")

    daemon_reload()

    # Re-enable services that were previously enabled so the symlinks
    # point to the correct .wants/ directory for the new WantedBy= value.
    for svc in previously_enabled:
        enable(svc)


def remove_service_files() -> None:
    """Remove installed service files and reload the daemon."""
    for name in (DAEMON_SERVICE, INDICATOR_SERVICE):
        path = SERVICE_DIR / name
        if path.exists():
            path.unlink()
            ok(f"Removed {name}")
    daemon_reload()


def daemon_reload() -> None:
    """Run systemctl --user daemon-reload."""
    _run_systemctl("daemon-reload")


def is_active(service: str) -> bool:
    """Check if a service is currently active (running)."""
    result = _run_systemctl("is-active", "--quiet", service)
    return result.returncode == 0


def is_enabled(service: str) -> bool:
    """Check if a service is enabled for autostart."""
    result = _run_systemctl("is-enabled", "--quiet", service)
    return result.returncode == 0


def start(service: str) -> None:
    """Start a systemd user service."""
    result = _run_systemctl("start", service)
    if result.returncode == 0:
        ok(f"Started {service}")
    else:
        warn(f"Failed to start {service}")


def stop(service: str) -> None:
    """Stop a systemd user service."""
    result = _run_systemctl("stop", service)
    if result.returncode == 0:
        ok(f"Stopped {service}")
    else:
        warn(f"Failed to stop {service}")


def restart(service: str) -> None:
    """Restart a systemd user service."""
    result = _run_systemctl("restart", service)
    if result.returncode == 0:
        ok(f"Restarted {service}")
    else:
        warn(f"Failed to restart {service}")


def enable(service: str) -> None:
    """Enable a systemd user service for autostart."""
    result = _run_systemctl("enable", service)
    if result.returncode == 0:
        ok(f"Enabled {service}")
    else:
        warn(f"Failed to enable {service}")


def disable(service: str) -> None:
    """Disable a systemd user service from autostart."""
    result = _run_systemctl("disable", service)
    if result.returncode == 0:
        ok(f"Disabled {service}")
    else:
        warn(f"Failed to disable {service}")


def print_status(service: str) -> None:
    """Print the status of a systemd user service (output goes directly to terminal)."""
    subprocess.run(
        ["systemctl", "--user", "status", service, "--no-pager"],
        check=False,
    )


def service_file_installed(service: str) -> bool:
    """Check if a service file exists in the user systemd directory."""
    return (SERVICE_DIR / service).exists()


def remove_legacy_autostart() -> None:
    """Remove the legacy XDG autostart desktop file if it exists."""
    if _LEGACY_AUTOSTART.exists():
        _LEGACY_AUTOSTART.unlink()
        ok(f"Removed legacy autostart file: {_LEGACY_AUTOSTART}")
