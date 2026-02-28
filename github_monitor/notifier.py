"""Desktop notifications for new pull requests via notify-send."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .poller import PullRequest

logger = logging.getLogger(__name__)

# Maximum number of PRs to show as individual notifications.
# Above this threshold a single summary notification is sent instead.
_INDIVIDUAL_THRESHOLD = 3

# Maximum number of PRs listed in a batch notification body.
_BATCH_BODY_LIMIT = 5


async def notify_new_prs(new_prs: list[PullRequest]) -> None:
    """Send desktop notifications for newly discovered PRs.

    If there are 1-3 new PRs, each gets its own notification.
    If there are more than 3, a single summary notification is sent
    listing up to the first 5 PRs to avoid desktop spam.
    """
    if not new_prs:
        return

    if len(new_prs) <= _INDIVIDUAL_THRESHOLD:
        for pr in new_prs:
            await _send_notification(
                summary=f"PR Review: {pr.repo_full_name}",
                body=f"#{pr.number} {pr.title}\nby {pr.author}",
                url=pr.url,
            )
    else:
        body = "\n".join(f"- {pr.repo_full_name}#{pr.number}: {pr.title}" for pr in new_prs[:_BATCH_BODY_LIMIT])
        await _send_notification(
            summary=f"{len(new_prs)} new PR review requests",
            body=body,
        )


async def _send_notification(
    summary: str,
    body: str,
    *,
    url: str | None = None,  # noqa: ARG001  # reserved for future action callbacks
    urgency: str = "normal",
) -> None:
    """Call notify-send as an async subprocess.

    Parameters
    ----------
    summary:
        Notification title.
    body:
        Notification body text.
    url:
        Optional URL (currently unused by notify-send, reserved for
        future use with action callbacks).
    urgency:
        Notification urgency level (low / normal / critical).
    """
    cmd = [
        "notify-send",
        "--app-name=github-monitor",
        f"--urgency={urgency}",
        "--icon=github",
        summary,
        body,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "notify-send failed (exit %d): %s",
                proc.returncode,
                stderr.decode().strip(),
            )
    except FileNotFoundError:
        logger.warning("notify-send not found. Install libnotify-bin.")
