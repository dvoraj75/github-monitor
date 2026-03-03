"""Pure helper functions for the popup window.

This module is deliberately free of GTK / gi imports so that it can be
unit-tested in environments where the GTK system packages are not
installed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PRInfo

# ---------------------------------------------------------------------------
# Relative time formatting
# ---------------------------------------------------------------------------

_MINUTE = 60
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR
_WEEK = 7 * _DAY
_MONTH = 30 * _DAY  # approximate


def relative_time(dt: datetime, *, now: datetime | None = None) -> str:  # noqa: PLR0911
    """Convert a datetime to a human-readable relative time string.

    Parameters
    ----------
    dt:
        The datetime to format (must be timezone-aware).
    now:
        Optional override for the current time (for deterministic tests).
    """
    if now is None:
        now = datetime.now(tz=UTC)

    delta = int((now - dt).total_seconds())

    if delta < 0:
        # Future timestamp — treat as "just now" rather than crashing.
        return "just now"

    if delta < _MINUTE:
        return "just now"

    if delta < _HOUR:
        minutes = delta // _MINUTE
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

    if delta < _DAY:
        hours = delta // _HOUR
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    if delta < 2 * _WEEK:
        days = delta // _DAY
        return f"{days} day{'s' if days != 1 else ''} ago"

    if delta < 2 * _MONTH:
        weeks = delta // _WEEK
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"

    months = delta // _MONTH
    return f"{months} month{'s' if months != 1 else ''} ago"


# ---------------------------------------------------------------------------
# Footer status text
# ---------------------------------------------------------------------------


def status_text(count: int, last_updated: datetime | None, *, now: datetime | None = None) -> str:
    """Format the footer status string.

    Examples
    --------
    - ``"5 pull requests · Updated 2 hours ago"``
    - ``"1 pull request · Updated just now"``
    - ``"No pull requests"``
    """
    if count == 0:
        label = "No pull requests"
    elif count == 1:
        label = "1 pull request"
    else:
        label = f"{count} pull requests"

    if last_updated is not None:
        label += f" · Updated {relative_time(last_updated, now=now)}"

    return label


# ---------------------------------------------------------------------------
# PR sorting
# ---------------------------------------------------------------------------


def sort_prs(prs: list[PRInfo]) -> list[PRInfo]:
    """Sort PRs: review-requested first, then by updated_at descending.

    Returns a new list; the original is not mutated.

    Within each group (review-requested vs. not), PRs are ordered by
    ``updated_at`` descending so the most recently updated appear first.
    """
    return sorted(
        prs,
        key=lambda pr: (not pr.review_requested, -pr.updated_at.timestamp()),
    )


# ---------------------------------------------------------------------------
# Markup escaping
# ---------------------------------------------------------------------------


def escape_markup(text: str) -> str:
    """Escape text for safe use in Pango markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
