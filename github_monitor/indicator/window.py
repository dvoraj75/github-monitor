"""Popup window displaying the current PR list.

Shows a GTK3 popup near the tray icon with a scrollable list of pull
requests, a header bar with a refresh button, and a footer with status
information.  Each row is clickable and opens the PR in the browser.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from ._window_helpers import escape_markup, relative_time, sort_prs, status_text  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

    from .models import DaemonStatus, PRInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
.pr-window {
    border-radius: 8px;
}

.header {
    padding: 12px 16px;
}

.header-title {
    font-weight: bold;
    font-size: 14px;
}

.refresh-button {
    padding: 4px 8px;
    min-height: 0;
    min-width: 0;
}

.pr-row {
    padding: 8px 16px;
}

.dot {
    font-size: 16px;
    min-width: 24px;
}

.review-requested {
    color: #e8590c;
}

.assigned {
    color: #2196f3;
}

.pr-repo {
    font-weight: bold;
}

.pr-title {
}

.dim {
    opacity: 0.6;
    font-size: 12px;
}

.footer {
    padding: 8px 16px;
    opacity: 0.6;
    font-size: 12px;
}

.empty-state {
    padding: 32px;
    opacity: 0.5;
}
"""

_WINDOW_WIDTH = 400
_MAX_WINDOW_HEIGHT = 500


# ---------------------------------------------------------------------------
# PRWindow
# ---------------------------------------------------------------------------


