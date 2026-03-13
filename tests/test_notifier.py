"""Tests for forgewatch.notifier."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from forgewatch.notifier import (
    _BATCH_BODY_LIMIT,
    _INDIVIDUAL_THRESHOLD,
    _download_avatar,
    _send_notification,
    _wait_and_open,
    notify_new_prs,
)
from forgewatch.poller import PullRequest
from tests.conftest import _mock_process

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _make_pr(
    number: int = 1,
    repo: str = "owner/repo",
    *,
    title: str = "Fix bug",
    author: str = "alice",
    author_avatar_url: str = "https://avatars.githubusercontent.com/u/12345",
) -> PullRequest:
    """Build a PullRequest for testing."""
    return PullRequest(
        url=f"https://github.com/{repo}/pull/{number}",
        api_url=f"https://api.github.com/repos/{repo}/pulls/{number}",
        title=title,
        repo_full_name=repo,
        author=author,
        author_avatar_url=author_avatar_url,
        number=number,
        updated_at=_NOW,
        review_requested=True,
        assigned=False,
    )


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — empty list
# ---------------------------------------------------------------------------


class TestNotifyNewPrsEmpty:
    """notify_new_prs should be a no-op for an empty list."""

    async def test_empty_list_does_nothing(self) -> None:
        with patch("forgewatch.notifier.asyncio.create_subprocess_exec") as mock_exec:
            await notify_new_prs([])
            mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — individual notifications (1-3 PRs)
# ---------------------------------------------------------------------------


class TestNotifyNewPrsIndividual:
    """notify_new_prs sends individual notifications for <= 3 PRs."""

    async def test_single_pr_notification(self) -> None:
        pr = _make_pr(number=42, repo="acme/web", title="Add login page", author="bob")
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "notify-send" in args
            assert "--app-name=forgewatch" in args
            assert "PR Review: acme/web" in args
            assert "#42 Add login page\nby bob" in args

    async def test_two_prs_send_two_notifications(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 3)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs)

            assert mock_exec.call_count == 2

    async def test_three_prs_send_three_notifications(self) -> None:
        """Boundary: exactly _INDIVIDUAL_THRESHOLD PRs -> individual."""
        prs = [_make_pr(number=i) for i in range(1, _INDIVIDUAL_THRESHOLD + 1)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs)

            assert mock_exec.call_count == _INDIVIDUAL_THRESHOLD

    async def test_individual_notification_contains_repo(self) -> None:
        pr = _make_pr(repo="org/backend")
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            assert "PR Review: org/backend" in args

    async def test_individual_notification_contains_author(self) -> None:
        pr = _make_pr(author="charlie")
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            body = [a for a in args if "by charlie" in a]
            assert len(body) == 1

    async def test_individual_notification_uses_avatar_icon(self) -> None:
        """When avatar download succeeds, icon should be the local path."""
        pr = _make_pr()
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value="/tmp/avatar.png"),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            assert "--icon=/tmp/avatar.png" in args

    async def test_individual_notification_falls_back_to_github_icon(self) -> None:
        """When avatar download fails, icon should be 'github'."""
        pr = _make_pr()
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            assert "--icon=github" in args


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — batch notifications (> 3 PRs)
# ---------------------------------------------------------------------------


class TestNotifyNewPrsBatch:
    """notify_new_prs sends a single summary for > 3 PRs."""

    async def test_four_prs_sends_single_batch(self) -> None:
        """Boundary: _INDIVIDUAL_THRESHOLD + 1 -> batch."""
        prs = [_make_pr(number=i) for i in range(1, _INDIVIDUAL_THRESHOLD + 2)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            mock_exec.assert_called_once()

    async def test_batch_summary_contains_count(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            args = mock_exec.call_args[0]
            assert "5 new PR review requests" in args

    async def test_batch_body_lists_prs(self) -> None:
        prs = [_make_pr(number=i, title=f"PR number {i}") for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            args = mock_exec.call_args[0]
            body = args[-1]  # last positional arg is the body
            for i in range(1, 6):
                assert f"owner/repo#{i}: PR number {i}" in body

    async def test_batch_body_truncates_to_limit(self) -> None:
        """Only the first _BATCH_BODY_LIMIT PRs appear in the body."""
        prs = [_make_pr(number=i, title=f"PR number {i}") for i in range(1, 9)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            args = mock_exec.call_args[0]
            body = args[-1]
            # First _BATCH_BODY_LIMIT PRs should be present
            for i in range(1, _BATCH_BODY_LIMIT + 1):
                assert f"PR number {i}" in body
            # PRs beyond the limit should NOT be present
            for i in range(_BATCH_BODY_LIMIT + 1, 9):
                assert f"PR number {i}" not in body

    async def test_batch_summary_count_reflects_total(self) -> None:
        """Summary shows total count, not truncated count."""
        prs = [_make_pr(number=i) for i in range(1, 9)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            args = mock_exec.call_args[0]
            assert "8 new PR review requests" in args


# ---------------------------------------------------------------------------
# Tests: _send_notification — command construction
# ---------------------------------------------------------------------------


class TestSendNotificationCommand:
    """_send_notification builds the correct notify-send command."""

    async def test_includes_app_name(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--app-name=forgewatch" in args

    async def test_includes_default_icon(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--icon=github" in args

    async def test_custom_icon_path(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", icon="/tmp/avatar.png")

            args = mock_exec.call_args[0]
            assert "--icon=/tmp/avatar.png" in args
            assert "--icon=github" not in args

    async def test_default_urgency_is_normal(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--urgency=normal" in args

    async def test_custom_urgency(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", urgency="critical")

            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_summary_and_body_passed_as_args(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("My Title", "My Body")

            args = mock_exec.call_args[0]
            assert "My Title" in args
            assert "My Body" in args

    async def test_url_adds_action_flag(self) -> None:
        """When url is provided, --action=open=Open should be in the command."""
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", url="https://github.com/owner/repo/pull/1")

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "--action=open=Open" in args

    async def test_no_url_omits_action_flag(self) -> None:
        """When no url is provided, --action should not be in the command."""
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert all("--action" not in a for a in args)

    async def test_url_uses_pipe_for_stdout(self) -> None:
        """When url is provided, stdout should be PIPE to read action response."""
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", url="https://github.com/owner/repo/pull/1")

            kwargs = mock_exec.call_args[1]
            assert kwargs["stdout"] == asyncio.subprocess.PIPE

    async def test_no_url_uses_devnull_for_stdout(self) -> None:
        """When no url is provided, stdout should be DEVNULL."""
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            kwargs = mock_exec.call_args[1]
            assert kwargs["stdout"] == asyncio.subprocess.DEVNULL

    async def test_stderr_captured(self) -> None:
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            kwargs = mock_exec.call_args[1]
            assert kwargs["stderr"] is not None


# ---------------------------------------------------------------------------
# Tests: _send_notification — error handling
# ---------------------------------------------------------------------------


class TestSendNotificationErrors:
    """_send_notification handles errors gracefully."""

    async def test_nonzero_exit_logs_warning(self) -> None:
        proc = _mock_process(returncode=1, stderr=b"something went wrong")

        with (
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("forgewatch.notifier.logger") as mock_logger,
        ):
            await _send_notification("title", "body")

            mock_logger.warning.assert_called_once()
            warning_args = mock_logger.warning.call_args[0]
            # Should mention the exit code and stderr content
            assert 1 in warning_args
            assert "something went wrong" in warning_args

    async def test_file_not_found_logs_warning(self) -> None:
        with (
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError,
            ),
            patch("forgewatch.notifier.logger") as mock_logger,
        ):
            await _send_notification("title", "body")

            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "notify-send not found" in warning_msg

    async def test_nonzero_exit_does_not_raise(self) -> None:
        """Failure in notify-send should not propagate."""
        proc = _mock_process(returncode=1, stderr=b"error")

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            # Should complete without raising
            await _send_notification("title", "body")

    async def test_file_not_found_does_not_raise(self) -> None:
        """Missing notify-send should not propagate."""
        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            # Should complete without raising
            await _send_notification("title", "body")


# ---------------------------------------------------------------------------
# Tests: _wait_and_open — clickable notification action
# ---------------------------------------------------------------------------


class TestWaitAndOpen:
    """_wait_and_open handles notification action responses."""

    async def test_opens_url_when_action_is_open(self) -> None:
        proc = _mock_process(stdout=b"open\n")

        with patch("forgewatch.notifier.open_url", new_callable=AsyncMock) as mock_open:
            await _wait_and_open(proc, "https://github.com/owner/repo/pull/1")
            mock_open.assert_awaited_once_with("https://github.com/owner/repo/pull/1")

    async def test_does_not_open_url_on_empty_action(self) -> None:
        """Notification expired without click — no URL should be opened."""
        proc = _mock_process(stdout=b"")

        with patch("forgewatch.notifier.open_url", new_callable=AsyncMock) as mock_open:
            await _wait_and_open(proc, "https://github.com/owner/repo/pull/1")
            mock_open.assert_not_awaited()

    async def test_does_not_open_url_on_nonzero_exit(self) -> None:
        proc = _mock_process(returncode=1, stderr=b"error", stdout=b"open\n")

        with patch("forgewatch.notifier.open_url", new_callable=AsyncMock) as mock_open:
            await _wait_and_open(proc, "https://github.com/owner/repo/pull/1")
            mock_open.assert_not_awaited()

    async def test_exception_does_not_propagate(self) -> None:
        """Errors in _wait_and_open should be caught, not propagated."""
        proc = AsyncMock()
        proc.communicate.side_effect = OSError("unexpected")

        # Should not raise
        await _wait_and_open(proc, "https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# Tests: _download_avatar
# ---------------------------------------------------------------------------


class TestDownloadAvatar:
    """_download_avatar fetches GitHub avatars to local files."""

    async def test_returns_none_for_empty_url(self) -> None:
        mock_session = MagicMock()
        result = await _download_avatar("", mock_session)
        assert result is None

    async def test_downloads_and_returns_path(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"\x89PNG fake image data")

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        # Clear module-level cache to force download
        from forgewatch.notifier import _avatar_cache

        _avatar_cache.clear()
        result = await _download_avatar("https://avatars.githubusercontent.com/u/99999", mock_session)

        assert result is not None
        assert result.endswith(".png")

    async def test_returns_none_on_http_error(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 404

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        from forgewatch.notifier import _avatar_cache

        _avatar_cache.clear()
        result = await _download_avatar("https://avatars.githubusercontent.com/u/missing", mock_session)

        assert result is None

    async def test_returns_none_on_network_error(self) -> None:
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("connection failed"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        from forgewatch.notifier import _avatar_cache

        _avatar_cache.clear()
        result = await _download_avatar("https://avatars.githubusercontent.com/u/error", mock_session)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: module constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module constants have expected values."""

    def test_individual_threshold(self) -> None:
        assert _INDIVIDUAL_THRESHOLD == 3

    def test_batch_body_limit(self) -> None:
        assert _BATCH_BODY_LIMIT == 5


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — custom threshold
# ---------------------------------------------------------------------------


