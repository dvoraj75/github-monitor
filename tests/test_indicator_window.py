"""Tests for _window_helpers.py helpers, PRWindow GTK widget, and models.

The pure helper functions are tested directly.  The ``PRWindow`` class
depends on GTK system packages, so its tests stub out ``gi`` /
``gi.repository`` in ``sys.modules`` before importing ``window.py``.
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from github_monitor.indicator._window_helpers import escape_markup, relative_time, sort_prs, status_text
from github_monitor.indicator.models import DaemonStatus, PRInfo

# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)


def _make_pr(
    *,
    url: str = "https://github.com/owner/repo/pull/1",
    title: str = "Fix bug",
    repo: str = "owner/repo",
    author: str = "octocat",
    author_avatar_url: str = "https://avatars.githubusercontent.com/u/1",
    number: int = 1,
    updated_at: datetime = _NOW,
    review_requested: bool = False,
    assigned: bool = False,
) -> PRInfo:
    """Build a PRInfo with sensible defaults."""
    return PRInfo(
        url=url,
        title=title,
        repo=repo,
        author=author,
        author_avatar_url=author_avatar_url,
        number=number,
        updated_at=updated_at,
        review_requested=review_requested,
        assigned=assigned,
    )


# ---------------------------------------------------------------------------
# relative_time
# ---------------------------------------------------------------------------


class TestRelativeTime:
    """Relative time formatting from a datetime."""

    def test_just_now_zero_delta(self) -> None:
        assert relative_time(_NOW, now=_NOW) == "just now"

    def test_just_now_30_seconds(self) -> None:
        dt = _NOW - timedelta(seconds=30)
        assert relative_time(dt, now=_NOW) == "just now"

    def test_boundary_59_seconds_is_just_now(self) -> None:
        dt = _NOW - timedelta(seconds=59)
        assert relative_time(dt, now=_NOW) == "just now"

    def test_one_minute_ago(self) -> None:
        dt = _NOW - timedelta(minutes=1)
        assert relative_time(dt, now=_NOW) == "1 minute ago"

    def test_minutes_ago(self) -> None:
        dt = _NOW - timedelta(minutes=5)
        assert relative_time(dt, now=_NOW) == "5 minutes ago"

    def test_59_minutes_ago(self) -> None:
        dt = _NOW - timedelta(minutes=59)
        assert relative_time(dt, now=_NOW) == "59 minutes ago"

    def test_one_hour_ago(self) -> None:
        dt = _NOW - timedelta(hours=1)
        assert relative_time(dt, now=_NOW) == "1 hour ago"

    def test_hours_ago(self) -> None:
        dt = _NOW - timedelta(hours=3)
        assert relative_time(dt, now=_NOW) == "3 hours ago"

    def test_23_hours_ago(self) -> None:
        dt = _NOW - timedelta(hours=23)
        assert relative_time(dt, now=_NOW) == "23 hours ago"

    def test_one_day_ago(self) -> None:
        dt = _NOW - timedelta(days=1)
        assert relative_time(dt, now=_NOW) == "1 day ago"

    def test_days_ago(self) -> None:
        dt = _NOW - timedelta(days=5)
        assert relative_time(dt, now=_NOW) == "5 days ago"

    def test_13_days_is_still_days(self) -> None:
        """13 days is below the 2-week threshold, so still shows days."""
        dt = _NOW - timedelta(days=13)
        assert relative_time(dt, now=_NOW) == "13 days ago"

    def test_one_week_ago(self) -> None:
        """14 days crosses into the weeks range."""
        dt = _NOW - timedelta(weeks=2)
        assert relative_time(dt, now=_NOW) == "2 weeks ago"

    def test_weeks_ago(self) -> None:
        dt = _NOW - timedelta(weeks=3)
        assert relative_time(dt, now=_NOW) == "3 weeks ago"

    def test_one_month_ago(self) -> None:
        """~60 days crosses into months range (2 * 30 day threshold)."""
        dt = _NOW - timedelta(days=62)
        assert relative_time(dt, now=_NOW) == "2 months ago"

    def test_months_ago(self) -> None:
        dt = _NOW - timedelta(days=95)
        assert relative_time(dt, now=_NOW) == "3 months ago"

    def test_future_timestamp_treated_as_just_now(self) -> None:
        dt = _NOW + timedelta(hours=1)
        assert relative_time(dt, now=_NOW) == "just now"


# ---------------------------------------------------------------------------
# status_text
# ---------------------------------------------------------------------------


class TestStatusText:
    """Footer status text formatting."""

    def test_zero_prs(self) -> None:
        assert status_text(0, None) == "No pull requests"

    def test_zero_prs_with_last_updated(self) -> None:
        last = _NOW - timedelta(minutes=3)
        result = status_text(0, last, now=_NOW)
        assert result == "No pull requests · Updated 3 minutes ago"

    def test_one_pr_singular(self) -> None:
        result = status_text(1, _NOW, now=_NOW)
        assert result == "1 pull request · Updated just now"

    def test_multiple_prs_with_time(self) -> None:
        last = _NOW - timedelta(hours=2)
        result = status_text(5, last, now=_NOW)
        assert result == "5 pull requests · Updated 2 hours ago"

    def test_prs_without_last_updated(self) -> None:
        result = status_text(5, None)
        assert result == "5 pull requests"


# ---------------------------------------------------------------------------
# sort_prs
# ---------------------------------------------------------------------------


class TestSortPrs:
    """PR list sorting: review-requested first, then by updated_at desc."""

    def test_empty_list(self) -> None:
        assert sort_prs([]) == []

    def test_single_pr_unchanged(self) -> None:
        pr = _make_pr()
        result = sort_prs([pr])
        assert result == [pr]

    def test_review_requested_first(self) -> None:
        """Review-requested PRs sort before non-review PRs."""
        pr_normal = _make_pr(number=1, review_requested=False, updated_at=_NOW)
        pr_review = _make_pr(number=2, review_requested=True, updated_at=_NOW - timedelta(days=1))

        result = sort_prs([pr_normal, pr_review])

        assert result[0].number == 2  # review-requested comes first
        assert result[1].number == 1

    def test_within_group_sorted_by_updated_at_descending(self) -> None:
        """Within the same review group, most recently updated first."""
        pr_old = _make_pr(number=1, review_requested=True, updated_at=_NOW - timedelta(hours=5))
        pr_new = _make_pr(number=2, review_requested=True, updated_at=_NOW - timedelta(hours=1))

        result = sort_prs([pr_old, pr_new])

        assert result[0].number == 2  # newer first
        assert result[1].number == 1

    def test_full_ordering(self) -> None:
        """Comprehensive test: review group sorted by time, then non-review group sorted by time."""
        pr_review_old = _make_pr(number=1, review_requested=True, updated_at=_NOW - timedelta(hours=3))
        pr_review_new = _make_pr(number=2, review_requested=True, updated_at=_NOW - timedelta(hours=1))
        pr_normal_old = _make_pr(number=3, review_requested=False, updated_at=_NOW - timedelta(hours=4))
        pr_normal_new = _make_pr(number=4, review_requested=False, updated_at=_NOW - timedelta(hours=2))

        result = sort_prs([pr_normal_old, pr_review_old, pr_normal_new, pr_review_new])
        numbers = [pr.number for pr in result]

        assert numbers == [2, 1, 4, 3]

    def test_does_not_mutate_original(self) -> None:
        """sort_prs returns a new list; the original is unchanged."""
        original = [
            _make_pr(number=1, updated_at=_NOW - timedelta(hours=1)),
            _make_pr(number=2, updated_at=_NOW),
        ]
        original_copy = list(original)

        sort_prs(original)

        assert original == original_copy


# ---------------------------------------------------------------------------
# escape_markup
# ---------------------------------------------------------------------------


class TestEscapeMarkup:
    """Pango markup escaping for safe display in GTK labels."""

    def test_plain_text_unchanged(self) -> None:
        assert escape_markup("hello world") == "hello world"

    def test_ampersand_escaped(self) -> None:
        assert escape_markup("A & B") == "A &amp; B"

    def test_less_than_escaped(self) -> None:
        assert escape_markup("a < b") == "a &lt; b"

    def test_greater_than_escaped(self) -> None:
        assert escape_markup("a > b") == "a &gt; b"

    def test_all_special_chars_escaped(self) -> None:
        assert escape_markup("<tag>&value</tag>") == "&lt;tag&gt;&amp;value&lt;/tag&gt;"

    def test_empty_string(self) -> None:
        assert escape_markup("") == ""

    def test_repo_name_with_no_special_chars(self) -> None:
        """Typical repo name should pass through unchanged."""
        assert escape_markup("owner/repo") == "owner/repo"


# ---------------------------------------------------------------------------
# Frozen dataclass models: PRInfo and DaemonStatus
# ---------------------------------------------------------------------------


class TestPRInfoModel:
    """PRInfo frozen dataclass properties."""

    def test_fields_accessible(self) -> None:
        pr = _make_pr(title="My PR", number=42, author="bob")
        assert pr.title == "My PR"
        assert pr.number == 42
        assert pr.author == "bob"

    def test_frozen_raises_on_assignment(self) -> None:
        pr = _make_pr()
        try:
            pr.title = "changed"  # type: ignore[misc]
            msg = "Expected FrozenInstanceError"
            raise AssertionError(msg)
        except dataclasses.FrozenInstanceError:
            pass

    def test_equality(self) -> None:
        pr_a = _make_pr(number=1, title="Same")
        pr_b = _make_pr(number=1, title="Same")
        assert pr_a == pr_b

    def test_inequality(self) -> None:
        pr_a = _make_pr(number=1)
        pr_b = _make_pr(number=2)
        assert pr_a != pr_b


class TestDaemonStatusModel:
    """DaemonStatus frozen dataclass properties."""

    def test_fields_accessible(self) -> None:
        status = DaemonStatus(pr_count=5, last_updated=_NOW)
        assert status.pr_count == 5
        assert status.last_updated == _NOW

    def test_last_updated_none(self) -> None:
        status = DaemonStatus(pr_count=0, last_updated=None)
        assert status.last_updated is None

    def test_frozen_raises_on_assignment(self) -> None:
        status = DaemonStatus(pr_count=3, last_updated=None)
        try:
            status.pr_count = 10  # type: ignore[misc]
            msg = "Expected FrozenInstanceError"
            raise AssertionError(msg)
        except dataclasses.FrozenInstanceError:
            pass

    def test_equality(self) -> None:
        a = DaemonStatus(pr_count=2, last_updated=_NOW)
        b = DaemonStatus(pr_count=2, last_updated=_NOW)
        assert a == b


# ---------------------------------------------------------------------------
# Stub out GTK / Gdk / Pango so window.py is importable in CI
# ---------------------------------------------------------------------------

_gi_stub = MagicMock()
_gi_stub.require_version = MagicMock()

for _mod in ("gi", "gi.repository"):
    if _mod not in sys.modules:
        sys.modules[_mod] = _gi_stub  # type: ignore[assignment]

from github_monitor.indicator.window import PRWindow  # noqa: E402

# ---------------------------------------------------------------------------
# PRWindow — construction
# ---------------------------------------------------------------------------


class TestPRWindowConstruction:
    """PRWindow builds the GTK window and internal widgets."""

    def test_creates_window_with_callbacks(self) -> None:
        on_pr_clicked = MagicMock()
        on_refresh = MagicMock()
        on_visibility = MagicMock()

        win = PRWindow(on_pr_clicked, on_refresh, on_visibility_changed=on_visibility)

        assert win._on_pr_clicked is on_pr_clicked
        assert win._on_refresh is on_refresh
        assert win._on_visibility_changed is on_visibility

    def test_initial_state_not_visible(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())

        assert win.visible is False

    def test_row_urls_initially_empty(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())

        assert win._row_urls == {}

    def test_visibility_changed_callback_optional(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())

        assert win._on_visibility_changed is None


# ---------------------------------------------------------------------------
# PRWindow — update_prs
# ---------------------------------------------------------------------------


class TestPRWindowUpdatePrs:
    """update_prs rebuilds rows and updates footer."""

    def test_populates_row_urls(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        prs = [
            _make_pr(number=1, url="https://github.com/o/r/pull/1"),
            _make_pr(number=2, url="https://github.com/o/r/pull/2"),
        ]
        status = DaemonStatus(pr_count=2, last_updated=_NOW)

        win.update_prs(prs, status)

        assert len(win._row_urls) == 2
        # URLs should be present (order may differ due to sorting)
        assert set(win._row_urls.values()) == {
            "https://github.com/o/r/pull/1",
            "https://github.com/o/r/pull/2",
        }

    def test_empty_prs_clears_row_urls(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        # Populate first
        prs = [_make_pr(number=1)]
        win.update_prs(prs, DaemonStatus(pr_count=1, last_updated=_NOW))
        assert len(win._row_urls) == 1

        # Now update with empty
        win.update_prs([], DaemonStatus(pr_count=0, last_updated=_NOW))
        assert win._row_urls == {}

    def test_updates_footer_text(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        status = DaemonStatus(pr_count=3, last_updated=None)

        win.update_prs([_make_pr(number=i) for i in range(3)], status)

        win._footer.set_text.assert_called()

    def test_status_none_uses_prs_length_for_count(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        prs = [_make_pr(number=1), _make_pr(number=2)]

        win.update_prs(prs, None)

        # Footer should have been set with count=2
        win._footer.set_text.assert_called()


# ---------------------------------------------------------------------------
# PRWindow — show / hide / toggle
# ---------------------------------------------------------------------------


class TestPRWindowVisibility:
    """show(), hide(), toggle() manage window visibility."""

    def test_show_sets_visible(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())

        with patch.object(win, "_position_near_pointer"):
            win.show()

        assert win.visible is True

    def test_hide_clears_visible(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        with patch.object(win, "_position_near_pointer"):
            win.show()

        win.hide()

        assert win.visible is False

    def test_toggle_from_hidden_to_visible(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        assert win.visible is False

        with patch.object(win, "_position_near_pointer"):
            win.toggle()

        assert win.visible is True

    def test_toggle_from_visible_to_hidden(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        with patch.object(win, "_position_near_pointer"):
            win.show()
        assert win.visible is True

        win.toggle()

        assert win.visible is False

    def test_show_calls_visibility_changed_callback(self) -> None:
        cb = MagicMock()
        win = PRWindow(MagicMock(), MagicMock(), on_visibility_changed=cb)

        with patch.object(win, "_position_near_pointer"):
            win.show()

        cb.assert_called_with(True)  # noqa: FBT003

    def test_hide_calls_visibility_changed_callback(self) -> None:
        cb = MagicMock()
        win = PRWindow(MagicMock(), MagicMock(), on_visibility_changed=cb)
        with patch.object(win, "_position_near_pointer"):
            win.show()
        cb.reset_mock()

        win.hide()

        cb.assert_called_with(False)  # noqa: FBT003

    def test_no_callback_when_none(self) -> None:
        """When on_visibility_changed is None, show/hide should not error."""
        win = PRWindow(MagicMock(), MagicMock(), on_visibility_changed=None)

        with patch.object(win, "_position_near_pointer"):
            win.show()
        win.hide()

        assert win.visible is False


# ---------------------------------------------------------------------------
# PRWindow — set_disconnected
# ---------------------------------------------------------------------------


class TestPRWindowSetDisconnected:
    """set_disconnected shows a 'not running' message."""

    def test_clears_row_urls(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        win._row_urls = {0: "https://example.com"}

        win.set_disconnected()

        assert win._row_urls == {}

    def test_clears_footer(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())

        win.set_disconnected()

        win._footer.set_text.assert_called_with("")


# ---------------------------------------------------------------------------
# PRWindow — event handlers
# ---------------------------------------------------------------------------


class TestPRWindowEventHandlers:
    """Internal event handlers delegate to callbacks."""

    def test_row_activated_calls_on_pr_clicked(self) -> None:
        on_pr_clicked = MagicMock()
        win = PRWindow(on_pr_clicked, MagicMock())
        win._row_urls = {0: "https://github.com/o/r/pull/1"}

        mock_row = MagicMock()
        mock_row.get_index.return_value = 0

        win._on_row_activated(MagicMock(), mock_row)

        on_pr_clicked.assert_called_once_with("https://github.com/o/r/pull/1")

    def test_row_activated_ignores_unknown_index(self) -> None:
        on_pr_clicked = MagicMock()
        win = PRWindow(on_pr_clicked, MagicMock())
        win._row_urls = {}

        mock_row = MagicMock()
        mock_row.get_index.return_value = 99

        win._on_row_activated(MagicMock(), mock_row)

        on_pr_clicked.assert_not_called()

    def test_refresh_clicked_calls_on_refresh(self) -> None:
        on_refresh = MagicMock()
        win = PRWindow(MagicMock(), on_refresh)

        win._on_refresh_clicked(MagicMock())

        on_refresh.assert_called_once()

    def test_focus_out_hides_window(self) -> None:
        win = PRWindow(MagicMock(), MagicMock())
        with patch.object(win, "_position_near_pointer"):
            win.show()
        assert win.visible is True

        result = win._on_focus_out(MagicMock(), MagicMock())

        assert win.visible is False
        assert result is False
