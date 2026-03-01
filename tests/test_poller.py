"""Tests for github_monitor.poller."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from github_monitor.poller import (
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

    async def test_network_error_returns_empty(self) -> None:
        client = GitHubClient(token="tok", username="user")
        await client.start()

        with aioresponses() as m:
            m.get(
                SEARCH_URL_RE,
                exception=aiohttp.ClientError("connection failed"),
            )
            m.get(
                SEARCH_URL_RE,
                exception=aiohttp.ClientError("connection failed"),
            )
            m.get(
                SEARCH_URL_RE,
                exception=aiohttp.ClientError("connection failed"),
            )
            prs = await client.fetch_review_requested()

        assert prs == []
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
