"""Tests for the pure helper functions in _tray_state.py.

The TrayIcon class itself depends on GTK/AppIndicator3 system packages
and is tested manually.  These tests cover the state logic (icon name
selection and label formatting) which lives in _tray_state.py, free of
GTK imports.
"""

from __future__ import annotations

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
