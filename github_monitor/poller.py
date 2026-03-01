"""GitHub API client for fetching pull requests."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Max pages to follow when paginating search results
_MAX_PAGES = 10

# Rate limit thresholds
_RATE_LIMIT_WARN_THRESHOLD = 5
_RATE_LIMIT_WAIT_THRESHOLD = 2
_RATE_LIMIT_FALLBACK_WAIT = 60

# Regex to extract next URL from Link header
_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class AuthError(Exception):
    """Raised when GitHub returns 401 — invalid credentials."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PullRequest:
    """Represents a single pull request requiring attention."""

    url: str  # html_url — clickable link
    api_url: str  # API url for future use
    title: str
    repo_full_name: str  # e.g. "owner/repo"
    author: str  # login of PR author
    author_avatar_url: str  # URL to author's GitHub avatar
    number: int
    updated_at: datetime
    review_requested: bool  # True if review requested from user
    assigned: bool  # True if user is assignee


def _parse_pr(
    item: dict[str, Any],
    *,
    review_requested: bool,
    assigned: bool,
) -> PullRequest:
    """Convert a GitHub search result item to a PullRequest."""
    # The search/issues endpoint returns html_url and url (API URL).
    # repo info is embedded in repository_url:
    #   https://api.github.com/repos/owner/name
    repo_url: str = item.get("repository_url", "")
    # Extract "owner/name" from the API URL
    repo_full_name = "/".join(repo_url.rsplit("/", 2)[-2:]) if repo_url else ""

    return PullRequest(
        url=item["html_url"],
        api_url=item["url"],
        title=item["title"],
        repo_full_name=repo_full_name,
        author=item["user"]["login"],
        author_avatar_url=item["user"].get("avatar_url", ""),
        number=item["number"],
        updated_at=datetime.fromisoformat(item["updated_at"]),
        review_requested=review_requested,
        assigned=assigned,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GitHubClient:
    """Async GitHub API client for fetching PRs."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        username: str,
        repos: list[str] | None = None,
    ) -> None:
        self._token = token
        self._username = username
        self._repos = repos or []
        self._session: aiohttp.ClientSession | None = None
        self._rate_limit_remaining: int = 30
        self._rate_limit_reset: datetime | None = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create aiohttp session with auth headers."""
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def update_config(
        self,
        token: str,
        username: str,
        repos: list[str] | None = None,
    ) -> None:
        """Update client configuration (called on SIGHUP config reload)."""
        self._token = token
        self._username = username
        self._repos = repos or []
        # Session headers will be stale — recreate on next start()

    # -- public fetch methods ------------------------------------------------

    async def fetch_review_requested(self) -> list[PullRequest]:
        """Fetch open PRs where review is requested from user."""
        query = f"type:pr state:open review-requested:{self._username}"
        query = self._append_repo_filter(query)
        items = await self._search_issues(query)
        return [_parse_pr(item, review_requested=True, assigned=False) for item in items]

    async def fetch_assigned(self) -> list[PullRequest]:
        """Fetch open PRs where user is assignee."""
        query = f"type:pr state:open assignee:{self._username}"
        query = self._append_repo_filter(query)
        items = await self._search_issues(query)
        return [_parse_pr(item, review_requested=False, assigned=True) for item in items]

    async def fetch_all(self) -> list[PullRequest]:
        """Fetch both review-requested and assigned PRs, deduplicated by URL."""
        review_prs, assigned_prs = await asyncio.gather(
            self.fetch_review_requested(),
            self.fetch_assigned(),
        )

        # Deduplicate: if a PR appears in both, merge the flags
        seen: dict[str, PullRequest] = {}
        for pr in review_prs:
            seen[pr.url] = pr

        for pr in assigned_prs:
            if pr.url in seen:
                # PR is both review-requested and assigned — merge flags
                existing = seen[pr.url]
                seen[pr.url] = PullRequest(
                    url=existing.url,
                    api_url=existing.api_url,
                    title=existing.title,
                    repo_full_name=existing.repo_full_name,
                    author=existing.author,
                    author_avatar_url=existing.author_avatar_url,
                    number=existing.number,
                    updated_at=existing.updated_at,
                    review_requested=True,
                    assigned=True,
                )
            else:
                seen[pr.url] = pr

        return list(seen.values())

    @property
    def rate_limit_remaining(self) -> int:
        """Current rate limit remaining (from last response)."""
        return self._rate_limit_remaining

    @property
    def rate_limit_reset(self) -> datetime | None:
        """When the rate limit resets (from last response)."""
        return self._rate_limit_reset

    # -- internal ------------------------------------------------------------

    def _append_repo_filter(self, query: str) -> str:
        """Append repo:owner/name qualifiers if repos are configured."""
        if not self._repos:
            return query
        repo_parts = " ".join(f"repo:{r}" for r in self._repos)
        return f"{query} {repo_parts}"

    async def _search_issues(self, query: str) -> list[dict[str, Any]]:
        """Execute a search/issues API call with pagination and rate limiting."""
        if self._session is None:
            msg = "Call start() before fetching"
            raise RuntimeError(msg)

        all_items: list[dict[str, Any]] = []
        url: str | None = f"{self.BASE_URL}/search/issues"
        params: dict[str, str] | None = {
            "q": query,
            "per_page": "100",
            "sort": "updated",
            "order": "desc",
        }
        page = 0

        while url and page < _MAX_PAGES:
            await self._wait_for_rate_limit()

            try:
                resp = await self._request_with_retry(url, params=params)
            except AuthError:
                raise
            except Exception:
                logger.exception("Error fetching %s", url)
                break

            self._update_rate_limit(resp)

            if resp.status == HTTPStatus.UNAUTHORIZED:
                body = await resp.text()
                msg = f"GitHub auth failed (401): {body}"
                raise AuthError(msg)

            if resp.status == HTTPStatus.FORBIDDEN:
                # Rate limited by GitHub
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    wait = int(retry_after)
                    logger.warning("Rate limited, waiting %d seconds", wait)
                    await asyncio.sleep(wait)
                    continue  # retry same page
                body = await resp.text()
                logger.error("GitHub 403 (not rate-limit): %s", body)
                break

            if resp.status != HTTPStatus.OK:
                body = await resp.text()
                logger.error("GitHub API error %d: %s", resp.status, body[:200])
                break

            data = await resp.json()
            items: list[dict[str, Any]] = data.get("items", [])
            all_items.extend(items)

            # Check for next page via Link header
            url = self._parse_next_link(resp.headers.get("Link", ""))
            params = None  # URL from Link header includes params
            page += 1

        return all_items

    async def _request_with_retry(
        self,
        url: str,
        params: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> aiohttp.ClientResponse:
        """Make a GET request with exponential backoff on 5xx errors."""
        if self._session is None:
            msg = "Call start() before fetching"
            raise RuntimeError(msg)

        last_resp: aiohttp.ClientResponse | None = None

        for attempt in range(max_retries):
            resp = await self._session.get(url, params=params)

            if resp.status < HTTPStatus.INTERNAL_SERVER_ERROR:
                return resp

            # 5xx — retry with backoff
            last_resp = resp
            wait = 2**attempt
            logger.warning(
                "GitHub returned %d, retrying in %ds (attempt %d/%d)",
                resp.status,
                wait,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(wait)

        # Exhausted retries — return last response for caller to handle
        if last_resp is None:
            msg = "No retries attempted"
            raise RuntimeError(msg)
        return last_resp

    def _update_rate_limit(self, resp: aiohttp.ClientResponse) -> None:
        """Read rate limit headers from response."""
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            self._rate_limit_remaining = int(remaining)

        reset = resp.headers.get("X-RateLimit-Reset")
        if reset is not None:
            self._rate_limit_reset = datetime.fromtimestamp(int(reset), tz=UTC)

        if self._rate_limit_remaining <= _RATE_LIMIT_WARN_THRESHOLD:
            logger.warning(
                "GitHub rate limit low: %d remaining, resets at %s",
                self._rate_limit_remaining,
                self._rate_limit_reset,
            )

    async def _wait_for_rate_limit(self) -> None:
        """Sleep if we're close to hitting the rate limit."""
        if self._rate_limit_remaining > _RATE_LIMIT_WAIT_THRESHOLD:
            return

        if self._rate_limit_reset is None:
            # No reset info — wait a conservative amount
            logger.warning(
                "Rate limit near zero, waiting %ds (no reset time)",
                _RATE_LIMIT_FALLBACK_WAIT,
            )
            await asyncio.sleep(_RATE_LIMIT_FALLBACK_WAIT)
            return

        now = datetime.now(tz=UTC)
        wait_seconds = (self._rate_limit_reset - now).total_seconds()
        if wait_seconds > 0:
            logger.warning(
                "Rate limit exhausted, waiting %.1fs until reset",
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds + 1)  # +1s buffer

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        """Extract the 'next' URL from a GitHub Link header."""
        if not link_header:
            return None
        match = _LINK_NEXT_RE.search(link_header)
        return match.group(1) if match else None
