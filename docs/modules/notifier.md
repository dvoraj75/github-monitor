# `notifier.py` — API reference

Module: `github_monitor.notifier`

> **Status:** Implemented (Phase 6).

Sends desktop notifications via `notify-send` when new pull requests are
detected. Small batches get individual notifications; larger batches get a
single summary to avoid desktop spam.

## Constants

| Constant | Value | Description |
|---|---|---|
| `_INDIVIDUAL_THRESHOLD` | `3` | Maximum PRs that trigger individual notifications |
| `_BATCH_BODY_LIMIT` | `5` | Maximum PRs listed in a batch notification body |

## Functions

### `notify_new_prs(new_prs: list[PullRequest]) -> None`

Send desktop notifications for newly discovered PRs. This is the main public
entry point — call it after each poll cycle with the `StateDiff.new_prs` list.

**Behaviour:**

- If `new_prs` is empty, returns immediately (no subprocess calls).
- If 1–3 new PRs: sends one notification per PR with:
  - Summary: `"PR Review: {repo_full_name}"`
  - Body: `"#{number} {title}\nby {author}"`
  - URL: the PR's `html_url` (reserved for future action callbacks)
- If > 3 new PRs: sends a single batch notification with:
  - Summary: `"{count} new PR review requests"`
  - Body: first 5 PRs as `"- {repo}#{number}: {title}"`, one per line

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `new_prs` | `list[PullRequest]` | PRs not seen in the previous poll cycle |

### `_send_notification(summary, body, *, url=None, urgency="normal") -> None`

Low-level function that calls `notify-send` as an async subprocess.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `summary` | `str` | *(required)* | Notification title |
| `body` | `str` | *(required)* | Notification body text |
| `url` | `str \| None` | `None` | Reserved for future action callbacks |
| `urgency` | `str` | `"normal"` | Urgency level: `low`, `normal`, or `critical` |

**Command constructed:**

```
notify-send --app-name=github-monitor --urgency={urgency} --icon=github {summary} {body}
```

**Error handling:**

- Non-zero exit code: logs a warning with the exit code and stderr output.
  Does **not** raise an exception.
- `notify-send` not found (`FileNotFoundError`): logs a warning suggesting
  `libnotify-bin` installation. Does **not** raise an exception.

Notifications are fire-and-forget — failures never interrupt the poll loop.

## Usage example

```python
from github_monitor.notifier import notify_new_prs
from github_monitor.store import PRStore

store = PRStore()

# After a poll cycle:
diff = store.update(prs_from_poller)
if diff.new_prs:
    await notify_new_prs(diff.new_prs)
```

## Design notes

- Uses `notify-send` via subprocess rather than a Python binding to avoid an
  extra dependency — `notify-send` (from `libnotify-bin`) is already present
  on XFCE and most other desktop Linux environments
- The `url` parameter is accepted but not currently passed to `notify-send`.
  It is reserved for future use with notification action callbacks (e.g.,
  opening the PR in a browser when the notification is clicked)
- The individual vs. batch threshold prevents desktop notification floods when
  many PRs appear at once (e.g., first poll after starting the daemon)
- All errors are caught and logged — the notifier never raises exceptions
  that would break the daemon's poll loop
