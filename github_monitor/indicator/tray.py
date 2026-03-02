"""System tray icon using AppIndicator3.

Displays a tray icon with a PR count label and a minimal GTK menu.
The icon changes based on connection state and whether any PRs
require review.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("AppIndicator3", "0.1")
gi.require_version("Gtk", "3.0")

from gi.repository import AppIndicator3, Gtk  # noqa: E402

from ._tray_state import Icon, get_icon_name, get_label  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_INDICATOR_ID = "github-monitor-indicator"


class TrayIcon:
    """System tray icon using AppIndicator3.

    The icon displays a PR count label and changes appearance based on
    the daemon connection state and whether any PRs need review.

    Parameters
    ----------
    on_activate:
        Called when the user clicks "Show PRs" / "Hide PRs" in the menu.
    on_refresh:
        Called when the user clicks "Refresh" in the menu.
    on_quit:
        Called when the user clicks "Quit" in the menu.
    """

    def __init__(
        self,
        on_activate: Callable[[], None],
        on_refresh: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_activate = on_activate
        self._on_refresh = on_refresh
        self._on_quit = on_quit

        # Internal state for recomputing the icon when only one
        # dimension changes (e.g. connected flips but count stays).
        self._count: int = 0
        self._has_review_requested: bool = False
        self._connected: bool = False

        self._indicator = AppIndicator3.Indicator.new(
            _INDICATOR_ID,
            Icon.DISCONNECTED,
            AppIndicator3.IndicatorCategory.COMMUNICATIONS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self._menu, self._show_prs_item = self._build_menu()
        self._indicator.set_menu(self._menu)

    # -- public API --------------------------------------------------------

    def set_pr_count(self, count: int, *, has_review_requested: bool) -> None:
        """Update the displayed PR count and icon state."""
        self._count = count
        self._has_review_requested = has_review_requested
        self._apply_state()

    def set_connected(self, *, connected: bool) -> None:
        """Update the daemon connection state and icon."""
        self._connected = connected
        self._apply_state()

    # -- internal ----------------------------------------------------------

    def _apply_state(self) -> None:
        """Recompute icon and label from the current internal state."""
        icon_name = get_icon_name(
            self._count,
            has_review_requested=self._has_review_requested,
            connected=self._connected,
        )
        label = get_label(self._count)

        self._indicator.set_icon_full(icon_name, "GitHub Monitor")
        self._indicator.set_label(label, "")

    def _build_menu(self) -> tuple[Gtk.Menu, Gtk.MenuItem]:
        """Build the GTK menu attached to the indicator.

        Returns the menu and the "Show PRs" item (so its label can be
        toggled later if needed).
        """
        menu = Gtk.Menu()

        show_prs_item = Gtk.MenuItem(label="Show PRs")
        show_prs_item.connect("activate", self._on_show_prs_activate)
        menu.append(show_prs_item)

        menu.append(Gtk.SeparatorMenuItem())

        refresh_item = Gtk.MenuItem(label="Refresh")
        refresh_item.connect("activate", self._on_refresh_activate)
        menu.append(refresh_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit_activate)
        menu.append(quit_item)

        menu.show_all()
        return menu, show_prs_item

    def _on_show_prs_activate(self, _item: Gtk.MenuItem) -> None:
        """Handle the 'Show PRs' / 'Hide PRs' menu item click."""
        self._on_activate()

    def _on_refresh_activate(self, _item: Gtk.MenuItem) -> None:
        """Handle the 'Refresh' menu item click."""
        self._on_refresh()

    def _on_quit_activate(self, _item: Gtk.MenuItem) -> None:
        """Handle the 'Quit' menu item click."""
        self._on_quit()