class TestNotifyCustomThreshold:
    """notify_new_prs respects the threshold parameter."""

    async def test_threshold_1_sends_batch_for_2_prs(self) -> None:
        """With threshold=1, 2 PRs should trigger a batch notification."""
        prs = [_make_pr(number=1), _make_pr(number=2)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, threshold=1)

            # Batch = 1 call (not 2 individual)
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "2 new PR review requests" in args

    async def test_threshold_5_sends_individual_for_5_prs(self) -> None:
        """With threshold=5, 5 PRs should get individual notifications."""
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, threshold=5)

            assert mock_exec.call_count == 5


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — custom urgency
# ---------------------------------------------------------------------------


class TestNotifyCustomUrgency:
    """notify_new_prs passes urgency through to _send_notification."""

    async def test_individual_notification_uses_custom_urgency(self) -> None:
        pr = _make_pr(number=1)
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr], urgency="critical")

            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_batch_notification_uses_custom_urgency(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, urgency="low")

            args = mock_exec.call_args[0]
            assert "--urgency=low" in args

    async def test_default_urgency_is_normal(self) -> None:
        pr = _make_pr(number=1)
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            assert "--urgency=normal" in args


# ---------------------------------------------------------------------------
# Tests: _download_avatar — cache behaviour
# ---------------------------------------------------------------------------


