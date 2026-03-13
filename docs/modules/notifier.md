# `notifier.py` -- API reference

Module: `forgewatch.notifier`

Sends desktop notifications via `notify-send` when new pull requests are
detected. Small batches get individual notifications with author avatars and
clickable links; larger batches get a single summary to avoid desktop spam.

## Constants

| Constant | Value | Description |
|---|---|---|
| `_INDIVIDUAL_THRESHOLD` | `3` | Default maximum PRs that trigger individual notifications |
| `_BATCH_BODY_LIMIT` | `5` | Maximum PRs listed in a batch notification body |
| `_AVATAR_SIZE` | `64` | Avatar image size in pixels (appended as `?s=N` to URL) |
| `_AVATAR_CACHE_DIR` | `~/.cache/forgewatch/avatars` | Directory for cached avatar files |

Module-level state:

| Name | Type | Description |
|---|---|---|
| `_avatar_cache` | `dict[str, Path]` | In-memory cache mapping avatar URLs to local file paths |
| `_background_tasks` | `set[asyncio.Task]` | Tracks background tasks (notification click handlers) to prevent GC |
| `_DEFAULT_REPO_OVERRIDE` | `RepoNotificationConfig` | Default repo override instance (all defaults) used when a repo has no explicit config |

## Functions

### `notify_new_prs()`

```python
async def notify_new_prs(
    new_prs: list[PullRequest],
    *,
    threshold: int = _INDIVIDUAL_THRESHOLD,
    urgency: str = "normal",
    grouping: str = "flat",
    repo_overrides: dict[str, RepoNotificationConfig] | None = None,
) -> None:
```

Send desktop notifications for newly discovered PRs. This is the main public
entry point -- call it after each poll cycle with the `StateDiff.new_prs` list.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `new_prs` | `list[PullRequest]` | (required) | PRs not seen in the previous poll cycle |
| `threshold` | `int` | `3` | Max PRs for individual notifications; above this, a summary is sent |
| `urgency` | `str` | `"normal"` | Notification urgency level: `low`, `normal`, or `critical` |
| `grouping` | `str` | `"flat"` | Grouping mode: `"flat"` (single list) or `"repo"` (grouped by repository) |
| `repo_overrides` | `dict[str, RepoNotificationConfig] \| None` | `None` | Per-repo settings: disable notifications, override urgency or threshold |

**Behaviour:**

- If `new_prs` is empty, returns immediately (no subprocess calls).
- PRs from repos with `enabled = false` in `repo_overrides` are filtered out
  before any notifications are sent.
- **Flat mode** (`grouping="flat"`, the default):
  - If 1-`threshold` new PRs: opens a shared `aiohttp.ClientSession` and sends
    one notification per PR with per-repo urgency override (if configured):
    - Summary: `"PR Review: {repo_full_name}"`
    - Body: `"#{number} {title}\nby {author}"`
    - Icon: author's avatar (downloaded and cached locally)
    - Action: clickable "Open" button that opens the PR in the default browser
  - If > `threshold` new PRs: sends a single batch notification with:
    - Summary: `"{count} new PR review requests"`
    - Body: first 5 PRs as `"- {repo}#{number}: {title}"`, one per line
- **Repo mode** (`grouping="repo"`):
  - PRs are sorted and grouped by `repo_full_name`.
  - Each repo group is handled independently using that repo's threshold
    (from `repo_overrides`, falling back to the global `threshold`).
  - Groups at or below the repo threshold get individual notifications.
  - Groups above the repo threshold get a single repo-level summary:
    - Summary: `"{count} new PRs in {repo_name}"`
    - Body: first 5 PRs as `"- #{number}: {title}"`, one per line

### `_send_notification()`

```python
async def _send_notification(
    summary: str,
    body: str,
    *,
    url: str | None = None,
    icon: str | None = None,
    urgency: str = "normal",
) -> None:
```

Low-level function that calls `notify-send` as an async subprocess.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `summary` | `str` | *(required)* | Notification title |
| `body` | `str` | *(required)* | Notification body text |
| `url` | `str \| None` | `None` | If provided, adds an "Open" action button to the notification |
| `icon` | `str \| None` | `None` | Path to icon file; falls back to the generic `github` icon name |
| `urgency` | `str` | `"normal"` | Urgency level: `low`, `normal`, or `critical` |

**Command constructed:**

```
notify-send --app-name=forgewatch --urgency={urgency} --icon={icon_or_github} [--action=open=Open] {summary} {body}
```

When `url` is provided, `--action=open=Open` is appended and the process stdout
is monitored in a background task. If the user clicks "Open", the URL is opened
via the XDG Desktop Portal (D-Bus), falling back to `xdg-open` if the portal
is unavailable.

When `url` is not provided, the process runs normally and stdout is discarded.

**Error handling:**

- Non-zero exit code: logs a warning with the exit code and stderr output.
  Does **not** raise an exception.
- `notify-send` not found (`FileNotFoundError`): logs a warning suggesting
  `libnotify-bin` installation. Does **not** raise an exception.

Notifications are fire-and-forget -- failures never interrupt the poll loop.

### `_download_avatar()`

```python
async def _download_avatar(avatar_url: str, session: aiohttp.ClientSession) -> str | None:
```

