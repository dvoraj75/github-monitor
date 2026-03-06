# `indicator/` -- API reference

Package: `github_monitor.indicator`

Optional system tray indicator that displays a live PR count and a clickable
popup window. Runs as a separate process and connects to the daemon over D-Bus.
The indicator does not import any daemon modules -- it uses its own data models
(`PRInfo`, `DaemonStatus`) to maintain process boundary isolation.

Requires GTK3, AppIndicator3 (system packages), and `gbulb` (Python package).
See the [development guide](../development.md#system-tray-indicator-dependencies)
for installation instructions.

## Module overview

| Module | Role |
|---|---|
| `__main__.py` | Entry point -- dependency checks, argument parsing, gbulb install, launch |
| `app.py` | Orchestrator -- wires D-Bus client, tray icon, and popup window |
| `client.py` | Async D-Bus client -- connects to daemon, subscribes to signals, auto-reconnects |
| `tray.py` | AppIndicator3 system tray icon with PR count label and GTK menu |
| `window.py` | GTK3 popup window with scrollable PR list and status footer |
| `models.py` | `PRInfo` and `DaemonStatus` frozen dataclasses |
| `_tray_state.py` | Pure functions for icon name selection, label formatting, and tooltip text (no GTK imports) |
| `_window_helpers.py` | Pure functions for relative time, sorting, status text, markup escaping (no GTK imports) |

---

## `__main__.py` -- Entry point

### `_check_dependencies()`

```python
def _check_dependencies() -> bool:
```

Verify that all required dependencies are available. Checks for PyGObject
(`gi`), GTK 3.0 typelib, AppIndicator3 0.1 typelib, and `gbulb`. Prints
actionable error messages to stderr for each missing dependency.

**Returns:** `True` if all dependencies are present, `False` otherwise.

### `main()`

```python
def main() -> None:
```

Launch the indicator after verifying dependencies.

1. Calls `_check_dependencies()` -- exits with code 1 on failure
2. Parses `--verbose` flag for debug logging
3. Configures logging
4. Loads `config.toml` (best-effort) to read the `icon_theme` setting; falls
   back to `"light"` if config loading fails for any reason
5. Installs `gbulb` event loop (`gbulb.install()`)
6. Creates an `IndicatorApp(icon_theme=...)` and runs it in a new event loop
7. Calls `app.shutdown()` in a `finally` block for clean resource release

**CLI arguments:**

| Argument | Description |
|---|---|
| `-v`, `--verbose` | Enable debug logging |

---

## `models.py` -- Data models

### `PRInfo`

```python
@dataclass(frozen=True)
class PRInfo:
    url: str
    title: str
    repo: str
    author: str
    author_avatar_url: str
    number: int
    updated_at: datetime
    review_requested: bool
    assigned: bool
```

Pull request data as received from the daemon over D-Bus. This is
intentionally separate from the daemon's `PullRequest` dataclass to maintain
process boundary isolation -- the indicator should not import daemon internals.

| Field | Type | Description |
|---|---|---|
| `url` | `str` | PR HTML URL (clickable link) |
| `title` | `str` | PR title |
| `repo` | `str` | Repository full name (`owner/repo`) |
| `author` | `str` | PR author username |
| `author_avatar_url` | `str` | Author's GitHub avatar URL |
| `number` | `int` | PR number |
| `updated_at` | `datetime` | Last update timestamp (timezone-aware) |
| `review_requested` | `bool` | Whether the user is a requested reviewer |
| `assigned` | `bool` | Whether the user is an assignee |

### `DaemonStatus`

```python
@dataclass(frozen=True)
class DaemonStatus:
    pr_count: int
    last_updated: datetime | None
```

Daemon status metadata as received over D-Bus.

| Field | Type | Description |
|---|---|---|
| `pr_count` | `int` | Number of PRs currently tracked |
| `last_updated` | `datetime \| None` | UTC timestamp of last poll, or `None` if never polled |

---

## `client.py` -- D-Bus client

### Constants

| Constant | Value | Description |
|---|---|---|
| `BUS_NAME` | `org.github_monitor.Daemon` | Daemon's D-Bus bus name |
| `OBJECT_PATH` | `/org/github_monitor/Daemon` | Daemon's D-Bus object path |
| `INTERFACE_NAME` | `org.github_monitor.Daemon` | Daemon's D-Bus interface name |
| `_RECONNECT_INTERVAL_S` | `10` | Seconds between reconnection attempts |

These are intentionally duplicated from `dbus_service.py` because the
indicator is a separate process and should not import daemon internals.

### Parsing helpers

#### `_parse_pr(data)`

```python
def _parse_pr(data: dict[str, object]) -> PRInfo:
```

Parse a single PR dict from the daemon's JSON into a `PRInfo` dataclass.

#### `_parse_prs(json_str)`

```python
def _parse_prs(json_str: str) -> list[PRInfo]:
```

Parse a JSON array string into a list of `PRInfo` dataclasses.

#### `_parse_status(json_str)`

```python
def _parse_status(json_str: str) -> DaemonStatus:
```

Parse a JSON object string into a `DaemonStatus` dataclass. Handles
`last_updated` being `None` (daemon has never polled yet).

### `DaemonClient`

```python
class DaemonClient:
    def __init__(
        self,
        on_prs_changed: Callable[[list[PRInfo]], None],
        on_connection_changed: Callable[[bool], None],
    ) -> None: ...
```

Async D-Bus client for the github-monitor daemon. Connects to the session
bus, obtains a proxy for the daemon's interface, subscribes to the
`PullRequestsChanged` signal, and handles automatic reconnection.

**Constructor parameters:**

| Parameter | Type | Description |
|---|---|---|
| `on_prs_changed` | `Callable[[list[PRInfo]], None]` | Called when the daemon emits `PullRequestsChanged` |
| `on_connection_changed` | `Callable[[bool], None]` | Called when connection state changes (`True` = connected) |

#### Properties

| Property | Type | Description |
|---|---|---|
| `connected` | `bool` | Whether the client is currently connected to the daemon |

#### `connect()`

```python
async def connect(self) -> None:
```

Connect to the daemon over D-Bus. On success, subscribes to the
`PullRequestsChanged` signal and installs a message handler to detect
daemon name disappearance (`NameOwnerChanged`). On failure, marks the
client as disconnected and schedules a reconnection attempt.

#### `disconnect()`

```python
async def disconnect(self) -> None:
```

Disconnect from D-Bus and cancel any pending reconnection timer.

#### `get_pull_requests()`

```python
async def get_pull_requests(self) -> list[PRInfo]:
```

Call the daemon's `GetPullRequests()` D-Bus method. Returns the parsed PR
list, or an empty list on failure (marks client as disconnected).

#### `get_status()`

```python
async def get_status(self) -> DaemonStatus | None:
```

Call the daemon's `GetStatus()` D-Bus method. Returns the parsed status,
or `None` on failure (marks client as disconnected).

#### `refresh()`

```python
async def refresh(self) -> list[PRInfo]:
```

Call the daemon's `Refresh()` D-Bus method (triggers an immediate poll).
Returns the updated PR list, or an empty list on failure.

#### Internal methods

| Method | Description |
|---|---|
| `_require_interface()` | Return the D-Bus interface proxy or raise `ConnectionError` |
| `_on_signal(json_str)` | Handle the `PullRequestsChanged` signal -- parse JSON, call `on_prs_changed` |
| `_on_message(msg)` | Low-level message handler to detect `NameOwnerChanged` for the daemon's bus name |
| `_set_disconnected()` | Mark as disconnected, notify callback, schedule reconnect |
| `_schedule_reconnect()` | Schedule a reconnection attempt after `_RECONNECT_INTERVAL_S` seconds |
| `_cancel_reconnect()` | Cancel a pending reconnection timer |

---

## `app.py` -- Orchestrator

### `IndicatorApp`

```python
class IndicatorApp:
    def __init__(self, *, icon_theme: str = "light") -> None: ...
```

Main application that bridges D-Bus, tray icon, and popup window. Creates
and wires together a `DaemonClient`, `TrayIcon`, and `PRWindow`.

The `icon_theme` parameter is forwarded to `TrayIcon` to select the icon
variant directory (`resources/light/` or `resources/dark/`).

The lifecycle is:
1. `run()` -- register signal handlers, connect to daemon, enter event loop
2. Event loop -- GTK events and asyncio coroutines run cooperatively via `gbulb`
3. `shutdown()` -- cancel background tasks, disconnect from D-Bus

#### `run()`

```python
async def run(self) -> None:
```

Start the indicator and run until shutdown is requested. Assumes
`gbulb.install()` has already been called. Registers `SIGTERM` and `SIGINT`
handlers, connects to the daemon, fetches initial state, and waits on a
shutdown event.

#### `shutdown()`

```python
async def shutdown(self) -> None:
```

Clean up resources: cancel pending background tasks and disconnect from
D-Bus.

#### Callbacks

These synchronous callbacks are registered with the client, tray, and window:

| Callback | Trigger | Action |
|---|---|---|
| `_on_prs_changed(prs)` | D-Bus `PullRequestsChanged` signal | Schedule async UI update |
| `_on_connection_changed(connected)` | D-Bus connect/disconnect | Update tray icon; fetch PRs on connect |
| `_on_activate()` | Tray "Show PRs" click | Toggle popup window |
| `_on_window_visibility_changed(visible)` | Window show/hide | Update tray menu label |
| `_on_refresh()` | Tray/window "Refresh" click | Schedule async daemon refresh |
| `_on_pr_clicked(url)` | PR row click in popup | Hide window, open URL in browser |
| `_on_quit()` | Tray "Quit" click | Set shutdown event |

#### Internal helpers

| Method | Description |
|---|---|
| `_handle_prs_changed(prs)` | Async: fetch status, update UI |
| `_handle_connected()` | Async: fetch initial PRs + status after (re)connecting |
| `_handle_refresh()` | Async: call daemon `Refresh()`, update UI |
| `_handle_open_url(url)` | Async: open URL via `url_opener.open_url()` |
| `_fetch_and_update()` | Async: fetch PRs + status, update UI |
| `_fetch_status()` | Async: fetch daemon status, fall back to cached value on error |
| `_update_ui(prs, status)` | Sync: push data to tray icon and popup window |
| `_schedule(coro)` | Schedule an async coroutine from a sync callback; store task ref to prevent GC |
| `_task_done(task)` | Discard completed task; log unhandled exceptions |

---

## `tray.py` -- System tray icon

### Constants

| Constant | Value | Description |
|---|---|---|
| `_INDICATOR_ID` | `github-monitor-indicator` | AppIndicator3 indicator ID |
| `_RESOURCES_DIR` | `indicator/resources/` | Base directory for icon files; subdirectory is selected by `icon_theme` (`light/` or `dark/`) |

### `TrayIcon`

```python
class TrayIcon:
    def __init__(
        self,
        on_activate: Callable[[], None],
        on_refresh: Callable[[], None],
        on_quit: Callable[[], None],
        *,
        icon_theme: str = "light",
    ) -> None: ...
```

AppIndicator3-based system tray icon with a PR count label and a GTK menu.

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `on_activate` | `Callable[[], None]` | *(required)* | Called when "Show PRs" / "Hide PRs" is clicked |
| `on_refresh` | `Callable[[], None]` | *(required)* | Called when "Refresh" is clicked |
| `on_quit` | `Callable[[], None]` | *(required)* | Called when "Quit" is clicked |
| `icon_theme` | `str` | `"light"` | Icon variant: `"light"` (dark icons for light panels) or `"dark"` (light icons for dark panels) |

**Menu items:** Show PRs (toggles label), Refresh, Quit.

#### `set_pr_count(count, *, has_review_requested)`

```python
def set_pr_count(self, count: int, *, has_review_requested: bool) -> None:
```

Update the displayed PR count and icon state. Recalculates the icon name
(via `_tray_state.get_icon_name()`), label (via `_tray_state.get_label()`),
and tooltip (via `_tray_state.get_tooltip()`). The tooltip is set via
`AppIndicator3.Indicator.set_title()` and is shown on mouse hover.

#### `set_connected(*, connected)`

```python
def set_connected(self, *, connected: bool) -> None:
```

Update the daemon connection state and icon appearance.

#### `set_window_visible(*, visible)`

```python
def set_window_visible(self, *, visible: bool) -> None:
```

Update the "Show PRs" / "Hide PRs" menu item label based on popup
window visibility.

---

## `window.py` -- Popup window

### Constants

| Constant | Value | Description |
|---|---|---|
| `_WINDOW_WIDTH` | `400` | Fixed popup window width in pixels |
| `_MAX_WINDOW_HEIGHT` | `500` | Maximum popup window height in pixels |

### `PRWindow`

```python
class PRWindow:
    def __init__(
        self,
        on_pr_clicked: Callable[[str], None],
        on_refresh: Callable[[], None],
        on_visibility_changed: Callable[[bool], None] | None = None,
    ) -> None: ...
```

GTK3 popup window with a header (title + refresh button), a scrollable PR
list, and a status footer.

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `on_pr_clicked` | `Callable[[str], None]` | *(required)* | Called with the PR URL when a row is clicked |
| `on_refresh` | `Callable[[], None]` | *(required)* | Called when the header refresh button is pressed |
| `on_visibility_changed` | `Callable[[bool], None] \| None` | `None` | Called when the window is shown or hidden |

#### Properties

| Property | Type | Description |
|---|---|---|
| `visible` | `bool` | Whether the popup window is currently visible |

#### `update_prs(prs, status)`

```python
def update_prs(self, prs: list[PRInfo], status: DaemonStatus | None) -> None:
```

Rebuild the PR list and update the footer. PRs are sorted via
`_window_helpers.sort_prs()` (review-requested first, then by
`updated_at` descending). If the list is empty, shows a "No pull requests"
empty state. The footer displays the PR count and last update time.

#### `show()`

```python
def show(self) -> None:
```

Show the popup window, positioned near the mouse pointer. Clamps to the
current monitor bounds so the window stays on-screen.

#### `hide()`

```python
def hide(self) -> None:
```

Hide the popup window.

#### `toggle()`

```python
def toggle(self) -> None:
```

Toggle popup window visibility.

#### `set_disconnected()`

```python
def set_disconnected(self) -> None:
```

Show a "Daemon is not running" empty state in the window and clear the
footer.

#### PR row layout

Each row displays:
- **Status dot** -- orange for review-requested, blue for assigned
- **Line 1:** `repo/name #number` (bold repo name)
- **Line 2:** PR title (ellipsized)
- **Line 3:** `by author . relative_time` (dimmed)

Clicking a row calls `on_pr_clicked(url)`.

#### Window behaviour

- Auto-hides on focus-out (clicking outside the window)
- Positioned near the mouse pointer on show, clamped to monitor bounds
- Non-decorated, non-resizable, skip-taskbar, popup-menu type hint
- On Wayland, `move()` may be ignored (acceptable for v1)

---

## `_tray_state.py` -- Pure tray state logic

No GTK imports -- fully unit-testable without system packages.

### `Icon`

```python
class Icon(StrEnum):
    NEUTRAL = "github-monitor"
    ACTIVE = "github-monitor-active"
    ALERT = "github-monitor-alert"
    DISCONNECTED = "github-monitor-disconnected"
```

Icon name constants resolved from the icon theme or the custom icon
directory.

### `get_icon_name()`

```python
def get_icon_name(count: int, *, has_review_requested: bool, connected: bool) -> Icon:
```

Determine the icon name based on current state.

**Priority (highest to lowest):**

1. Not connected --> `Icon.DISCONNECTED`
2. Has review-requested PRs --> `Icon.ALERT`
3. Has any PRs --> `Icon.ACTIVE`
4. Otherwise --> `Icon.NEUTRAL`

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `count` | `int` | Current PR count |
| `has_review_requested` | `bool` | Whether any PR has `review_requested=True` |
| `connected` | `bool` | Whether the indicator is connected to the daemon |

**Returns:** An `Icon` enum member.

### `get_label()`

```python
def get_label(count: int) -> str:
```

Format the tray label from a PR count. Returns an empty string for zero
(no label shown), otherwise the count as a string.

### `get_tooltip()`

```python
def get_tooltip(count: int, *, has_review_requested: bool, connected: bool) -> str:
```

Build a dynamic tooltip string for the tray icon. The tooltip is displayed
when the user hovers over the tray icon (via `AppIndicator3.Indicator.set_title()`).

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `count` | `int` | Current PR count |
| `has_review_requested` | `bool` | Whether any PR has `review_requested=True` |
| `connected` | `bool` | Whether the indicator is connected to the daemon |

**Return values:**

| Condition | Example output |
|---|---|
| Not connected | `"GitHub Monitor — Disconnected"` |
| Zero PRs | `"GitHub Monitor — No open PRs"` |
| 1 PR, no review | `"GitHub Monitor — 1 open PR"` |
| Multiple PRs, no review | `"GitHub Monitor — 3 open PRs"` |
| PRs with review requested | `"GitHub Monitor — 3 open PRs (review requested)"` |

---

## `_window_helpers.py` -- Pure window helpers

No GTK imports -- fully unit-testable without system packages.

### Time constants

| Constant | Value | Description |
|---|---|---|
| `_MINUTE` | `60` | Seconds in a minute |
| `_HOUR` | `3600` | Seconds in an hour |
| `_DAY` | `86400` | Seconds in a day |
| `_WEEK` | `604800` | Seconds in a week |
| `_MONTH` | `2592000` | Seconds in a month (approximate, 30 days) |

### `relative_time()`

```python
def relative_time(dt: datetime, *, now: datetime | None = None) -> str:
```

Convert a datetime to a human-readable relative time string.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `dt` | `datetime` | *(required)* | Timezone-aware datetime to format |
| `now` | `datetime \| None` | `None` | Override for current time (for deterministic tests) |

**Return values:**

| Condition | Example output |
|---|---|
| Future or < 60s | `"just now"` |
| < 1 hour | `"5 minutes ago"` |
| < 1 day | `"3 hours ago"` |
| < 2 weeks | `"4 days ago"` |
| < 2 months | `"3 weeks ago"` |
| >= 2 months | `"5 months ago"` |

Handles singular/plural correctly (e.g. "1 minute ago", "2 minutes ago").

### `status_text()`

```python
def status_text(count: int, last_updated: datetime | None, *, now: datetime | None = None) -> str:
```

Format the footer status string displayed at the bottom of the popup window.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `count` | `int` | *(required)* | Current PR count |
| `last_updated` | `datetime \| None` | *(required)* | Last poll timestamp, or `None` |
| `now` | `datetime \| None` | `None` | Override for current time (for tests) |

**Examples:**

- `"5 pull requests . Updated 2 hours ago"`
- `"1 pull request . Updated just now"`
- `"No pull requests"`

### `sort_prs()`

```python
def sort_prs(prs: list[PRInfo]) -> list[PRInfo]:
```

Sort PRs: review-requested first, then by `updated_at` descending. Returns
a new list; the original is not mutated.

### `escape_markup()`

```python
def escape_markup(text: str) -> str:
```

Escape text for safe use in Pango markup. Replaces `&`, `<`, and `>` with
their XML entity equivalents.

---

## Usage example

```python
# The indicator is typically launched via its entry point:
#   python -m github_monitor.indicator
#   github-monitor-indicator

# Or programmatically:
import asyncio
import gbulb
from github_monitor.indicator.app import IndicatorApp

gbulb.install()
app = IndicatorApp(icon_theme="dark")  # or "light" (default)
loop = asyncio.new_event_loop()
try:
    loop.run_until_complete(app.run())
finally:
    loop.run_until_complete(app.shutdown())
    loop.close()
```

## Design notes

- The indicator is a **separate process** that communicates with the daemon
  exclusively over D-Bus. It never imports daemon modules (`poller`, `store`,
  etc.)
- `PRInfo` and `DaemonStatus` are defined in `models.py` separately from the
  daemon's `PullRequest` dataclass to enforce process boundary isolation
- `_tray_state.py` and `_window_helpers.py` are deliberately free of GTK
  imports so they can be unit-tested in CI environments without system GTK
  packages installed
- `gbulb` provides a GLib-based asyncio event loop, allowing GTK callbacks
  (synchronous) and D-Bus calls (asynchronous) to run cooperatively in a
  single thread
- The `_schedule()` pattern in `IndicatorApp` bridges sync GTK callbacks to
  async coroutines by wrapping them in `asyncio.ensure_future()` and storing
  task references to prevent garbage collection
- Auto-reconnection: when the daemon exits or crashes, the client detects the
  `NameOwnerChanged` signal and retries the connection every 10 seconds
- D-Bus coordinates (`BUS_NAME`, `OBJECT_PATH`, `INTERFACE_NAME`) are
  duplicated from `dbus_service.py` rather than imported, reinforcing the
  process boundary
