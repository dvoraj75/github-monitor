"""Pure state logic for the tray icon.

This module is deliberately free of GTK / AppIndicator3 imports so that
it can be unit-tested in environments where ``gi`` is not installed.
"""

from __future__ import annotations

from enum import StrEnum


# Icon name constants — resolved from the icon theme or a custom path.
class Icon(StrEnum):
    NEUTRAL = "github-monitor"
    ACTIVE = "github-monitor-active"
    ALERT = "github-monitor-alert"
    DISCONNECTED = "github-monitor-disconnected"


def get_icon_name(count: int, *, has_review_requested: bool, connected: bool) -> Icon:
    """Determine the icon name based on current state.

    Priority (highest to lowest):
    1. Disconnected → dimmed icon
    2. Has review-requested PRs → alert icon
    3. Has any PRs → active icon
    4. Otherwise → neutral icon
    """
    if not connected:
        return Icon.DISCONNECTED
    if count > 0 and has_review_requested:
        return Icon.ALERT
    if count > 0:
        return Icon.ACTIVE
    return Icon.NEUTRAL


def get_label(count: int) -> str:
    """Format the tray label from a PR count.

    Returns an empty string for zero (no label shown), otherwise
    the count as a string.
    """
    if count == 0:
        return ""
    return str(count)