class TestDownloadAvatarCacheHit:
    """_download_avatar should use the in-memory cache on second call."""

    async def test_cache_hit_skips_download(self, tmp_path: Path) -> None:
        """Calling _download_avatar twice for the same URL should only fetch once."""
        from forgewatch import notifier

        avatar_url = "https://avatars.githubusercontent.com/u/cache-test-1"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"\x89PNG fake data")

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        # Clear caches and redirect cache dir to tmp_path
        notifier._avatar_cache.clear()
        with patch.object(notifier, "_AVATAR_CACHE_DIR", tmp_path):
            result1 = await _download_avatar(avatar_url, mock_session)
            assert result1 is not None

            # Second call — should hit in-memory cache, no HTTP request
            result2 = await _download_avatar(avatar_url, mock_session)
            assert result2 == result1

            # get() was called only once (for the first download)
            assert mock_session.get.call_count == 1

    async def test_cache_stale_file_redownloads(self, tmp_path: Path) -> None:
        """If the cached file was deleted from disk, re-download it."""
        from forgewatch import notifier

        avatar_url = "https://avatars.githubusercontent.com/u/cache-stale-1"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"\x89PNG fake data")

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        notifier._avatar_cache.clear()
        with patch.object(notifier, "_AVATAR_CACHE_DIR", tmp_path):
            result1 = await _download_avatar(avatar_url, mock_session)
            assert result1 is not None

            # Delete the file from disk to simulate cache staleness
            Path(result1).unlink()  # noqa: ASYNC240

            # Second call — stale cache entry triggers re-download
            result2 = await _download_avatar(avatar_url, mock_session)
            assert result2 is not None
            assert mock_session.get.call_count == 2


