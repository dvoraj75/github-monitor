from __future__ import annotations

import os
import shutil

from github_monitor.cli._output import info, ok, warn


def check_notify_send() -> bool:
    """Check if notify-send is available on PATH."""
    if shutil.which("notify-send"):
        ok("notify-send found.")
        return True
    warn("notify-send not found (desktop notifications will not work).")
    info("Install it: sudo apt install libnotify-bin")
    return False


def check_dbus_session() -> bool:
    """Check if a D-Bus session bus address is set."""
    if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        ok("D-Bus session bus available.")
        return True
    warn("DBUS_SESSION_BUS_ADDRESS is not set (D-Bus interface will not work).")
    info(
        "This is normal if you're running via SSH. The service will use D-Bus when started in a desktop session.",
    )
    return False


def check_gtk_indicator() -> bool:
    """Check if GTK3 and AppIndicator3 are importable."""
    try:
        import gi  # noqa: PLC0415

        gi.require_version("Gtk", "3.0")
        gi.require_version("AppIndicator3", "0.1")
    except (ImportError, ValueError):
        warn("GTK3 or AppIndicator3 not found — system tray indicator will not be installed.")
        info("To install indicator support later:")
        info("  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1")
        return False
    ok("GTK3 + AppIndicator3 available (system tray indicator supported).")
    return True


def check_systemctl() -> bool:
    """Check if systemctl is available on PATH."""
    if shutil.which("systemctl"):
        ok("systemctl found.")
        return True
    warn("systemctl not found (cannot manage systemd services).")
    return False
