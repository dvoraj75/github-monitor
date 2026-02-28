"""Tests for github_monitor.notifier."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from github_monitor.notifier import (
    _BATCH_BODY_LIMIT,
    _INDIVIDUAL_THRESHOLD,
    _send_notification,
    notify_new_prs,
)
from github_monitor.poller import PullRequest

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
) -> PullRequest:
    """Build a PullRequest for testing."""
    return PullRequest(
        url=f"https://github.com/{repo}/pull/{number}",
        api_url=f"https://api.github.com/repos/{repo}/pulls/{number}",
        title=title,
        repo_full_name=repo,
        author=author,
        number=number,
        updated_at=_NOW,
        review_requested=True,
        assigned=False,
    )


def _mock_process(returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    """Build a mock process that has communicate() and returncode."""
    proc = AsyncMock()
    proc.communicate.return_value = (b"", stderr)
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# Tests: notify_new_prs — empty list
# ---------------------------------------------------------------------------


class TestNotifyNewPrsEmpty:
    """notify_new_prs should be a no-op for an empty list."""

    async def test_empty_list_does_nothing(self) -> None:
        with patch("github_monitor.notifier.asyncio.create_subprocess_exec") as mock_exec:
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

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs([pr])

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "notify-send" in args
            assert "--app-name=github-monitor" in args
            assert "PR Review: acme/web" in args
            assert "#42 Add login page\nby bob" in args

    async def test_two_prs_send_two_notifications(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 3)]
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            assert mock_exec.call_count == 2

    async def test_three_prs_send_three_notifications(self) -> None:
        """Boundary: exactly _INDIVIDUAL_THRESHOLD PRs -> individual."""
        prs = [_make_pr(number=i) for i in range(1, _INDIVIDUAL_THRESHOLD + 1)]
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            assert mock_exec.call_count == _INDIVIDUAL_THRESHOLD

    async def test_individual_notification_contains_repo(self) -> None:
        pr = _make_pr(repo="org/backend")
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            assert "PR Review: org/backend" in args

    async def test_individual_notification_contains_author(self) -> None:
        pr = _make_pr(author="charlie")
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs([pr])

            args = mock_exec.call_args[0]
            body = [a for a in args if "by charlie" in a]
            assert len(body) == 1


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
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            mock_exec.assert_called_once()

    async def test_batch_summary_contains_count(self) -> None:
        prs = [_make_pr(number=i) for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await notify_new_prs(prs)

            args = mock_exec.call_args[0]
            assert "5 new PR review requests" in args

    async def test_batch_body_lists_prs(self) -> None:
        prs = [_make_pr(number=i, title=f"PR number {i}") for i in range(1, 6)]
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
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
            "github_monitor.notifier.asyncio.create_subprocess_exec",
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
            "github_monitor.notifier.asyncio.create_subprocess_exec",
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
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--app-name=github-monitor" in args

    async def test_includes_icon(self) -> None:
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--icon=github" in args

    async def test_default_urgency_is_normal(self) -> None:
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body")

            args = mock_exec.call_args[0]
            assert "--urgency=normal" in args

    async def test_custom_urgency(self) -> None:
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", urgency="critical")

            args = mock_exec.call_args[0]
            assert "--urgency=critical" in args

    async def test_summary_and_body_passed_as_args(self) -> None:
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("My Title", "My Body")

            args = mock_exec.call_args[0]
            assert "My Title" in args
            assert "My Body" in args

    async def test_url_param_accepted(self) -> None:
        """url is accepted without error (reserved for future use)."""
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ) as mock_exec:
            await _send_notification("title", "body", url="https://github.com/owner/repo/pull/1")

            mock_exec.assert_called_once()

    async def test_stderr_captured(self) -> None:
        proc = _mock_process()

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
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
                "github_monitor.notifier.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("github_monitor.notifier.logger") as mock_logger,
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
                "github_monitor.notifier.asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError,
            ),
            patch("github_monitor.notifier.logger") as mock_logger,
        ):
            await _send_notification("title", "body")

            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "notify-send not found" in warning_msg

    async def test_nonzero_exit_does_not_raise(self) -> None:
        """Failure in notify-send should not propagate."""
        proc = _mock_process(returncode=1, stderr=b"error")

        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            return_value=proc,
        ):
            # Should complete without raising
            await _send_notification("title", "body")

    async def test_file_not_found_does_not_raise(self) -> None:
        """Missing notify-send should not propagate."""
        with patch(
            "github_monitor.notifier.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            # Should complete without raising
            await _send_notification("title", "body")


# ---------------------------------------------------------------------------
# Tests: module constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module constants have expected values."""

    def test_individual_threshold(self) -> None:
        assert _INDIVIDUAL_THRESHOLD == 3

    def test_batch_body_limit(self) -> None:
        assert _BATCH_BODY_LIMIT == 5
