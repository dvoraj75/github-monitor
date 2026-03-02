"""Entry point for the github-monitor indicator (system tray icon).

Run with::

    python -m github_monitor.indicator

This module checks for required dependencies before importing any
indicator code, and prints actionable error messages if something is
missing.
"""

from __future__ import annotations

import sys

_SYSTEM_PACKAGES_HELP = """\
The indicator requires GTK3 and AppIndicator3 system packages.

On Ubuntu / Debian:
    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \\
        gir1.2-appindicator3-0.1 libcairo2-dev libgirepository1.0-dev

On Fedora:
    sudo dnf install python3-gobject gtk3 libappindicator-gtk3

Then reinstall with indicator support:
    uv sync --extra indicator
"""

_GBULB_HELP = """\
The indicator requires the 'gbulb' package for GLib/asyncio integration.

Install it with:
    uv sync --extra indicator
  or:
    uv pip install gbulb>=0.6
"""


def _check_dependencies() -> bool:
    """Verify that all required dependencies are available.

    Returns True if everything is OK, False otherwise (with errors
    printed to stderr).
    """
    ok = True

    # Check PyGObject (gi)
    try:
        import gi  # noqa: PLC0415
    except ImportError:
        print(_SYSTEM_PACKAGES_HELP, file=sys.stderr)  # noqa: T201
        return False

    # Check GTK3 typelib
    try:
        gi.require_version("Gtk", "3.0")
    except ValueError:
        print("ERROR: GTK 3.0 typelib not found.", file=sys.stderr)  # noqa: T201
        print(_SYSTEM_PACKAGES_HELP, file=sys.stderr)  # noqa: T201
        ok = False

    # Check AppIndicator3 typelib
    try:
        gi.require_version("AppIndicator3", "0.1")
    except ValueError:
        print("ERROR: AppIndicator3 0.1 typelib not found.", file=sys.stderr)  # noqa: T201
        print(_SYSTEM_PACKAGES_HELP, file=sys.stderr)  # noqa: T201
        ok = False

    # Check gbulb
    try:
        import gbulb  # noqa: PLC0415, F401
    except ImportError:
        print("ERROR: 'gbulb' package not found.", file=sys.stderr)  # noqa: T201
        print(_GBULB_HELP, file=sys.stderr)  # noqa: T201
        ok = False

    return ok


def main() -> None:
    """Launch the indicator after verifying dependencies."""
    if not _check_dependencies():
        sys.exit(1)

    # Imports deferred until after dependency checks so the user gets
    # a helpful message instead of a raw ImportError traceback.
    # Placeholder — the app orchestrator (Step 6) will replace this.
    print("github-monitor indicator — not yet implemented")  # noqa: T201


if __name__ == "__main__":
    main()