class TestDownloadAvatarDiskCache:
    """_download_avatar should reuse files on disk from previous runs."""

    async def test_disk_cache_hit(self, tmp_path: Path) -> None:
        """File exists on disk (from a previous daemon run) — reuse without HTTP."""
        import hashlib

        from forgewatch import notifier

        avatar_url = "https://avatars.githubusercontent.com/u/disk-cache-1"
        url_hash = hashlib.md5(avatar_url.encode()).hexdigest()  # noqa: S324
        cached_file = tmp_path / f"{url_hash}.png"
        cached_file.write_bytes(b"\x89PNG old data")

        mock_session = MagicMock()

        notifier._avatar_cache.clear()
        with patch.object(notifier, "_AVATAR_CACHE_DIR", tmp_path):
            result = await _download_avatar(avatar_url, mock_session)

        assert result == str(cached_file)
        # No HTTP call should have been made
        mock_session.get.assert_not_called()

    async def test_write_failure_returns_none(self, tmp_path: Path) -> None:
        """If writing avatar bytes to disk fails, return None."""
        from forgewatch import notifier

        avatar_url = "https://avatars.githubusercontent.com/u/write-fail-1"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"\x89PNG fake data")

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        notifier._avatar_cache.clear()
        with (
            patch.object(notifier, "_AVATAR_CACHE_DIR", tmp_path),
            patch("pathlib.Path.write_bytes", side_effect=OSError("disk full")),
        ):
            result = await _download_avatar(avatar_url, mock_session)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: _send_notification — background task for URL
