# Configuration

ForgeWatch is configured via a TOML file and optional environment variable
overrides.

## Config file location

> **Tip:** Run `forgewatch setup` (or `forgewatch setup --config-only`)
> to create the config file interactively. The wizard prompts for the token,
> username, poll interval, and optional repository filter, then writes
> `config.toml` to the default location.

The config file path is resolved in this order:

1. **Explicit path** -- passed directly to `load_config(path)` or via the `-c` /
   `--config` CLI flag
2. **`FORGEWATCH_CONFIG` env var** -- if set, its value is used as the config
   file path
3. **Default path** -- `~/.config/forgewatch/config.toml`

If no config file is found at the resolved path, a `ConfigError` is raised.

## Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `github_token` | string | Yes | -- | GitHub personal access token (PAT) with `repo` scope |
| `github_username` | string | Yes | -- | Your GitHub username (used in search queries) |
| `poll_interval` | integer | No | `300` | Seconds between poll cycles (minimum: 30) |
| `repos` | list of strings | No | `[]` | Repository filter in `owner/name` format; empty = all repos |
| `log_level` | string | No | `"info"` | Log level: `"debug"`, `"info"`, `"warning"`, or `"error"` |
| `notify_on_first_poll` | boolean | No | `false` | Send notifications for PRs found on the first poll |
| `notifications_enabled` | boolean | No | `true` | Enable/disable desktop notifications entirely |
| `dbus_enabled` | boolean | No | `true` | Enable/disable the D-Bus interface |
| `github_base_url` | string | No | `"https://api.github.com"` | GitHub API base URL (for GitHub Enterprise Server) |
| `max_retries` | integer | No | `3` | Max HTTP retries for 5xx errors (minimum: 0) |
| `notification_threshold` | integer | No | `3` | PRs above this count get a summary notification instead of individual ones (minimum: 1) |
| `notification_urgency` | string | No | `"normal"` | Notification urgency: `"low"`, `"normal"`, or `"critical"` |
| `icon_theme` | string | No | `"light"` | Icon theme for the system tray indicator: `"light"` (dark icons for light panels) or `"dark"` (light icons for dark panels) |

### `[notifications]` section

Settings for notification grouping and per-repo overrides. These affect how
desktop notifications are grouped and allow fine-grained control per repository.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `grouping` | string | No | `"flat"` | Grouping mode: `"flat"` (single list) or `"repo"` (grouped by repository) |

#### `[notifications.repos."owner/repo"]` sub-tables

Per-repo notification overrides. Each key is a repository in `owner/name`
format. Repos without an entry use the global defaults.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `enabled` | boolean | No | `true` | Set to `false` to suppress notifications for this repo |
| `urgency` | string | No | `"normal"` | Notification urgency: `"low"`, `"normal"`, or `"critical"` |
| `threshold` | integer | No | `3` | Individual vs. summary threshold for this repo (minimum: 1) |

### `[indicator]` section

Settings for the system tray indicator process. These are read by the
indicator via `load_indicator_config()` and have no effect on the daemon.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `reconnect_interval` | integer | No | `10` | Seconds between D-Bus reconnect attempts (minimum: 1) |
| `window_width` | integer | No | `400` | Popup window width in pixels (minimum: 200) |
| `max_window_height` | integer | No | `500` | Maximum popup window height in pixels (minimum: 200) |

## GitHub token setup

ForgeWatch needs a GitHub personal access token (PAT) to query the
Search API for pull requests. GitHub offers two token types: **classic** and
**fine-grained**. Either works; fine-grained tokens allow tighter scoping and
are GitHub's recommended path going forward.

### Option A: Classic personal access token

Classic tokens use broad OAuth scopes. They are simpler to set up and widely
supported.

1. Open **Settings > Developer settings > Personal access tokens > Tokens
   (classic)** in GitHub, or go directly to:\
   <https://github.com/settings/tokens/new>
