"""Tests for forgewatch.poller."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from forgewatch.poller import (
    _MAX_PAGES,
    AuthError,
    GitHubClient,
    _parse_pr,
)

SEARCH_URL = "https://api.github.com/search/issues"
SEARCH_URL_RE = re.compile(r"^https://api\.github\.com/search/issues\b")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_item(
    number: int = 1,
    title: str = "Fix bug",
    author: str = "alice",
    repo: str = "owner/repo",
    updated_at: str = "2025-06-15T10:00:00Z",
) -> dict[str, Any]:
    """Build a minimal GitHub search result item."""
    return {
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "url": f"https://api.github.com/repos/{repo}/pulls/{number}",
        "title": title,
        "number": number,
        "user": {"login": author, "avatar_url": f"https://avatars.githubusercontent.com/u/{number}"},
        "repository_url": f"https://api.github.com/repos/{repo}",
        "updated_at": updated_at,
    }


def _search_response(
    items: list[dict[str, Any]],
    total_count: int | None = None,
) -> dict[str, Any]:
    """Wrap items in a search API response envelope."""
    return {
        "total_count": total_count if total_count is not None else len(items),
        "incomplete_results": False,
        "items": items,
    }


# ---------------------------------------------------------------------------
# _parse_pr
# ---------------------------------------------------------------------------


class TestParsePr:
    def test_parses_basic_item(self) -> None:
        item = _make_search_item(
            number=42,
            title="Add feature",
            author="bob",
            repo="org/project",
        )
        pr = _parse_pr(item, review_requested=True, assigned=False)

        assert pr.url == "https://github.com/org/project/pull/42"
        assert pr.api_url == "https://api.github.com/repos/org/project/pulls/42"
        assert pr.title == "Add feature"
        assert pr.repo_full_name == "org/project"
        assert pr.author == "bob"
        assert pr.author_avatar_url == "https://avatars.githubusercontent.com/u/42"
        assert pr.number == 42
        assert pr.review_requested is True
        assert pr.assigned is False
        assert isinstance(pr.updated_at, datetime)

    def test_frozen_dataclass(self) -> None:
        item = _make_search_item()
        pr = _parse_pr(item, review_requested=False, assigned=True)
        with pytest.raises(AttributeError):
            pr.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GitHubClient — session lifecycle
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    async def test_start_creates_session(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()
        assert client._session is not None
        await client.close()

    async def test_close_clears_session(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()
        await client.close()
        assert client._session is None

    async def test_close_without_start_is_safe(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.close()  # should not raise


# ---------------------------------------------------------------------------
# GitHubClient — fetch_review_requested
# ---------------------------------------------------------------------------


class TestFetchReviewRequested:
    async def test_returns_prs(self) -> None:
        client = GitHubClient(token="tok", username="testuser")
        await client.start()

        items = [_make_search_item(number=1), _make_search_item(number=2)]

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, payload=_search_response(items))
            prs = await client.fetch_review_requested()

        assert len(prs) == 2
        assert all(pr.review_requested is True for pr in prs)
        assert all(pr.assigned is False for pr in prs)
        await client.close()

    async def test_query_includes_username(self) -> None:
        client = GitHubClient(token="tok", username="janedoe")
        await client.start()

        with aioresponses() as m:
            # Use a callback to capture the actual request URL and verify params
            captured_urls: list[str] = []

            def callback(url: Any, **kwargs: Any) -> CallbackResult:
                captured_urls.append(str(url))
                return CallbackResult(payload=_search_response([]))

            m.get(SEARCH_URL_RE, callback=callback)
            await client.fetch_review_requested()

            assert len(captured_urls) == 1
            # aiohttp/yarl may encode the colon — accept any encoding form
            assert "review-requested" in captured_urls[0]
            assert "janedoe" in captured_urls[0]

        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — fetch_assigned
# ---------------------------------------------------------------------------


class TestFetchAssigned:
    async def test_returns_assigned_prs(self) -> None:
        client = GitHubClient(token="tok", username="testuser")
        await client.start()

        items = [_make_search_item(number=10)]

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, payload=_search_response(items))
            prs = await client.fetch_assigned()

        assert len(prs) == 1
        assert prs[0].assigned is True
        assert prs[0].review_requested is False
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — fetch_all (deduplication)
# ---------------------------------------------------------------------------


class TestFetchAll:
    async def test_deduplicates_by_url(self) -> None:
        client = GitHubClient(token="tok", username="testuser")
        await client.start()

        # Same PR appears in both queries
        shared_item = _make_search_item(number=5, repo="owner/shared")
        review_only = _make_search_item(number=1, repo="owner/review")
        assigned_only = _make_search_item(number=2, repo="owner/assigned")

        with aioresponses() as m:
            # First call = review-requested, second = assigned
            m.get(
                SEARCH_URL_RE,
                payload=_search_response([shared_item, review_only]),
            )
            m.get(
                SEARCH_URL_RE,
                payload=_search_response([shared_item, assigned_only]),
            )
            prs = await client.fetch_all()

        assert len(prs) == 3
        urls = {pr.url for pr in prs}
        assert "https://github.com/owner/shared/pull/5" in urls
        assert "https://github.com/owner/review/pull/1" in urls
        assert "https://github.com/owner/assigned/pull/2" in urls

        # The shared PR should have both flags set
        shared = next(pr for pr in prs if pr.number == 5)
        assert shared.review_requested is True
        assert shared.assigned is True

        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — repo filtering
# ---------------------------------------------------------------------------


class TestRepoFiltering:
    async def test_appends_repo_qualifiers(self) -> None:
        client = GitHubClient(
            token="tok",
            username="user",
            repos=["org/repo1", "org/repo2"],
        )
        await client.start()

        captured_urls: list[str] = []

        def callback(url: Any, **kwargs: Any) -> CallbackResult:
            captured_urls.append(str(url))
            return CallbackResult(payload=_search_response([]))

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, callback=callback)
            await client.fetch_review_requested()

        assert len(captured_urls) == 1
        url = captured_urls[0]
        # URL-encoded or plain — either form is acceptable
        assert "repo" in url
        assert "repo1" in url
        assert "repo2" in url

        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    async def test_reads_rate_limit_headers(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        headers = {
            "X-RateLimit-Remaining": "15",
            "X-RateLimit-Reset": "1750000000",
        }

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, payload=_search_response([]), headers=headers)
            await client.fetch_review_requested()

        assert client.rate_limit_remaining == 15
        assert client.rate_limit_reset == datetime.fromtimestamp(
            1750000000,
            tz=UTC,
        )
        await client.close()

    async def test_waits_when_rate_limit_exhausted(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        # Simulate exhausted rate limit
        client._rate_limit_remaining = 1
        # Set reset to the past so wait is minimal
        client._rate_limit_reset = datetime.now(tz=UTC)

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, payload=_search_response([]))
            # Should not raise — just waits and proceeds
            prs = await client.fetch_review_requested()

        assert prs == []
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_401_raises_auth_error(self) -> None:
        client = GitHubClient(token="bad_token", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, status=401, body="Bad credentials")
            with pytest.raises(AuthError, match="401"):
                await client.fetch_review_requested()

        await client.close()

    async def test_5xx_retries_and_returns_empty_on_failure(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            # All 3 retries return 500
            m.get(SEARCH_URL_RE, status=500)
            m.get(SEARCH_URL_RE, status=500)
            m.get(SEARCH_URL_RE, status=500)
            prs = await client.fetch_review_requested()

        # Should not raise, but return empty (logged error)
        assert prs == []
        await client.close()

    async def test_403_with_retry_after(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            # First request: 403 rate limited with short Retry-After
            m.get(
                SEARCH_URL_RE,
                status=403,
                headers={"Retry-After": "0"},
            )
            # Second request after retry: success
            m.get(
                SEARCH_URL_RE,
                payload=_search_response([_make_search_item()]),
            )
            prs = await client.fetch_review_requested()

        assert len(prs) == 1
        await client.close()

    async def test_network_error_raises(self) -> None:
        """Network errors should propagate so callers can preserve state."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(
                SEARCH_URL_RE,
                exception=aiohttp.ClientError("connection failed"),
            )
            with pytest.raises(aiohttp.ClientError, match="connection failed"):
                await client.fetch_review_requested()

        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — pagination
