"""Tests for _tray_state.py helpers and the TrayIcon GTK widget.

The pure helper functions (``get_icon_name``, ``get_label``) are tested
directly.  The ``TrayIcon`` class depends on GTK/AppIndicator3, so its
tests stub out ``gi`` / ``gi.repository`` in ``sys.modules`` before
importing ``tray.py``.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

from github_monitor.indicator._tray_state import get_icon_name, get_label

# ---------------------------------------------------------------------------
# get_icon_name
# ---------------------------------------------------------------------------


class TestGetIconName:
    """Icon name selection based on count, review, and connection state."""

    def test_disconnected_overrides_everything(self) -> None:
        """Disconnected state always returns the disconnected icon."""
        result = get_icon_name(5, has_review_requested=True, connected=False)

        assert result == "github-monitor-disconnected"

    def test_zero_prs_connected(self) -> None:
        """Zero PRs with a live connection shows the neutral icon."""
        result = get_icon_name(0, has_review_requested=False, connected=True)

        assert result == "github-monitor"

    def test_has_prs_no_review(self) -> None:
        """PRs present but none requesting review shows the active icon."""
        result = get_icon_name(3, has_review_requested=False, connected=True)

        assert result == "github-monitor-active"

    def test_has_prs_with_review_requested(self) -> None:
        """PRs with review requested shows the alert icon."""
        result = get_icon_name(2, has_review_requested=True, connected=True)

        assert result == "github-monitor-alert"

    def test_review_requested_takes_priority_over_active(self) -> None:
        """When both count > 0 and review requested, alert wins over active."""
        result = get_icon_name(1, has_review_requested=True, connected=True)

        assert result == "github-monitor-alert"

    def test_disconnected_with_zero_prs(self) -> None:
        """Disconnected with zero PRs still shows disconnected icon."""
        result = get_icon_name(0, has_review_requested=False, connected=False)

        assert result == "github-monitor-disconnected"

    def test_zero_prs_with_review_flag_shows_neutral(self) -> None:
        """Zero PRs with review flag set (edge case) shows neutral, not alert."""
        result = get_icon_name(0, has_review_requested=True, connected=True)

        assert result == "github-monitor"


# ---------------------------------------------------------------------------
# get_label
# ---------------------------------------------------------------------------


class TestGetLabel:
    """Label formatting from PR count."""

    def test_zero_returns_empty_string(self) -> None:
        """Zero PRs should show no label."""
        assert get_label(0) == ""

    def test_positive_returns_count_string(self) -> None:
        """Positive count returns the number as a string."""
        assert get_label(5) == "5"

    def test_large_number(self) -> None:
        """Large counts are formatted as plain integers."""
        assert get_label(42) == "42"


# ---------------------------------------------------------------------------
# Stub out GTK / AppIndicator3 so tray.py is importable in CI
# ---------------------------------------------------------------------------

_gi_stub = MagicMock()
_gi_stub.require_version = MagicMock()

for _mod in ("gi", "gi.repository"):
    if _mod not in sys.modules:
        sys.modules[_mod] = _gi_stub  # type: ignore[assignment]

from github_monitor.indicator.tray import TrayIcon  # noqa: E402

# ---------------------------------------------------------------------------
# TrayIcon — construction
# ---------------------------------------------------------------------------


class TestTrayIconConstruction:
    """TrayIcon constructs an AppIndicator3 indicator with menu."""

    def test_creates_indicator(self) -> None:
        on_activate = MagicMock()
        on_refresh = MagicMock()
        on_quit = MagicMock()

        tray = TrayIcon(on_activate, on_refresh, on_quit, icon_theme="light")

        # The internal indicator should be set up
        assert tray._indicator is not None
        assert tray._count == 0
        assert tray._has_review_requested is False
        assert tray._connected is False

    def test_builds_menu(self) -> None:
        on_activate = MagicMock()
        on_refresh = MagicMock()
        on_quit = MagicMock()

        tray = TrayIcon(on_activate, on_refresh, on_quit)

        assert tray._menu is not None
        assert tray._show_prs_item is not None


# ---------------------------------------------------------------------------
# TrayIcon — set_pr_count
# ---------------------------------------------------------------------------


class TestTrayIconSetPrCount:
    """set_pr_count updates icon and label via the indicator."""

    def test_updates_icon_and_label(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())

        tray.set_pr_count(5, has_review_requested=True)

        assert tray._count == 5
        assert tray._has_review_requested is True
        # set_icon_full and set_label should have been called
        tray._indicator.set_icon_full.assert_called()
        tray._indicator.set_label.assert_called()

    def test_zero_count_shows_neutral_icon(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())
        tray._connected = True

        tray.set_pr_count(0, has_review_requested=False)

        # Last call to set_icon_full should use the neutral icon name
        icon_call = tray._indicator.set_icon_full.call_args
        assert icon_call[0][0] == "github-monitor"

    def test_review_requested_shows_alert_icon(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())
        tray._connected = True

        tray.set_pr_count(3, has_review_requested=True)

        icon_call = tray._indicator.set_icon_full.call_args
        assert icon_call[0][0] == "github-monitor-alert"


# ---------------------------------------------------------------------------
# TrayIcon — set_connected
# ---------------------------------------------------------------------------


class TestTrayIconSetConnected:
    """set_connected updates the icon to reflect daemon connection state."""

    def test_connected_updates_state(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())

        tray.set_connected(connected=True)

        assert tray._connected is True
        tray._indicator.set_icon_full.assert_called()

    def test_disconnected_shows_disconnected_icon(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())

        tray.set_connected(connected=False)

        icon_call = tray._indicator.set_icon_full.call_args
        assert icon_call[0][0] == "github-monitor-disconnected"


# ---------------------------------------------------------------------------
# TrayIcon — set_window_visible
# ---------------------------------------------------------------------------


class TestTrayIconSetWindowVisible:
    """set_window_visible toggles the menu item label."""

    def test_visible_shows_hide_prs(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())

        tray.set_window_visible(visible=True)

        tray._show_prs_item.set_label.assert_called_with("Hide PRs")

    def test_hidden_shows_show_prs(self) -> None:
        tray = TrayIcon(MagicMock(), MagicMock(), MagicMock())

        tray.set_window_visible(visible=False)

        tray._show_prs_item.set_label.assert_called_with("Show PRs")


# ---------------------------------------------------------------------------
# TrayIcon — menu callbacks
# ---------------------------------------------------------------------------


class TestTrayIconMenuCallbacks:
    """Menu items delegate to the correct callbacks."""

    def test_show_prs_activate_calls_on_activate(self) -> None:
        on_activate = MagicMock()
        tray = TrayIcon(on_activate, MagicMock(), MagicMock())

        tray._on_show_prs_activate(MagicMock())

        on_activate.assert_called_once()

    def test_refresh_activate_calls_on_refresh(self) -> None:
        on_refresh = MagicMock()
        tray = TrayIcon(MagicMock(), on_refresh, MagicMock())

        tray._on_refresh_activate(MagicMock())

        on_refresh.assert_called_once()

    def test_quit_activate_calls_on_quit(self) -> None:
        on_quit = MagicMock()
        tray = TrayIcon(MagicMock(), MagicMock(), on_quit)

        tray._on_quit_activate(MagicMock())

        on_quit.assert_called_once()