# ---------------------------------------------------------------------------


class TestSendNotificationBackgroundTask:
    """_send_notification with url should spawn _wait_and_open as a background task."""

    async def test_url_creates_background_task(self) -> None:
        proc = _mock_process(stdout=b"open\n")

        with (
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("forgewatch.notifier._wait_and_open", new_callable=AsyncMock) as mock_wait,
            patch("forgewatch.notifier.asyncio.create_task") as mock_create_task,
        ):
            await _send_notification("title", "body", url="https://example.com/pr/1")

            # _wait_and_open should have been called (via create_task)
            mock_wait.assert_called_once_with(proc, "https://example.com/pr/1")
            mock_create_task.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _wait_and_open — ValueError exception
# ---------------------------------------------------------------------------


class TestWaitAndOpenValueError:
    """_wait_and_open should catch ValueError without propagating."""

    async def test_value_error_does_not_propagate(self) -> None:
        proc = AsyncMock()
        proc.communicate.side_effect = ValueError("decode error")

        # Should not raise
        await _wait_and_open(proc, "https://github.com/owner/repo/pull/1")


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — repo grouping mode
# ---------------------------------------------------------------------------


class TestNotifyRepoGrouping:
    """notify_new_prs with grouping='repo' groups by repository."""

    async def test_repo_grouping_individual_single_repo(self) -> None:
        """Repo mode with PRs from one repo below threshold -> individual notifications."""
        prs = [_make_pr(number=i, repo="acme/web") for i in range(1, 3)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="repo")

            assert mock_exec.call_count == 2

    async def test_repo_grouping_individual_multi_repo(self) -> None:
        """Repo mode with PRs from multiple repos, all below threshold -> individual per repo."""
        prs = [
            _make_pr(number=1, repo="acme/web"),
            _make_pr(number=2, repo="acme/api"),
            _make_pr(number=3, repo="acme/web"),
        ]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="repo")

            # 1 PR in acme/api (individual) + 2 PRs in acme/web (individual) = 3 calls
            assert mock_exec.call_count == 3

    async def test_repo_grouping_summary_for_large_group(self) -> None:
        """Repo mode with many PRs from one repo -> repo-level summary."""
        prs = [_make_pr(number=i, repo="acme/web", title=f"PR {i}") for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, grouping="repo")

            # Should be a single summary notification
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "5 new PRs in acme/web" in args

    async def test_repo_grouping_mixed_threshold(self) -> None:
        """Repo mode: one repo below threshold (individual), another above (summary)."""
        prs = [
            _make_pr(number=1, repo="acme/api", title="API fix"),
            _make_pr(number=2, repo="acme/web", title="Web fix 1"),
            _make_pr(number=3, repo="acme/web", title="Web fix 2"),
            _make_pr(number=4, repo="acme/web", title="Web fix 3"),
            _make_pr(number=5, repo="acme/web", title="Web fix 4"),
        ]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="repo")

            # acme/api: 1 PR -> individual (1 call)
            # acme/web: 4 PRs -> summary (1 call)
            assert mock_exec.call_count == 2

            # Check the summary notification for acme/web
            all_args = [call[0] for call in mock_exec.call_args_list]
            summary_args = [a for a in all_args if any("4 new PRs in acme/web" in s for s in a)]
            assert len(summary_args) == 1

    async def test_repo_grouping_summary_body_contains_pr_info(self) -> None:
        """Repo summary body should list PR numbers and titles."""
        prs = [_make_pr(number=i, repo="acme/web", title=f"Fix {i}") for i in range(1, 5)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, grouping="repo")

            args = mock_exec.call_args[0]
            body = args[-1]
            assert "- #1: Fix 1" in body
            assert "- #2: Fix 2" in body


