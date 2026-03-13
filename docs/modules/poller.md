# `poller.py` -- API reference

Module: `forgewatch.poller`

Async HTTP client that queries the GitHub Search Issues API for pull requests
where the configured user is a requested reviewer or assignee.

## Constants

| Name | Type | Value | Description |
|---|---|---|---|
| `_MAX_PAGES` | `int` | `10` | Maximum pages to follow when paginating |
| `_RATE_LIMIT_WARN_THRESHOLD` | `int` | `5` | Log a warning when remaining requests fall to this level |
| `_RATE_LIMIT_WAIT_THRESHOLD` | `int` | `2` | Preemptively wait when remaining requests fall to this level |
| `_RATE_LIMIT_FALLBACK_WAIT` | `int` | `60` | Seconds to wait if rate limit is exhausted but no reset time is known |
| `_LINK_NEXT_RE` | `re.Pattern` | `<([^>]+)>;\s*rel="next"` | Regex to extract the `next` URL from a `Link` header |

## `AuthError`

```python
class AuthError(Exception): ...
```

Raised when the GitHub API returns a 401 Unauthorized response. This indicates
a bad or expired token, and retrying would be pointless.

## `PullRequest`

```python
@dataclass(frozen=True)
class PullRequest:
    url: str
    api_url: str
    title: str
    repo_full_name: str
    author: str
    author_avatar_url: str
    number: int
    updated_at: datetime
    review_requested: bool
    assigned: bool
```

An immutable dataclass representing a single GitHub pull request.

| Field | Type | Description |
|---|---|---|
| `url` | `str` | HTML URL (clickable link), e.g., `https://github.com/owner/repo/pull/42` |
| `api_url` | `str` | API URL, e.g., `https://api.github.com/repos/owner/repo/pulls/42` |
| `title` | `str` | PR title |
| `repo_full_name` | `str` | Repository in `owner/name` format, extracted from `repository_url` |
| `author` | `str` | GitHub login of the PR author |
| `author_avatar_url` | `str` | URL to the author's GitHub avatar image |
| `number` | `int` | PR number within the repository |
| `updated_at` | `datetime` | Last updated timestamp (timezone-aware UTC) |
| `review_requested` | `bool` | `True` if the user was requested as a reviewer |
| `assigned` | `bool` | `True` if the user is an assignee |

A PR can have both `review_requested=True` and `assigned=True` if it appears in
both search queries (see `fetch_all()` deduplication).

## `_parse_pr()` (internal)

```python
def _parse_pr(
    item: dict[str, Any],
    *,
    review_requested: bool,
    assigned: bool,
) -> PullRequest:
```

Converts a raw GitHub search result item (dict) into a `PullRequest` instance.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `item` | `dict[str, Any]` | A single item from the GitHub search API `items` array |
| `review_requested` | `bool` | Whether this PR came from the review-requested query |
| `assigned` | `bool` | Whether this PR came from the assignee query |

### Field mapping

| `PullRequest` field | Source in API item |
|---|---|
| `url` | `item["html_url"]` |
| `api_url` | `item["url"]` |
| `title` | `item["title"]` |
| `repo_full_name` | Last two segments of `item["repository_url"]` (e.g., `owner/repo`) |
| `author` | `item["user"]["login"]` |
| `author_avatar_url` | `item["user"]["avatar_url"]` (defaults to `""` if missing) |
| `number` | `item["number"]` |
| `updated_at` | `item["updated_at"]` parsed as ISO 8601 datetime |

## `GitHubClient`

```python
class GitHubClient:
```

The main API client. Manages an `aiohttp.ClientSession`, handles authentication,
pagination, rate limiting, and retries. The base URL and retry count are
configurable via the constructor for GitHub Enterprise Server support.

### Constructor