2. Fill in the form:
   - **Note** -- a descriptive name, e.g. `forgewatch`
   - **Expiration** -- pick a duration (90 days recommended; see
     [Security tips](#security-tips) below)
   - **Scopes** -- tick the required scope from the table below
3. Click **Generate token** and copy the value immediately (it is shown only
   once).

| Scope | When to use | What it grants |
|---|---|---|
| `repo` | You monitor **private** repositories | Full read/write access to private repos (GitHub does not offer a read-only private-repo scope for classic tokens) |
| `public_repo` | You **only** monitor public repositories | Read access to public repo data -- sufficient if all your review requests are on public repos |

> **Why `repo`?** ForgeWatch calls the GitHub Search Issues API
> (`search/issues`) to find PRs where you are a reviewer or assignee. For
> private repos, this endpoint requires the `repo` scope. If you only work
> with public repos, `public_repo` is enough.

### Option B: Fine-grained personal access token

Fine-grained tokens let you grant the minimum permissions needed and restrict
access to specific repositories or organisations.

1. Open **Settings > Developer settings > Personal access tokens >
   Fine-grained tokens** in GitHub, or go directly to:\
   <https://github.com/settings/personal-access-tokens/new>
2. Fill in the form:
   - **Token name** -- e.g. `forgewatch`
   - **Expiration** -- pick a duration (90 days recommended)
   - **Resource owner** -- select your personal account or the organisation
     whose repos you want to monitor
   - **Repository access** -- choose one of:
     - *All repositories* -- monitor PRs across every repo you have access to
     - *Only select repositories* -- pick specific repos (must match the
       `repos` list in your config, if set)
   - **Permissions** -- expand **Repository permissions** and set the entries
     from the table below; leave everything else at *No access*
3. Click **Generate token** and copy the value immediately.

| Permission | Access level | Why needed |
|---|---|---|
| **Pull requests** | Read-only | Query pull requests assigned to you or requesting your review |
| **Metadata** | Read-only | Automatically granted when any other repository permission is selected |

> **Tip:** If you use the `repos` config option to filter to specific
> repositories, you can scope the fine-grained token to exactly those repos
> for minimal privilege.

### Security tips

- **Prefer environment variables.** Set `GITHUB_TOKEN` instead of putting the
  token in `config.toml` to avoid accidentally committing secrets (see
  [Environment variable overrides](#environment-variable-overrides) below).
- **Set an expiration date** and rotate tokens before they expire. GitHub can
  send you an email reminder before expiry.
- **Use the minimum scope.** If you only monitor public repos, `public_repo`
  (classic) or read-only Pull requests (fine-grained) is sufficient -- there
  is no need for full `repo` access.
- **Never commit `config.toml`** -- it is already listed in `.gitignore`.
- **Revoke unused tokens** at
  <https://github.com/settings/tokens> (classic) or
  <https://github.com/settings/personal-access-tokens> (fine-grained).

## Environment variable overrides

| Variable | Overrides | Notes |
|---|---|---|
| `GITHUB_TOKEN` | `github_token` | Takes precedence over the file value. Useful for keeping tokens out of config files. |
| `FORGEWATCH_CONFIG` | Config file path | Alternative to passing `-c` on the command line. |

`GITHUB_TOKEN` is applied after the config file is loaded, so you can have a
config file without a token and supply it via the environment instead.

## Validation rules

All validation happens at config load time. Validation collects **all** errors
and raises a single `ConfigError` listing every problem, so you can fix
everything in one pass. Error messages include actionable hints where possible
(e.g. example token prefix, recommended poll interval).

Unrecognised top-level keys produce a log warning (possible typo detection).

- `github_token` -- must be a non-empty string
- `github_username` -- must be a non-empty string
- `poll_interval` -- must be an integer >= 30
- `repos` -- must be a list; each entry must match the pattern
  `^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$` (i.e., `owner/name`)
- `log_level` -- must be one of `debug`, `info`, `warning`, `error` (case-insensitive)
- `notify_on_first_poll` -- must be a boolean
- `notifications_enabled` -- must be a boolean
- `dbus_enabled` -- must be a boolean
- `github_base_url` -- must be a string starting with `http://` or `https://`; trailing slashes are stripped
- `max_retries` -- must be an integer >= 0
- `notification_threshold` -- must be an integer >= 1
- `notification_urgency` -- must be one of `low`, `normal`, `critical` (case-insensitive)
- `icon_theme` -- must be one of `light`, `dark` (case-insensitive)

**`[notifications]` section:**

- `notifications` -- must be a table (if present)
- `notifications.grouping` -- must be one of `flat`, `repo` (case-insensitive)
- `notifications.repos` -- must be a table (if present)
- Each `notifications.repos."owner/repo"` entry must be a table with:
  - `enabled` -- must be a boolean
  - `urgency` -- must be one of `low`, `normal`, `critical` (case-insensitive)
  - `threshold` -- must be an integer >= 1

**`[indicator]` section:**

- `reconnect_interval` -- must be an integer >= 1
- `window_width` -- must be an integer >= 200
- `max_window_height` -- must be an integer >= 200

## Example config

A minimal configuration with only required fields:

```toml
github_token    = "ghp_abc123def456"
github_username = "janedoe"
```

This uses defaults: `poll_interval = 300`, `repos = []` (all repositories),
`log_level = "info"`, notifications enabled, D-Bus enabled.

A full configuration:

```toml
github_token            = "ghp_abc123def456"
github_username         = "janedoe"
poll_interval           = 60
repos                   = ["myorg/frontend", "myorg/backend", "otherorg/shared-lib"]
log_level               = "debug"
notify_on_first_poll    = true
notifications_enabled   = true
dbus_enabled            = true
github_base_url         = "https://github.example.com/api/v3"
max_retries             = 5
notification_threshold  = 5
notification_urgency    = "low"
icon_theme              = "light"

[notifications]
grouping = "repo"

[notifications.repos."myorg/frontend"]
urgency = "critical"
threshold = 5

[notifications.repos."myorg/noisy-repo"]
enabled = false

[indicator]
reconnect_interval = 10
window_width       = 400
max_window_height  = 500
```

Using environment variables instead of a token in the file:

```bash
export GITHUB_TOKEN="ghp_abc123def456"
```

```toml
# github_token is omitted — will be picked up from GITHUB_TOKEN
github_username = "janedoe"
poll_interval   = 120
repos           = ["myorg/frontend"]
```

## Config file template

The repository includes a `config.example.toml` at the project root:

```toml
# GitHub personal access token
# Required scopes: repo (for private repos) or public_repo (public only)
github_token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Your GitHub username
github_username = "your-username"

# Polling interval in seconds (default: 300 = 5 minutes)
poll_interval = 300

# Optional: filter to specific repos (owner/name format)
# If empty, monitors all repos where you have review requests
# repos = ["owner/repo1", "owner/repo2"]
repos = []

# Log level: "debug", "info", "warning", or "error" (default: "info")
# log_level = "info"

# Send notifications for PRs found on the first poll (default: false)
# notify_on_first_poll = false

# Enable/disable desktop notifications (default: true)
# notifications_enabled = true

# Enable/disable D-Bus interface (default: true)
# dbus_enabled = true

# GitHub API base URL (default: "https://api.github.com")
# github_base_url = "https://github.example.com/api/v3"

# Max HTTP retries for 5xx errors with exponential backoff (default: 3)
# max_retries = 3

# Number of new PRs that trigger individual notifications (default: 3)
# notification_threshold = 3

# Notification urgency: "low", "normal", or "critical" (default: "normal")
# notification_urgency = "normal"

# Icon theme for the system tray indicator: "light" or "dark" (default: "light")
# Use "light" for light desktop panels (dark icons on light background).
# Use "dark" for dark desktop panels (light icons on dark background).
# icon_theme = "light"

# ---------------------------------------------------------------------------
# Notification grouping and per-repo overrides
# ---------------------------------------------------------------------------

# [notifications]
# grouping = "flat"                  # "flat" (default) or "repo"
#
# [notifications.repos."owner/repo"]
# enabled = true                     # Set to false to suppress notifications
# urgency = "normal"                 # "low", "normal", or "critical"
# threshold = 3                      # Individual vs summary threshold

# ---------------------------------------------------------------------------
# Indicator settings (system tray process)
# ---------------------------------------------------------------------------

# [indicator]
# reconnect_interval = 10   # Seconds between reconnect attempts (default: 10)
# window_width = 400         # Popup window width in pixels (default: 400)
# max_window_height = 500    # Maximum popup window height in pixels (default: 500)
```

## Runtime changes via SIGHUP

Configuration can be reloaded at runtime by sending `SIGHUP` to the daemon:

```bash
systemctl --user reload forgewatch
# or
kill -HUP $(pidof forgewatch)
```

On reload, the daemon re-reads the config file (respecting the original `-c`
path if one was provided at startup), updates the GitHub client settings
(token, username, repos, base URL, retries), and applies the new log level
immediately.

## Programmatic usage

```python
from pathlib import Path
from forgewatch.config import load_config, load_indicator_config

# Load from default path
cfg = load_config()

# Load from explicit path
cfg = load_config(Path("/etc/forgewatch/config.toml"))

# Load from string path
cfg = load_config("/tmp/test-config.toml")

# Access fields
print(cfg.github_token)              # "ghp_..."
print(cfg.github_username)           # "janedoe"
print(cfg.poll_interval)             # 300
print(cfg.repos)                     # ["owner/repo1", ...]
print(cfg.log_level)                 # "info"
print(cfg.notifications_enabled)     # True
print(cfg.dbus_enabled)              # True
print(cfg.github_base_url)           # "https://api.github.com"
print(cfg.max_retries)               # 3
print(cfg.notification_threshold)    # 3
print(cfg.notification_urgency)      # "normal"
print(cfg.icon_theme)                # "light"

# Access notification grouping settings
print(cfg.notifications.grouping)    # "flat"
print(cfg.notifications.repos)       # {} (or dict of RepoNotificationConfig)

# Load indicator-specific config ([indicator] section)
ind = load_indicator_config()
print(ind.reconnect_interval)        # 10
print(ind.window_width)              # 400
print(ind.max_window_height)         # 500
```
