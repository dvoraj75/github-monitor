# `dbus_service.py` -- API reference

Module: `github_monitor.dbus_service`

Exposes the daemon's state on the D-Bus session bus under the well-known name
`org.github_monitor.Daemon`. External tools (panel plugins, CLI scripts) can
call methods to query PR state or trigger a refresh, and subscribe to the
`PullRequestsChanged` signal for live updates.

## Constants

| Constant | Value | Description |
|---|---|---|
| `BUS_NAME` | `org.github_monitor.Daemon` | Well-known D-Bus bus name |
| `OBJECT_PATH` | `/org/github_monitor/Daemon` | Object path where the interface is exported |
| `INTERFACE_NAME` | `org.github_monitor.Daemon` | D-Bus interface name |

## Serialisation helpers

### `_serialize_pr(pr: PullRequest) -> dict[str, Any]`

Convert a single `PullRequest` to a JSON-serialisable dictionary with keys:
`url`, `title`, `repo`, `author`, `author_avatar_url`, `number`, `updated_at` (ISO 8601 string),
`review_requested`, `assigned`.

### `_serialize_prs(prs: list[PullRequest]) -> str`

Serialise a list of `PullRequest` objects to a JSON string (array of objects).

### `_serialize_status(status: StoreStatus) -> str`

Serialise a `StoreStatus` to a JSON string with keys: `pr_count` (int),
`last_updated` (ISO 8601 string or `null`).

## `GithubMonitorInterface`

D-Bus service interface class, extends `dbus_next.service.ServiceInterface`.

### Constructor

```python
GithubMonitorInterface(
    store: PRStore,
    poll_callback: Callable[[], Awaitable[None]],
)
```

| Parameter | Type | Description |
|---|---|---|
| `store` | `PRStore` | In-memory store to read PR state from |
| `poll_callback` | `Callable[[], Awaitable[None]]` | Async function to trigger an immediate poll cycle |

### D-Bus methods

#### `GetPullRequests() -> 's'`

Return a JSON array of all currently tracked PRs. Each element contains:

```json
{
    "url": "https://github.com/owner/repo/pull/42",
    "title": "Fix bug",
    "repo": "owner/repo",
    "author": "username",
    "author_avatar_url": "https://avatars.githubusercontent.com/u/12345",
    "number": 42,
    "updated_at": "2025-01-15T10:30:00+00:00",
    "review_requested": true,
    "assigned": false
}
```

#### `GetStatus() -> 's'`

Return a JSON object with store metadata:

```json
{
    "pr_count": 5,
    "last_updated": "2025-01-15T10:30:00+00:00"
}
```

`last_updated` is `null` if the store has never been updated.

#### `Refresh() -> 's'`

Trigger an immediate poll cycle (calls the `poll_callback`), then return the
updated PR list in the same format as `GetPullRequests()`. This method is
async — it awaits the poll callback before returning.

### D-Bus signals

#### `PullRequestsChanged() -> 's'`

Emitted when the PR list changes (new, updated, or closed PRs detected).
Carries a JSON array of all current PRs (same format as `GetPullRequests()`).

The daemon calls this signal after each poll cycle that produces a non-empty
`StateDiff`.

## `setup_dbus()`

```python
async def setup_dbus(
    store: PRStore,
    poll_callback: Callable[[], Awaitable[None]],
) -> tuple[MessageBus, GithubMonitorInterface]:
```

Connect to the D-Bus session bus, create and export the interface, and request
the well-known bus name.

**Returns** a tuple of the connected `MessageBus` and the
`GithubMonitorInterface` instance. The caller should:

- Call `interface.PullRequestsChanged()` after poll cycles with changes
- Call `bus.disconnect()` on shutdown

## Usage example

```python
from github_monitor.store import PRStore
from github_monitor.dbus_service import setup_dbus

store = PRStore()

async def poll_once():
    # ... fetch and update store ...
    pass

bus, interface = await setup_dbus(store, poll_once)

# After a poll cycle with changes:
interface.PullRequestsChanged()

# On shutdown:
bus.disconnect()
```

## Testing with `busctl`

Once the daemon is running, test the interface from the command line:

```bash
# Introspect the interface
busctl --user introspect org.github_monitor.Daemon /org/github_monitor/Daemon

# Call GetPullRequests
busctl --user call org.github_monitor.Daemon /org/github_monitor/Daemon \
    org.github_monitor.Daemon GetPullRequests

# Call GetStatus
busctl --user call org.github_monitor.Daemon /org/github_monitor/Daemon \
    org.github_monitor.Daemon GetStatus

# Trigger a refresh
busctl --user call org.github_monitor.Daemon /org/github_monitor/Daemon \
    org.github_monitor.Daemon Refresh

# Monitor signals
dbus-monitor --session "interface='org.github_monitor.Daemon'"
```

## Design notes

- Return type annotation `"s"` is a D-Bus type signature (string), not a
  Python type — this is how `dbus-next` maps method return types to the D-Bus
  wire format
- Method names use PascalCase (`GetPullRequests`, not `get_pull_requests`)
  following D-Bus naming conventions
- The signal carries the **full current PR list** rather than just the diff,
  which is simpler for consumers that only need current state
- Serialisation helpers are module-level functions (not methods) so they can be
  tested independently
- The interface is not thread-safe; it is designed for single-threaded asyncio
  use alongside the rest of the daemon