```python
def __init__(
    self,
    token: str,
    username: str,
    repos: list[str] | None = None,
    base_url: str = "https://api.github.com",
    max_retries: int = 3,
) -> None:
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `token` | `str` | (required) | GitHub PAT for authentication |
| `username` | `str` | (required) | GitHub username for search query filters |
| `repos` | `list[str] \| None` | `None` | Optional repo filter; `None` or empty = all repos |
| `base_url` | `str` | `"https://api.github.com"` | GitHub API base URL (trailing slashes are stripped) |
| `max_retries` | `int` | `3` | Max retry attempts for 5xx errors |

The constructor does **not** create the HTTP session -- call `start()` first.

### Lifecycle methods

#### `start()`

```python
async def start(self) -> None:
```

Creates the `aiohttp.ClientSession` with authentication headers:

- `Authorization: token {token}`
- `Accept: application/vnd.github+json`
- `X-GitHub-Api-Version: 2022-11-28`

Must be called before any `fetch_*` method.

#### `close()`

```python
async def close(self) -> None:
```

Closes the HTTP session and sets it to `None`. Safe to call even if `start()`
was never called.

#### `update_config()`

```python
def update_config(
    self,
    token: str,
    username: str,
    repos: list[str] | None = None,
    base_url: str = "https://api.github.com",
    max_retries: int = 3,
) -> None:
```

Updates the client's token, username, repo filter, base URL, and max retries.
Intended for use when the daemon reloads configuration (SIGHUP). Note that
the session's authentication headers are **not** updated -- the session must
be recreated for header changes to take effect.

### Fetch methods

#### `fetch_review_requested()`

```python
async def fetch_review_requested(self) -> list[PullRequest]:
```

Fetches open PRs where the user is a requested reviewer.

**Search query:** `type:pr state:open review-requested:{username}` (plus
optional `repo:` qualifiers).

All returned `PullRequest` instances have `review_requested=True`,
`assigned=False`.

#### `fetch_assigned()`

```python
async def fetch_assigned(self) -> list[PullRequest]:
```

Fetches open PRs where the user is an assignee.

**Search query:** `type:pr state:open assignee:{username}` (plus optional
`repo:` qualifiers).

All returned `PullRequest` instances have `review_requested=False`,
`assigned=True`.

#### `fetch_all()`

```python
async def fetch_all(self) -> list[PullRequest]:
```

Runs both `fetch_review_requested()` and `fetch_assigned()` concurrently via
`asyncio.gather()`, then deduplicates the results.

**Deduplication:** PRs are keyed by their `url` field. If the same PR appears
in both queries, the flags are merged so that both `review_requested=True` and
`assigned=True`. This is done by creating a new `PullRequest` with merged flags.

**Returns:** A flat list of unique `PullRequest` instances.

### Properties

#### `rate_limit_remaining`

```python
@property
def rate_limit_remaining(self) -> int:
```

The number of remaining API requests, as reported by the last response's
`X-RateLimit-Remaining` header. Initialized to 30 (GitHub search API default).

#### `rate_limit_reset`

```python
@property
def rate_limit_reset(self) -> datetime | None:
```

The UTC timestamp when the rate limit resets, as reported by the last response's
`X-RateLimit-Reset` header. `None` if no response has been received yet.

### Internal methods

These are implementation details but documented here for completeness.

#### `_append_repo_filter()`

```python
def _append_repo_filter(self, query: str) -> str:
```

If `repos` is configured, appends `repo:owner/name` for each repository to the
search query string. If no repos are configured, returns the query unchanged.

#### `_search_issues()`

```python
async def _search_issues(self, query: str) -> list[dict[str, Any]]:
```

Core search method. Executes a paginated search against `GET /search/issues`
using the configured `_base_url`:

1. Waits for rate limit if necessary (`_wait_for_rate_limit()`)
2. Makes the request via `_request_with_retry()`. If the request raises a
   non-`AuthError` exception (e.g. network error after retries exhausted),
   the exception is logged and re-raised to the caller
3. Updates rate limit state from response headers
4. Handles status codes:
   - **200:** Extracts items, checks for `Link: rel="next"` header
   - **401:** Raises `AuthError`
   - **403:** Reads `Retry-After` header, sleeps, retries once
   - **Other:** Logs error, returns items collected so far
5. Follows pagination up to `_MAX_PAGES` pages
6. If all `_MAX_PAGES` pages were fetched and a `Link: rel="next"` header
   is still present, logs a warning suggesting the user narrow their repo
   filter

#### `_request_with_retry()`

```python
async def _request_with_retry(
    self,
    url: str,
    params: dict[str, str] | None = None,
) -> aiohttp.ClientResponse:
```

Makes an HTTP GET request with retry logic. Uses `self._max_retries`
(configurable via the constructor) to determine the number of retry attempts:

- On **5xx** responses: retries up to `_max_retries` times with exponential
  backoff (`2^attempt` seconds)
- On success or non-5xx error: returns the response immediately
- If all retries are exhausted: returns the last response (caller handles the
  status code)

#### `_update_rate_limit()`

```python
def _update_rate_limit(self, resp: aiohttp.ClientResponse) -> None:
```

Reads `X-RateLimit-Remaining` and `X-RateLimit-Reset` from the response headers
and updates internal state. Logs a warning if remaining drops to
`_RATE_LIMIT_WARN_THRESHOLD` (5) or below.

#### `_wait_for_rate_limit()`

```python
async def _wait_for_rate_limit(self) -> None:
```

Called before each search request. If `rate_limit_remaining` is at or below
`_RATE_LIMIT_WAIT_THRESHOLD` (2), sleeps until the rate limit resets:

- If a reset time is known: sleeps until `reset_time + 1 second` buffer
- If no reset time is known: sleeps for `_RATE_LIMIT_FALLBACK_WAIT` (60s)

#### `_parse_next_link()` (static)

```python
@staticmethod
def _parse_next_link(link_header: str) -> str | None:
```

Parses the `Link` HTTP header to extract the URL with `rel="next"`. Returns
`None` if no next link is found or the header is empty.

**Example input:**

```
<https://api.github.com/search/issues?q=test&page=2>; rel="next",
<https://api.github.com/search/issues?q=test&page=5>; rel="last"
```

**Returns:** `"https://api.github.com/search/issues?q=test&page=2"`

## Error handling summary

| Scenario | Behavior |
|---|---|
| HTTP 200 | Parse items, continue pagination |
| HTTP 401 | Raise `AuthError` immediately |
| HTTP 403 + `Retry-After` | Sleep for the specified duration, retry once |
| HTTP 5xx | Retry up to `_max_retries` times with exponential backoff (2^n seconds) |
| Network error | Retry up to `_max_retries` times with exponential backoff, then raise |
| Rate limit near exhaustion | Preemptively wait until reset before making request |
| All retries exhausted (5xx) | Return last response (caller handles the status code) |
| All retries exhausted (network) | Raise exception (daemon catches, preserves store state) |
| Pagination cap reached | Log warning suggesting user narrow repo filter; return items collected so far |

## Usage example

```python
import asyncio
from forgewatch.poller import GitHubClient