class PRWindow:
    """Popup window displaying the current PR list.

    Parameters
    ----------
    on_pr_clicked:
        Called with the PR URL when a row is clicked.
    on_refresh:
        Called when the header refresh button is pressed.
    """

    def __init__(
        self,
        on_pr_clicked: Callable[[str], None],
        on_refresh: Callable[[], None],
        on_visibility_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._on_pr_clicked = on_pr_clicked
        self._on_refresh = on_refresh
        self._on_visibility_changed = on_visibility_changed

        # Maps ListBoxRow index → PR URL for click handling.
        self._row_urls: dict[int, str] = {}

        self._load_css()

        self._window = self._build_window()
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)

        self._footer = Gtk.Label(label="")
        self._footer.set_halign(Gtk.Align.START)
        self._footer.get_style_context().add_class("footer")

        # Content area that can be swapped between list and empty/disconnected state.
        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_max_content_height(_MAX_WINDOW_HEIGHT - 100)
        self._scrolled.set_propagate_natural_height(True)
        self._scrolled.add(self._listbox)

        # Assemble the main layout.
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.pack_start(self._build_header(), expand=False, fill=True, padding=0)
        vbox.pack_start(Gtk.Separator(), expand=False, fill=True, padding=0)
        vbox.pack_start(self._scrolled, expand=True, fill=True, padding=0)
        vbox.pack_start(Gtk.Separator(), expand=False, fill=True, padding=0)
        vbox.pack_start(self._footer, expand=False, fill=True, padding=0)

        self._window.add(vbox)

    # -- public API --------------------------------------------------------

    @property
    def visible(self) -> bool:
        """Whether the popup window is currently visible."""
        return self._visible

    def update_prs(self, prs: list[PRInfo], status: DaemonStatus | None) -> None:
        """Rebuild the PR list and update the footer."""
        self._clear_listbox()
        sorted_prs = sort_prs(prs)

        if not sorted_prs:
            self._show_empty_state("No pull requests")
        else:
            for idx, pr in enumerate(sorted_prs):
                row = self._build_pr_row(pr)
                self._listbox.add(row)
                self._row_urls[idx] = pr.url

        # Update footer.
        count = status.pr_count if status else len(prs)
        last_updated = status.last_updated if status else None
        self._footer.set_text(status_text(count, last_updated))

        # Realize child widgets without showing the window itself
        # to avoid a visual flash when the window is hidden.
        self._realize_children()

    def show(self) -> None:
        """Show the popup window near the mouse pointer."""
        self._position_near_pointer()
        self._window.show_all()
        self._window.present()
        self._set_visible(visible=True)

    def hide(self) -> None:
        """Hide the popup window."""
        self._window.hide()
        self._set_visible(visible=False)

    def toggle(self) -> None:
        """Toggle popup window visibility."""
        if self._visible:
            self.hide()
        else:
            self.show()

    def set_disconnected(self) -> None:
        """Show a 'daemon not running' state in the window."""
        self._clear_listbox()
        self._show_empty_state("Daemon is not running\nWaiting for connection\u2026")
        self._footer.set_text("")

        # Realize child widgets without showing the window itself.
        self._realize_children()

    # -- internal: window construction -------------------------------------

    @staticmethod
    def _load_css() -> None:
        """Load the application CSS into the default screen."""
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS.encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _build_window(self) -> Gtk.Window:
        """Create and configure the popup window."""
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_keep_above(True)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        window.set_default_size(_WINDOW_WIDTH, -1)
        window.get_style_context().add_class("pr-window")

        window.connect("focus-out-event", self._on_focus_out)

        self._visible = False
        return window

    def _build_header(self) -> Gtk.Box:
        """Build the header bar with title and refresh button."""
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.get_style_context().add_class("header")

        title = Gtk.Label(label="GitHub Monitor")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("header-title")
        header.pack_start(title, expand=True, fill=True, padding=0)

        refresh_btn = Gtk.Button(label="\u21bb Refresh")
        refresh_btn.get_style_context().add_class("refresh-button")
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        header.pack_end(refresh_btn, expand=False, fill=False, padding=0)

        return header

    # -- internal: PR rows -------------------------------------------------

    def _build_pr_row(self, pr: PRInfo) -> Gtk.ListBoxRow:
        """Build a single PR row for the ListBox."""
        row = Gtk.ListBoxRow()
        row.set_activatable(True)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.get_style_context().add_class("pr-row")

        # Status dot.
        dot = Gtk.Label(label="\u25cf")
        dot.set_valign(Gtk.Align.START)
        dot.get_style_context().add_class("dot")
        if pr.review_requested:
            dot.get_style_context().add_class("review-requested")
        elif pr.assigned:
            dot.get_style_context().add_class("assigned")
        hbox.pack_start(dot, expand=False, fill=False, padding=0)

        # Info area: repo#num, title, author + time.
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # Line 1: repo + number.
        repo_label = Gtk.Label()
        repo_label.set_markup(f"<b>{escape_markup(pr.repo)}</b> #{pr.number}")
        repo_label.set_halign(Gtk.Align.START)
        repo_label.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.pack_start(repo_label, expand=False, fill=False, padding=0)

        # Line 2: title.
        title_label = Gtk.Label(label=pr.title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_max_width_chars(50)
        title_label.get_style_context().add_class("pr-title")
        info_box.pack_start(title_label, expand=False, fill=False, padding=0)

        # Line 3: author + relative time.
        meta_text = f"by {pr.author} \u00b7 {relative_time(pr.updated_at)}"
        meta_label = Gtk.Label(label=meta_text)
        meta_label.set_halign(Gtk.Align.START)
        meta_label.get_style_context().add_class("dim")
        info_box.pack_start(meta_label, expand=False, fill=False, padding=0)

        hbox.pack_start(info_box, expand=True, fill=True, padding=0)
        row.add(hbox)
        return row

    # -- internal: state helpers -------------------------------------------

    def _clear_listbox(self) -> None:
        """Remove all rows from the ListBox and destroy their widgets."""
        self._row_urls.clear()
        for child in self._listbox.get_children():
            self._listbox.remove(child)
            child.destroy()

    def _realize_children(self) -> None:
        """Realize all child widgets so they are ready to display.

        If the window is currently visible, ``show_all()`` is called on
        the window itself.  If hidden, only the inner container is shown
        so that GTK allocates sizes without flashing the window on
        screen.
        """
        if self._visible:
            self._window.show_all()
        else:
            # show_all() on the container realizes widgets (sizes, CSS)
            # without making the top-level window visible.
            for child in self._window.get_children():
                child.show_all()

    def _set_visible(self, visible: bool) -> None:  # noqa: FBT001
        """Update the visibility flag and notify the callback."""
        self._visible = visible
        if self._on_visibility_changed is not None:
            self._on_visibility_changed(visible)

    def _show_empty_state(self, message: str) -> None:
        """Show a centered message in the list area."""
        label = Gtk.Label(label=message)
        label.set_justify(Gtk.Justification.CENTER)
        label.get_style_context().add_class("empty-state")

        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_selectable(False)
        row.add(label)
        self._listbox.add(row)

    def _position_near_pointer(self) -> None:
        """Position the window near the mouse pointer.

        Clamps to the current monitor bounds so the window stays
        on-screen.  On Wayland, ``move()`` may be ignored — this is
        acceptable for v1.
        """
        display = Gdk.Display.get_default()
        if display is None:
            return

        seat = display.get_default_seat()
        if seat is None:
            return

        pointer = seat.get_pointer()
        if pointer is None:
            return

        _screen, px, py = pointer.get_position()

        # Find the monitor that contains the pointer.
        monitor = display.get_monitor_at_point(px, py)
        if monitor is None:
            self._window.move(px, py)
            return

        geom = monitor.get_geometry()

        # Get the natural size of the window so we can clamp properly.
        _min_w, natural_w = self._window.get_preferred_width()
        _min_h, natural_h = self._window.get_preferred_height()

        # Try to position below the pointer, aligned so it doesn't
        # go off the right edge.
        x = min(px, geom.x + geom.width - natural_w)
        x = max(x, geom.x)

        y = py + 10  # small offset below cursor
        if y + natural_h > geom.y + geom.height:
            # Not enough room below — place above the pointer instead.
            y = py - natural_h - 10
        y = max(y, geom.y)

        self._window.move(x, y)

    # -- internal: event handlers ------------------------------------------

    def _on_focus_out(self, _window: Gtk.Window, _event: Gdk.EventFocus) -> bool:
        """Hide the window when it loses focus."""
        self.hide()
        return False

    def _on_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        """Handle a PR row click — open the URL in the browser."""
        idx = row.get_index()
        url = self._row_urls.get(idx)
        if url:
            logger.debug("PR row clicked: %s", url)
            self._on_pr_clicked(url)

    def _on_refresh_clicked(self, _button: Gtk.Button) -> None:
        """Handle the header refresh button click."""
        self._on_refresh()