class TestNotifyFlatGrouping:
    """notify_new_prs with grouping='flat' preserves existing behaviour."""

    async def test_flat_mode_individual_notifications(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 3)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="flat")

            assert mock_exec.call_count == 2

    async def test_flat_mode_batch_notification(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, grouping="flat")

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "5 new PR review requests" in args

    async def test_default_grouping_is_flat(self) -> None:
        """Without specifying grouping, behaviour matches flat mode."""
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "5 new PR review requests" in args


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — per-repo overrides
# ---------------------------------------------------------------------------


class TestNotifyRepoOverrides:
    """Per-repo notification overrides (enabled, urgency, threshold)."""

    async def test_disabled_repo_skipped_flat_mode(self) -> None:
        """Disabled repo PRs should not produce notifications in flat mode."""
        from forgewatch.config import RepoNotificationConfig

        prs = [
            _make_pr(number=1, repo="acme/web"),
            _make_pr(number=2, repo="acme/api"),
        ]
        overrides = {
            "acme/web": RepoNotificationConfig(enabled=False),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="flat", repo_overrides=overrides)

            # Only acme/api PR should trigger a notification
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "acme/api" in " ".join(args)

    async def test_disabled_repo_skipped_repo_mode(self) -> None:
        """Disabled repo PRs should not produce notifications in repo mode."""
        from forgewatch.config import RepoNotificationConfig

        prs = [
            _make_pr(number=1, repo="acme/web"),
            _make_pr(number=2, repo="acme/api"),
        ]
        overrides = {
            "acme/web": RepoNotificationConfig(enabled=False),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, grouping="repo", repo_overrides=overrides)

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "acme/api" in " ".join(args)

    async def test_all_repos_disabled_sends_nothing(self) -> None:
        """If all repos are disabled, no notifications are sent."""
        from forgewatch.config import RepoNotificationConfig

        prs = [
            _make_pr(number=1, repo="acme/web"),
            _make_pr(number=2, repo="acme/api"),
        ]
        overrides = {
            "acme/web": RepoNotificationConfig(enabled=False),
            "acme/api": RepoNotificationConfig(enabled=False),
        }

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
        ) as mock_exec:
            await notify_new_prs(prs, grouping="flat", repo_overrides=overrides)
            mock_exec.assert_not_called()

    async def test_per_repo_urgency_in_flat_mode(self) -> None:
        """Per-repo urgency override should be used for individual notifications."""
        from forgewatch.config import RepoNotificationConfig

        pr = _make_pr(number=1, repo="acme/web")
        overrides = {
            "acme/web": RepoNotificationConfig(urgency="critical"),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr], grouping="flat", urgency="low", repo_overrides=overrides)

            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_per_repo_urgency_in_repo_mode(self) -> None:
        """Per-repo urgency override in repo grouping mode."""
        from forgewatch.config import RepoNotificationConfig

        pr = _make_pr(number=1, repo="acme/web")
        overrides = {
            "acme/web": RepoNotificationConfig(urgency="critical"),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr], grouping="repo", urgency="low", repo_overrides=overrides)

            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_per_repo_threshold_in_repo_mode(self) -> None:
        """Per-repo threshold override — repo with threshold=1 should summarise 2 PRs."""
        from forgewatch.config import RepoNotificationConfig

        prs = [
            _make_pr(number=1, repo="acme/web"),
            _make_pr(number=2, repo="acme/web"),
        ]
        overrides = {
            "acme/web": RepoNotificationConfig(threshold=1),
        }
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, grouping="repo", repo_overrides=overrides)

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "2 new PRs in acme/web" in args

    async def test_repos_without_overrides_use_global_defaults(self) -> None:
        """Repos not in overrides should use global urgency/threshold."""
        from forgewatch.config import RepoNotificationConfig

        pr = _make_pr(number=1, repo="acme/other")
        overrides = {
            "acme/web": RepoNotificationConfig(urgency="critical"),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr], grouping="repo", urgency="normal", repo_overrides=overrides)

            args = mock_exec.call_args[0]
            assert "--urgency=normal" in args

    async def test_none_overrides_behaves_like_no_overrides(self) -> None:
        """repo_overrides=None should behave identically to no overrides."""
        prs = [_make_pr(number=1)]
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs(prs, repo_overrides=None)

            mock_exec.assert_called_once()

    async def test_override_with_only_enabled_inherits_global_urgency(self) -> None:
        """Repo with only ``enabled=true`` should inherit global urgency, not the dataclass default."""
        from forgewatch.config import RepoNotificationConfig

        pr = _make_pr(number=1, repo="acme/web")
        overrides = {
            "acme/web": RepoNotificationConfig(enabled=True),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            await notify_new_prs([pr], urgency="critical", repo_overrides=overrides)

            args = mock_exec.call_args[0]
            # Should use global urgency="critical", NOT the dataclass default "normal"
            assert "--urgency=critical" in args

    async def test_override_with_only_enabled_inherits_global_threshold(self) -> None:
        """Repo with only ``enabled=true`` should inherit global threshold."""
        from forgewatch.config import RepoNotificationConfig

        prs = [_make_pr(number=i, repo="acme/web") for i in range(1, 3)]
        overrides = {
            "acme/web": RepoNotificationConfig(enabled=True),
        }
        proc = _mock_process()

        with (
            patch("forgewatch.notifier._download_avatar", return_value=None),
            patch(
                "forgewatch.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
        ):
            # threshold=5 (global) => 2 PRs should be individual, not batch
            await notify_new_prs(prs, grouping="repo", threshold=5, repo_overrides=overrides)

            assert mock_exec.call_count == 2


# ---------------------------------------------------------------------------
# Tests: flat-mode batch + per-repo urgency overrides
# ---------------------------------------------------------------------------


class TestFlatModeBatchUrgency:
    """Flat-mode batch notification should use the highest per-repo urgency."""

    async def test_flat_batch_uses_highest_per_repo_urgency(self) -> None:
        """Mixed repos in batch: highest per-repo urgency wins."""
        from forgewatch.config import RepoNotificationConfig

        prs = [_make_pr(number=i, repo="acme/web") for i in range(1, 3)] + [
            _make_pr(number=i, repo="acme/api") for i in range(3, 5)
        ]
        overrides = {
            "acme/web": RepoNotificationConfig(urgency="critical"),
            "acme/api": RepoNotificationConfig(urgency="low"),
        }
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, threshold=1, urgency="normal", repo_overrides=overrides)

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_flat_batch_with_no_overrides_uses_global(self) -> None:
        """Without per-repo overrides, batch should use global urgency."""
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, urgency="low")

            args = mock_exec.call_args[0]
            assert "--urgency=low" in args


# ---------------------------------------------------------------------------
# Tests: repo-mode batch truncation at _BATCH_BODY_LIMIT
# ---------------------------------------------------------------------------


class TestRepoModeBatchTruncation:
    """Repo-grouped summary body should truncate at _BATCH_BODY_LIMIT."""

    async def test_repo_batch_body_truncates_to_limit(self) -> None:
        """Only the first _BATCH_BODY_LIMIT PRs appear in repo-grouped summary body."""
        prs = [_make_pr(number=i, repo="acme/web", title=f"PR {i}") for i in range(1, 9)]
        proc = _mock_process()

        with patch(
            "forgewatch.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs, grouping="repo")

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            body = args[-1]
            # First _BATCH_BODY_LIMIT PRs should be present
            for i in range(1, _BATCH_BODY_LIMIT + 1):
                assert f"PR {i}" in body
            # PRs beyond the limit should NOT be present
            for i in range(_BATCH_BODY_LIMIT + 1, 9):
                assert f"PR {i}" not in body