async def main() -> None:
    client = GitHubClient(
        token="ghp_your_token",
        username="janedoe",
        repos=["myorg/frontend", "myorg/backend"],
        base_url="https://api.github.com",  # or GHE URL
        max_retries=3,
    )
    await client.start()

    try:
        prs = await client.fetch_all()
        for pr in prs:
            flags = []
            if pr.review_requested:
                flags.append("review")
            if pr.assigned:
                flags.append("assigned")
            print(f"  [{', '.join(flags)}] {pr.repo_full_name}#{pr.number}: {pr.title}")

        print(f"\nRate limit remaining: {client.rate_limit_remaining}")
    finally:
        await client.close()

asyncio.run(main())
```

## Tests

Tests in `tests/test_poller.py` organized into test classes:

| Class | Coverage |
|---|---|
| `TestParsePr` | Field parsing, frozen dataclass, avatar URL |
| `TestClientLifecycle` | Session creation, close, close-without-start |
| `TestFetchReviewRequested` | Returns PRs with correct flags, query includes username |
| `TestFetchAssigned` | Returns PRs with correct flags |
| `TestFetchAll` | Deduplication, flag merging |
| `TestRepoFiltering` | Repo qualifiers in query URL |
| `TestRateLimiting` | Header parsing, preemptive waiting |
| `TestErrorHandling` | 401, 5xx retries, 403 Retry-After, network errors |
| `TestPagination` | Link header following |
| `TestParseNextLink` | Next URL extraction, no-next, empty header |
| `TestUpdateConfig` | Field updates including base_url and max_retries |
| `TestCustomBaseUrl` | Custom base URL used in HTTP requests |
| `TestConfigurableRetries` | Configurable retry count, zero retries |
| `TestPaginationCapWarning` | Warning when page limit reached with more pages, no warning when all consumed |