Downloads a GitHub avatar to a local temp file. Returns the local file path
as a string, or `None` on failure.

Uses a two-level cache:
1. **In-memory** (`_avatar_cache`): instant lookup for avatars already downloaded
   this session
2. **On-disk** (`_AVATAR_CACHE_DIR`): persists across restarts via deterministic
   filenames (MD5 hash of the URL)

The caller provides a shared `aiohttp.ClientSession` so that avatar downloads
within a notification batch reuse the same HTTP connection.

### `_fetch_avatar_bytes()`

```python
async def _fetch_avatar_bytes(avatar_url: str, session: aiohttp.ClientSession) -> bytes | None:
```

Fetches raw avatar image bytes from GitHub. Appends `?s={_AVATAR_SIZE}` to
request a small image. Returns `None` on any HTTP or network error.

### `_wait_and_open()`

```python
async def _wait_and_open(proc: asyncio.subprocess.Process, url: str) -> None:
```

Background task that waits for a `notify-send` process (started with
`--action=open=Open`) to complete. If the user clicked the "Open" action,
`notify-send` prints `"open"` to stdout, and this function opens the URL
in the default browser via `url_opener.open_url()` (which tries the XDG
Desktop Portal first, then falls back to `xdg-open`).

See [url_opener.md](url_opener.md) for details on the URL opening mechanism.

### `_notify_flat()` (internal)

```python
async def _notify_flat(
    new_prs: list[PullRequest],
    *,
    threshold: int,
    urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> None:
```

Sends notifications in flat mode (original behaviour). Filters disabled repos,
then applies the global threshold to decide between individual and summary
notifications. Per-repo urgency overrides are applied to individual notifications.

### `_notify_grouped_by_repo()` (internal)

```python
async def _notify_grouped_by_repo(
    new_prs: list[PullRequest],
    *,
    threshold: int,
    urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> None:
```

Sends notifications grouped by repository. Filters disabled repos, sorts PRs by
`repo_full_name`, and processes each repo group independently using per-repo
threshold and urgency settings.

### `_filter_disabled_repos()` (internal)

```python
def _filter_disabled_repos(
    prs: list[PullRequest],
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> list[PullRequest]:
```

Removes PRs from repos that have `enabled = False` in `repo_overrides`. Returns
all PRs unchanged if `repo_overrides` is `None` or empty.

### `_get_repo_urgency()` (internal)

```python
def _get_repo_urgency(
    repo_name: str,
    default_urgency: str,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> str:
```

Returns the urgency for a given repo, falling back to the global default if the
repo has no override.

### `_get_repo_threshold()` (internal)

```python
def _get_repo_threshold(
    repo_name: str,
    default_threshold: int,
    repo_overrides: dict[str, RepoNotificationConfig] | None,
) -> int:
```

Returns the threshold for a given repo, falling back to the global default if
the repo has no override.

## Usage example

```python
from forgewatch.notifier import notify_new_prs
from forgewatch.config import RepoNotificationConfig
from forgewatch.store import PRStore

store = PRStore()

# After a poll cycle:
diff = store.update(prs_from_poller)
if diff.new_prs:
    await notify_new_prs(diff.new_prs)

# With custom threshold and urgency:
await notify_new_prs(diff.new_prs, threshold=5, urgency="critical")

# With repo grouping:
await notify_new_prs(diff.new_prs, grouping="repo")

# With per-repo overrides:
overrides = {
    "acme/web": RepoNotificationConfig(urgency="critical", threshold=5),
    "acme/noisy": RepoNotificationConfig(enabled=False),
}
await notify_new_prs(diff.new_prs, grouping="repo", repo_overrides=overrides)
```

## Design notes

- Uses `notify-send` via subprocess rather than a Python binding to avoid an
  extra dependency -- `notify-send` (from `libnotify-bin`) is already present
  on XFCE and most other desktop Linux environments
- Clickable notifications use `notify-send --action=open=Open` and a background
  task that monitors stdout for the action name, then opens the PR URL via the
  shared `url_opener` module (see [url_opener.md](url_opener.md)). The URL
  opener tries the XDG Desktop Portal (D-Bus) first, falling back to `xdg-open`
  when the portal is unavailable. The portal approach is necessary because
  `xdg-open` fails silently inside the systemd sandbox when the browser is a
  Snap package (Snap's `snap-confine` rejects the restricted permissions)
- Author avatars are downloaded from GitHub, cached on disk (MD5-hashed
  filenames), and passed to `notify-send` via `--icon={path}`. A shared
  `aiohttp.ClientSession` is used for all avatar downloads within a
  notification batch to avoid creating a new session per avatar
- The individual vs. batch threshold prevents desktop notification floods when
  many PRs appear at once (e.g., first poll after starting the daemon). The
  threshold is configurable via the `threshold` parameter
- Repo grouping mode (`grouping="repo"`) uses `itertools.groupby` after sorting
  by `repo_full_name`, so each repo's PRs are handled independently with their
  own threshold/urgency settings
- Per-repo overrides allow disabling notifications for noisy repos, setting
  repo-specific urgency levels, or adjusting the summary threshold per repo
- Background tasks are stored in `_background_tasks` to prevent garbage
  collection before completion
- All errors are caught and logged -- the notifier never raises exceptions
  that would break the daemon's poll loop
