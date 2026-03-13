"""Desktop notifications for new pull requests via notify-send.

Supports:
- PR author avatar as notification icon (downloaded from GitHub)
- Clickable notifications that open the PR in a browser
- Uses the XDG Desktop Portal (D-Bus) to open URLs, which works
  correctly from sandboxed systemd services.  Falls back to xdg-open
  when the portal is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

from .url_opener import open_url

if TYPE_CHECKING:
    from .poller import PullRequest

from .config import RepoNotificationConfig

logger = logging.getLogger(__name__)

# Maximum number of PRs to show as individual notifications.
# Above this threshold a single summary notification is sent instead.
_INDIVIDUAL_THRESHOLD = 3

# Maximum number of PRs listed in a batch notification body.
_BATCH_BODY_LIMIT = 5

# Avatar size in pixels (appended as ?s=N to GitHub avatar URL)
_AVATAR_SIZE = 64

# Directory for cached avatar files — use XDG_CACHE_HOME (default ~/.cache)
_AVATAR_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "forgewatch" / "avatars"

# In-memory cache: avatar_url -> local file path
_avatar_cache: dict[str, Path] = {}

# Background tasks kept alive to prevent garbage collection.
# When a notification with a URL is sent, we spawn a background task
# that waits for the user to click the notification and then opens
# the PR in a browser.  The task reference is stored here so it is not
# garbage-collected before completion.
_background_tasks: set[asyncio.Task[None]] = set()

# Default repo override — used when a repo has no explicit config.
_DEFAULT_REPO_OVERRIDE = RepoNotificationConfig()


async def _download_avatar(avatar_url: str, session: aiohttp.ClientSession) -> str | None:
    """Download a GitHub avatar to a local temp file.

    Returns the local file path as a string, or None on failure.
    Results are cached so the same avatar is only downloaded once
    per daemon lifetime.
    """
    if not avatar_url:
        return None

    # Check in-memory cache
    if avatar_url in _avatar_cache:
        cached = _avatar_cache[avatar_url]
        if cached.exists():
            return str(cached)
        # File was deleted — re-download
        del _avatar_cache[avatar_url]

    # Ensure cache directory exists
    _AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Deterministic filename from URL
    url_hash = hashlib.md5(avatar_url.encode()).hexdigest()  # noqa: S324
    dest = _AVATAR_CACHE_DIR / f"{url_hash}.png"

    # If already on disk (from a previous run), reuse
    if dest.exists():
        _avatar_cache[avatar_url] = dest
        return str(dest)

    data = await _fetch_avatar_bytes(avatar_url, session)
    if data is None:
        return None

    try:
        dest.write_bytes(data)
    except OSError:
        logger.debug("Failed to write avatar to %s", dest, exc_info=True)
        return None

    _avatar_cache[avatar_url] = dest
    return str(dest)


async def _fetch_avatar_bytes(avatar_url: str, session: aiohttp.ClientSession) -> bytes | None:
    """Fetch avatar image bytes from GitHub. Returns None on failure."""
    sized_url = f"{avatar_url}?s={_AVATAR_SIZE}"
    try:
        async with session.get(sized_url) as resp:
            if resp.status != 200:  # noqa: PLR2004
                logger.debug("Avatar download failed (HTTP %d): %s", resp.status, sized_url)
                return None
            return await resp.read()
    except (aiohttp.ClientError, TimeoutError, OSError):
        logger.debug("Avatar download error: %s", sized_url, exc_info=True)
        return None


async def notify_new_prs(
    new_prs: list[PullRequest],
    *,
    threshold: int = _INDIVIDUAL_THRESHOLD,
    urgency: str = "normal",
    grouping: str = "flat",
    repo_overrides: dict[str, RepoNotificationConfig] | None = None,
) -> None:
    """Send desktop notifications for newly discovered PRs.

    If there are 1-*threshold* new PRs, each gets its own notification
    with the author's avatar as the icon and a clickable action to open
    the PR in a browser.

    If there are more than *threshold*, a single summary notification is
    sent listing up to the first 5 PRs to avoid desktop spam.

    When *grouping* is ``"repo"``, PRs are grouped by repository and
    each group is handled independently (its own threshold / summary).

    *repo_overrides* allows per-repo settings: disable notifications
    for specific repos, or override urgency / threshold.
    """
    if not new_prs:
        return

    if grouping == "repo":
        await _notify_grouped_by_repo(new_prs, threshold=threshold, urgency=urgency, repo_overrides=repo_overrides)
    else:
        await _notify_flat(new_prs, threshold=threshold, urgency=urgency, repo_overrides=repo_overrides)


async def _notify_flat(
    new_prs: list[PullRequest],
    *,
    threshold: int,
    urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> None:
    """Send notifications in flat mode (original behaviour)."""
    filtered = _filter_disabled_repos(new_prs, repo_overrides)
    if not filtered:
        return

    if len(filtered) <= threshold:
        async with aiohttp.ClientSession() as session:
            for pr in filtered:
                pr_urgency = _get_repo_urgency(pr.repo_full_name, urgency, repo_overrides)
                icon = await _download_avatar(pr.author_avatar_url, session)
                await _send_notification(
                    summary=f"PR Review: {pr.repo_full_name}",
                    body=f"#{pr.number} {pr.title}\nby {pr.author}",
                    url=pr.url,
                    icon=icon,
                    urgency=pr_urgency,
                )
    else:
        body = "\n".join(f"- {pr.repo_full_name}#{pr.number}: {pr.title}" for pr in filtered[:_BATCH_BODY_LIMIT])
        await _send_notification(
            summary=f"{len(filtered)} new PR review requests",
            body=body,
            urgency=urgency,
        )


async def _notify_grouped_by_repo(
    new_prs: list[PullRequest],
    *,
    threshold: int,
    urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> None:
    """Send notifications grouped by repository."""
    filtered = _filter_disabled_repos(new_prs, repo_overrides)
    if not filtered:
        return

    sorted_prs = sorted(filtered, key=lambda pr: pr.repo_full_name)

    async with aiohttp.ClientSession() as session:
        for repo_name, group in itertools.groupby(sorted_prs, key=lambda pr: pr.repo_full_name):
            repo_prs = list(group)
            repo_threshold = _get_repo_threshold(repo_name, threshold, repo_overrides)
            repo_urgency = _get_repo_urgency(repo_name, urgency, repo_overrides)

            if len(repo_prs) <= repo_threshold:
                for pr in repo_prs:
                    icon = await _download_avatar(pr.author_avatar_url, session)
                    await _send_notification(
                        summary=f"PR Review: {pr.repo_full_name}",
                        body=f"#{pr.number} {pr.title}\nby {pr.author}",
                        url=pr.url,
                        icon=icon,
                        urgency=repo_urgency,
                    )
            else:
                body = "\n".join(f"- #{pr.number}: {pr.title}" for pr in repo_prs[:_BATCH_BODY_LIMIT])
                await _send_notification(
                    summary=f"{len(repo_prs)} new PRs in {repo_name}",
                    body=body,
                    urgency=repo_urgency,
                )


def _filter_disabled_repos(
    prs: list[PullRequest],
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> list[PullRequest]:
    """Remove PRs from repos that have notifications disabled."""
    if not repo_overrides:
        return prs
    return [pr for pr in prs if repo_overrides.get(pr.repo_full_name, _DEFAULT_REPO_OVERRIDE).enabled]


def _get_repo_urgency(
    repo_name: str,
    default_urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> str:
    """Return the urgency for a repo, falling back to the global default."""
    if not repo_overrides or repo_name not in repo_overrides:
        return default_urgency
    return repo_overrides[repo_name].urgency


def _get_repo_threshold(
    repo_name: str,
    default_threshold: int,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> int:
    """Return the threshold for a repo, falling back to the global default."""
    if not repo_overrides or repo_name not in repo_overrides:
        return default_threshold
    return repo_overrides[repo_name].threshold


async def _send_notification(
    summary: str,
    body: str,
    *,
    url: str | None = None,
    icon: str | None = None,
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
        Optional URL. When provided, an "Open" action button is added
        to the notification.  If the user clicks it, the URL is opened
        in the default browser via the XDG Desktop Portal (or
        ``xdg-open`` as a fallback).
    icon:
        Optional path to an icon file.  Falls back to the generic
        "github" icon name when not provided.
    urgency:
        Notification urgency level (low / normal / critical).
    """
    icon_arg = f"--icon={icon}" if icon else "--icon=github"
    cmd = [
        "notify-send",
        "--app-name=forgewatch",
        f"--urgency={urgency}",
        icon_arg,
    ]

    if url:
        cmd.append("--action=open=Open")

    cmd.extend(["--", summary, body])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if url else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        if url:
            # notify-send --action blocks until the user interacts or
            # the notification expires.  Run the wait in a background
            # task so we don't block the poll loop.
            task = asyncio.create_task(_wait_and_open(proc, url))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        else:
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    "notify-send failed (exit %d): %s",
                    proc.returncode,
                    stderr.decode().strip(),
                )
    except FileNotFoundError:
        logger.warning("notify-send not found. Install libnotify-bin.")


async def _wait_and_open(proc: asyncio.subprocess.Process, url: str) -> None:
    """Wait for a notify-send process and open *url* if the user clicked "Open"."""
    try:
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "notify-send failed (exit %d): %s",
                proc.returncode,
                stderr.decode().strip(),
            )
            return

        action = stdout.decode().strip()
        if action == "open":
            await open_url(url)
    except (OSError, ValueError):
        logger.debug("Error waiting for notification action", exc_info=True)
