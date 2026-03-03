"""Tests for the pure helper functions in _window_helpers.py.

The PRWindow class itself depends on GTK system packages and is tested
manually.  These tests cover the logic that lives in _window_helpers.py,
which is deliberately free of GTK imports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from github_monitor.indicator._window_helpers import escape_markup, relative_time, sort_prs, status_text
from github_monitor.indicator.models import PRInfo

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