# ---------------------------------------------------------------------------


class TestPagination:
    async def test_follows_link_next_header(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        page1_items = [_make_search_item(number=i) for i in range(1, 4)]
        page2_items = [_make_search_item(number=i) for i in range(4, 6)]
        page2_url = f"{SEARCH_URL}?q=test&page=2"

        with aioresponses() as m:
            m.get(
                SEARCH_URL_RE,
                payload=_search_response(page1_items, total_count=5),
                headers={"Link": f'<{page2_url}>; rel="next"'},
            )
            m.get(
                page2_url,
                payload=_search_response(page2_items, total_count=5),
            )
            prs = await client.fetch_review_requested()

        assert len(prs) == 5
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — _parse_next_link
# ---------------------------------------------------------------------------


class TestParseNextLink:
    def test_extracts_next_url(self) -> None:
        header = (
            '<https://api.github.com/search/issues?q=test&page=2>; rel="next", '
            '<https://api.github.com/search/issues?q=test&page=5>; rel="last"'
        )
        assert GitHubClient._parse_next_link(header) == ("https://api.github.com/search/issues?q=test&page=2")

    def test_returns_none_when_no_next(self) -> None:
        header = '<https://api.github.com/search/issues?q=test&page=1>; rel="prev"'
        assert GitHubClient._parse_next_link(header) is None

    def test_returns_none_for_empty_header(self) -> None:
        assert GitHubClient._parse_next_link("") is None


# ---------------------------------------------------------------------------
# GitHubClient — update_config
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    def test_updates_fields(self) -> None:
        client = GitHubClient(token="old", username="old_user", repos=["a/b"])
        client.update_config(token="new", username="new_user", repos=["c/d"])
        assert client._token == "new"
        assert client._username == "new_user"
        assert client._repos == ["c/d"]

    def test_updates_base_url_and_max_retries(self) -> None:
        client = GitHubClient(token="tok", username="user")
        client.update_config(
            token="tok",
            username="user",
            base_url="https://gh.corp.example.com/api/v3",
            max_retries=5,
        )
        assert client._base_url == "https://gh.corp.example.com/api/v3"
        assert client._max_retries == 5

    def test_base_url_trailing_slash_stripped(self) -> None:
        client = GitHubClient(token="tok", username="user")
        client.update_config(
            token="tok",
            username="user",
            base_url="https://gh.example.com/",
        )
        assert client._base_url == "https://gh.example.com"


# ---------------------------------------------------------------------------
# GitHubClient — custom base_url
# ---------------------------------------------------------------------------


class TestCustomBaseUrl:
    async def test_uses_custom_base_url(self) -> None:
        custom_url = "https://gh.corp.example.com/api/v3"
        custom_search_re = re.compile(r"^https://gh\.corp\.example\.com/api/v3/search/issues\b")
        client = GitHubClient(token="tok", username="user", base_url=custom_url)
        await client.start()

        captured_urls: list[str] = []

        def callback(url: Any, **kwargs: Any) -> CallbackResult:
            captured_urls.append(str(url))
            return CallbackResult(payload=_search_response([]))

        with aioresponses() as m:
            m.get(custom_search_re, callback=callback)
            await client.fetch_review_requested()

        assert len(captured_urls) == 1
        assert captured_urls[0].startswith(custom_url)
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — custom max_retries
# ---------------------------------------------------------------------------


class TestCustomMaxRetries:
    async def test_retries_configured_number_of_times(self) -> None:
        client = GitHubClient(token="tok", username="user", max_retries=2)
        await client.start()

        with aioresponses() as m:
            # Only 2 retries configured (not 3)
            m.get(SEARCH_URL_RE, status=500)
            m.get(SEARCH_URL_RE, status=500)
            prs = await client.fetch_review_requested()

        assert prs == []
        await client.close()

    async def test_zero_retries_raises_immediately(self) -> None:
        """max_retries=0 means no retries — raises RuntimeError."""
        client = GitHubClient(token="tok", username="user", max_retries=0)
        await client.start()

        with aioresponses(), pytest.raises(RuntimeError, match="No retries attempted"):
            # No requests should be made (range(0) is empty)
            await client.fetch_review_requested()

        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — 403 without Retry-After (non-rate-limit)
# ---------------------------------------------------------------------------


class TestForbiddenNonRateLimit:
    async def test_403_without_retry_after_returns_empty(self) -> None:
        """A 403 without Retry-After header should log error and return empty."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, status=403, body="Forbidden: abuse detection")
            prs = await client.fetch_review_requested()

        assert prs == []
        await client.close()

    async def test_403_without_retry_after_partial_results(self) -> None:
        """If a 403 hits on page 2, page 1 results are still returned."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        page1_items = [_make_search_item(number=1)]
        page2_url = f"{SEARCH_URL}?q=test&page=2"

        with aioresponses() as m:
            m.get(
                SEARCH_URL_RE,
                payload=_search_response(page1_items, total_count=2),
                headers={"Link": f'<{page2_url}>; rel="next"'},
            )
            m.get(
                page2_url,
                status=403,
                body="Forbidden: secondary rate limit",
            )
            prs = await client.fetch_review_requested()

        assert len(prs) == 1
        assert prs[0].number == 1
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — rate limit fallback (no reset header)
# ---------------------------------------------------------------------------


class TestRateLimitFallbackWait:
    async def test_waits_fallback_when_no_reset_header(self) -> None:
        """When rate limit is low but no reset time is known, sleep 60s fallback."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        # Set rate limit low, but no reset time
        client._rate_limit_remaining = 1
        client._rate_limit_reset = None

        with (
            aioresponses() as m,
            patch("forgewatch.poller.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            m.get(SEARCH_URL_RE, payload=_search_response([]))
            await client.fetch_review_requested()

        # Should have slept for the fallback duration (60s)
        mock_sleep.assert_any_call(60)
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — non-OK status (not 401, 403, or 5xx)
# ---------------------------------------------------------------------------


class TestNonOkStatus:
    async def test_422_returns_empty(self) -> None:
        """Unprocessable Entity (422) should log error and return empty."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, status=422, body="Validation Failed")
            prs = await client.fetch_review_requested()

        assert prs == []
        await client.close()

    async def test_429_returns_empty(self) -> None:
        """Too Many Requests (429) without special handling returns empty."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(SEARCH_URL_RE, status=429, body="Too Many Requests")
            prs = await client.fetch_review_requested()

        assert prs == []
        await client.close()


# ---------------------------------------------------------------------------
# GitHubClient — pagination cap warning
# ---------------------------------------------------------------------------


class TestPaginationCapWarning:
    async def test_warns_when_page_limit_reached_with_more_pages(self, caplog: pytest.LogCaptureFixture) -> None:
        """When all _MAX_PAGES pages are fetched and a next link still exists, a warning should be logged."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            # Set up _MAX_PAGES pages, each with a Link: next header
            for page_num in range(_MAX_PAGES):
                items = [_make_search_item(number=page_num * 100 + i) for i in range(1, 3)]
                next_url = f"{SEARCH_URL}?q=test&page={page_num + 2}"
                if page_num == 0:
                    m.get(
                        SEARCH_URL_RE,
                        payload=_search_response(items),
                        headers={"Link": f'<{next_url}>; rel="next"'},
                    )
                else:
                    prev_url = f"{SEARCH_URL}?q=test&page={page_num + 1}"
                    m.get(
                        prev_url,
                        payload=_search_response(items),
                        headers={"Link": f'<{next_url}>; rel="next"'},
                    )

            with caplog.at_level(logging.WARNING, logger="forgewatch.poller"):
                prs = await client.fetch_review_requested()

        # Should have fetched items from all pages
        assert len(prs) == _MAX_PAGES * 2

        # Warning should be logged
        assert any("page limit" in record.message.lower() for record in caplog.records)
        assert any(str(_MAX_PAGES) in record.message for record in caplog.records)

        await client.close()

    async def test_no_warning_when_all_pages_consumed(self, caplog: pytest.LogCaptureFixture) -> None:
        """When exactly _MAX_PAGES pages are fetched and the last has no next link, no warning."""
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            # Set up _MAX_PAGES pages; the last one has no Link: next header
            for page_num in range(_MAX_PAGES):
                items = [_make_search_item(number=page_num * 100 + 1)]
                is_last = page_num == _MAX_PAGES - 1

                if page_num == 0:
                    if is_last:
                        m.get(SEARCH_URL_RE, payload=_search_response(items))
                    else:
                        next_url = f"{SEARCH_URL}?q=test&page={page_num + 2}"
                        m.get(
                            SEARCH_URL_RE,
                            payload=_search_response(items),
                            headers={"Link": f'<{next_url}>; rel="next"'},
                        )
                else:
                    current_url = f"{SEARCH_URL}?q=test&page={page_num + 1}"
                    if is_last:
                        m.get(current_url, payload=_search_response(items))
                    else:
                        next_url = f"{SEARCH_URL}?q=test&page={page_num + 2}"
                        m.get(
                            current_url,
                            payload=_search_response(items),
                            headers={"Link": f'<{next_url}>; rel="next"'},
                        )

            with caplog.at_level(logging.WARNING, logger="forgewatch.poller"):
                prs = await client.fetch_review_requested()

        assert len(prs) == _MAX_PAGES

        # No pagination warning should be logged
        assert not any("page limit" in record.message.lower() for record in caplog.records)

        await client.close()
