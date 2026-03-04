# Systemd integration

This document covers running github-monitor as a systemd user service, including
installation, management, security hardening, and troubleshooting.

## Overview

github-monitor is designed to run as a **systemd user service** — a background
process managed by your user session (not root). This means:

- It starts automatically when you log in
- It restarts on failure
- Logs are captured by journald
- No root privileges required

## Prerequisites

- github-monitor installed (e.g. via `uv sync`, `uv tool install .`, or
  `pip install --user .`)
- A valid configuration file at `~/.config/github-monitor/config.toml`
- D-Bus session bus available (standard on any Linux desktop)
- `systemd --user` running (standard on modern Linux distributions)

## The service unit file

The service file is located at `systemd/github-monitor.service` in the project
repository:

```ini
[Unit]
Description=GitHub PR Monitor
After=network-online.target dbus.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/github-monitor
ExecReload=kill -HUP $MAINPID
Restart=on-failure
RestartSec=10
Environment=GITHUB_TOKEN=

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%h/.config/github-monitor

[Install]
WantedBy=default.target
```

### Directive reference

#### `[Unit]` section

| Directive | Value | Purpose |
|---|---|---|
| `Description` | `GitHub PR Monitor` | Human-readable name shown in `systemctl status` |
| `After` | `network-online.target dbus.service` | Wait for network and D-Bus before starting |
| `Wants` | `network-online.target` | Soft dependency on network (daemon still starts if network is delayed) |

#### `[Service]` section

| Directive | Value | Purpose |
|---|---|---|
| `Type` | `simple` | The process started by `ExecStart` is the main daemon process |
| `ExecStart` | *(resolved at install time)* | Absolute path to the executable, determined by `github-monitor service install` |
| `ExecReload` | `kill -HUP $MAINPID` | Send SIGHUP to reload configuration without restarting |
| `Restart` | `on-failure` | Restart the service if it exits with a non-zero code |
| `RestartSec` | `10` | Wait 10 seconds before restarting after failure |
| `Environment` | `GITHUB_TOKEN=` | Placeholder for the GitHub token (see [Token configuration](#token-configuration)) |

#### Security hardening

| Directive | Value | Purpose |
|---|---|---|
| `NoNewPrivileges` | `true` | Prevent the process from gaining additional privileges via setuid/setgid |
| `ProtectSystem` | `strict` | Mount the entire filesystem read-only (except explicitly allowed paths) |
| `ProtectHome` | `read-only` | Mount `$HOME` read-only |
| `ReadWritePaths` | `%h/.config/github-monitor` | Allow write access to the config directory only |

These directives follow the principle of least privilege. The daemon only needs
to read its config file and make network requests — it does not need write
access to the filesystem.

#### `[Install]` section

| Directive | Value | Purpose |
|---|---|---|
| `WantedBy` | `default.target` | Start the service when the user session starts (i.e. on login) |

## Installation

### Automated (recommended)

The easiest way to install is with the built-in setup wizard:

```bash
github-monitor setup
```

This walks you through configuration, installs systemd service files, and
enables + starts the services. You can also run individual steps:

```bash
github-monitor setup --config-only    # only create config.toml
github-monitor setup --service-only   # only install + start services
```

> **Note:** The `install.sh` script is deprecated. Use `github-monitor setup`
> instead.

### Manual

```bash
# 1. Install/update systemd service files (resolves executable path automatically)
github-monitor service install

# 2. Enable the service (starts on login) and start it now
systemctl --user enable --now github-monitor
```

If you prefer to copy the files yourself, note that the bundled templates in
`systemd/` contain placeholders — use `github-monitor service install` to get
service files with the correct `ExecStart` path for your installation.

## Token configuration

The service file includes an `Environment=GITHUB_TOKEN=` line as a placeholder.
You have several options for providing the token:

### Option 1: Edit the service file (simplest)

Set the token directly in the service file:

```ini
Environment=GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Then reload:

```bash
systemctl --user daemon-reload
systemctl --user restart github-monitor
```

### Option 2: Use the config file

If `github_token` is set in `~/.config/github-monitor/config.toml`, the
daemon will use that value. The `Environment=GITHUB_TOKEN=` line can be left
empty — it only takes effect if set to a non-empty value.

### Option 3: Environment drop-in file

Create an override file to keep secrets out of the main service file:

```bash
mkdir -p ~/.config/systemd/user/github-monitor.service.d/
cat > ~/.config/systemd/user/github-monitor.service.d/token.conf << 'EOF'
[Service]
Environment=GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
systemctl --user daemon-reload
systemctl --user restart github-monitor
```

This approach keeps the token separate from the service file and is not
overwritten when you update the service file from the repository.

## Managing the service

### Via CLI (recommended)

The `github-monitor service` command wraps common systemctl operations:

```bash
github-monitor service status      # show service status
github-monitor service start       # start daemon (+ indicator if installed)
github-monitor service stop        # stop services
github-monitor service restart     # restart services
github-monitor service enable      # enable autostart on login
github-monitor service disable     # disable autostart
github-monitor service install     # install/update systemd unit files
```

These commands automatically manage both the daemon and indicator services
when the indicator service file is installed.

### Via systemctl (manual)

#### Check status

```bash
systemctl --user status github-monitor
```

### View logs

```bash
# Follow logs in real time
journalctl --user -u github-monitor -f

# Show last 50 lines
journalctl --user -u github-monitor -n 50

# Show logs since last boot
journalctl --user -u github-monitor -b

# Show only errors
journalctl --user -u github-monitor -p err
```

### Restart / stop

```bash
# Restart (e.g. after config change)
systemctl --user restart github-monitor

# Stop
systemctl --user stop github-monitor
```

### Reload configuration (without restart)

The daemon handles `SIGHUP` for config reload:

```bash
systemctl --user kill -s HUP github-monitor
```

This reloads the config file and recreates the HTTP session (picks up new
token, poll interval, repo filter, etc.) without losing the current in-memory
state.

### Disable (prevent auto-start on login)

```bash
systemctl --user disable github-monitor
```

## Updating

To update to the latest version:

```bash
pip install --upgrade github-monitor
# or
pipx upgrade github-monitor
```

After updating, reinstall the service files to pick up any changes and restart:

```bash
github-monitor service install
github-monitor service restart
```

> **Note:** The `update.sh` script is deprecated. Use the commands above instead.

To update manually from a git checkout instead:

```bash
git pull
uv tool install . --force --reinstall
github-monitor service install
systemctl --user restart github-monitor
```

## Troubleshooting

### Service fails to start

**Check the logs first:**

```bash
journalctl --user -u github-monitor -n 20 --no-pager
```

**Common causes:**

| Symptom | Cause | Fix |
|---|---|---|
| `ExecStart not found` / exit code 203 | `github-monitor` executable not found at the path in the service file | Re-run `github-monitor service install` to resolve the correct path, or edit `ExecStart` manually |
| `ConfigError: github_token must be non-empty` | No token configured | Set the token via `Environment=GITHUB_TOKEN=...` in the service file, a drop-in, or the config file |
| `ConfigError: ... config.toml not found` | Missing config file | Create `~/.config/github-monitor/config.toml` from `config.example.toml` |
| `FileNotFoundError: notify-send` | `libnotify-bin` not installed | Install with `sudo apt install libnotify-bin` (notifications are optional — the daemon still runs) |

### Service starts but no D-Bus interface

**Check that the session bus is available:**

```bash
busctl --user list | grep github_monitor
```

If the service is running but the bus name does not appear, check that
`DBUS_SESSION_BUS_ADDRESS` is set in the systemd environment:

```bash
systemctl --user show-environment | grep DBUS
```

If it is not set, you may need to import the environment:

```bash
dbus-update-activation-environment --systemd DBUS_SESSION_BUS_ADDRESS
```

### Custom ExecStart path

`github-monitor service install` automatically resolves the executable path
using `$PATH`, so it works with virtualenv, `uv`, `pipx`, and `pip install
--user` installs alike. If you need to override the path manually, edit the
installed service file:

```ini
# Example: uv-managed virtualenv
ExecStart=/home/youruser/.venv/bin/github-monitor

# Example: pipx
ExecStart=/home/youruser/.local/bin/github-monitor
```

Remember to run `systemctl --user daemon-reload` after editing the service file.

### Clicking a notification does not open the browser

When running as a systemd service with security hardening, notification
click-to-open uses the **XDG Desktop Portal** (D-Bus) to open URLs instead of
calling `xdg-open` directly. This is necessary because `xdg-open` can fail
silently inside the sandbox — notably when the browser is a Snap package
(Snap's `snap-confine` rejects the restricted permissions set by
`ProtectSystem=strict` and `NoNewPrivileges=true`).

**Requirements for click-to-open:**

- The `xdg-desktop-portal` service must be running (standard on GNOME, KDE,
  XFCE, and most other desktop environments)
- A portal backend must be installed (e.g. `xdg-desktop-portal-gtk`,
  `xdg-desktop-portal-gnome`, or `xdg-desktop-portal-kde`)

**Verify the portal is available:**

```bash
gdbus call --session \
  -d org.freedesktop.portal.Desktop \
  -o /org/freedesktop/portal/desktop \
  -m org.freedesktop.portal.OpenURI.OpenURI \
  "" "https://example.com" {}
```

If this opens a browser tab, the portal is working. If it fails, install the
portal packages:

```bash
# Debian / Ubuntu
sudo apt install xdg-desktop-portal xdg-desktop-portal-gtk
```

If the portal is unavailable, the notifier falls back to `xdg-open`
automatically (which works when running outside the systemd sandbox, e.g.
during development).

## Indicator service

The system tray indicator is an optional separate process that connects to the
daemon over D-Bus. It has its own systemd service unit that depends on the
daemon service.

### Indicator service unit file

The service file is located at `systemd/github-monitor-indicator.service`:

```ini
[Unit]
Description=GitHub PR Monitor - Panel Indicator
After=github-monitor.service
Wants=github-monitor.service

[Service]
Type=simple
ExecStart=%h/.local/bin/github-monitor-indicator
Restart=on-failure
RestartSec=10

# Security hardening (lighter than daemon — no file writes needed)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=default.target
```

#### Key differences from the daemon service

| Aspect | Daemon | Indicator |
|---|---|---|
| `After` | `network-online.target dbus.service` | `github-monitor.service` |
| `Wants` | `network-online.target` | `github-monitor.service` |
| `WantedBy` | `default.target` | `default.target` |
| `ReadWritePaths` | `%h/.config/github-monitor` | *(none — read-only is sufficient)* |

Both services use `WantedBy=default.target` so they start reliably on login
regardless of the desktop environment. Many DEs and window managers (especially
tiling WMs and some Wayland compositors) never activate
`graphical-session.target`, which would prevent the indicator from starting.
The indicator has `Restart=on-failure`, so if it starts before the display
server is ready it will automatically retry. The `Wants` directive on
`github-monitor.service` ensures the daemon starts alongside the indicator, but
the indicator still starts even if the daemon fails (the indicator auto-reconnects).

### Installing the indicator service

`github-monitor setup` automatically detects GTK3/AppIndicator3 and installs
the indicator service alongside the daemon. To install the indicator manually:

```bash
# 1. Install the indicator package
uv tool install '.[indicator]'
# or: uv sync --extra indicator

# 2. Install service files (resolves executable path automatically)
github-monitor service install

# 3. Enable and start
systemctl --user enable --now github-monitor-indicator
```

### Managing the indicator service

```bash
# Check status
systemctl --user status github-monitor-indicator

# View logs
journalctl --user -u github-monitor-indicator -f

# Restart
systemctl --user restart github-monitor-indicator

# Stop
systemctl --user stop github-monitor-indicator
```

### Indicator troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ExecStart not found` / exit code 203 | `github-monitor-indicator` not found | Re-run `github-monitor service install` or install with `uv tool install '.[indicator]'` |
| `ERROR: GTK 3.0 typelib not found` | Missing GTK3 system packages | `sudo apt install python3-gi gir1.2-gtk-3.0` |
| `ERROR: AppIndicator3 0.1 typelib not found` | Missing AppIndicator3 typelib | `sudo apt install gir1.2-appindicator3-0.1` |
| `ERROR: 'gbulb' package not found` | Missing gbulb Python package | `uv sync --extra indicator` |
| Tray icon shows "disconnected" | Daemon is not running | Start the daemon: `systemctl --user start github-monitor` |
| No tray icon visible | Desktop environment lacks AppIndicator support | Install a system tray extension (e.g. `gnome-shell-extension-appindicator` for GNOME) |

## Uninstallation

### Automated (recommended)

```bash
github-monitor uninstall
```

This stops and disables both services, removes systemd unit files and the
legacy autostart entry, and optionally removes the config directory. If
`systemctl` is not available, the stop/disable steps are skipped but file
removal still proceeds.

### Manual

#### Daemon

```bash
# Stop and disable the service
systemctl --user stop github-monitor
systemctl --user disable github-monitor

# Remove the service file
rm ~/.config/systemd/user/github-monitor.service

# Remove any drop-in overrides
rm -rf ~/.config/systemd/user/github-monitor.service.d/

# Reload systemd
systemctl --user daemon-reload
```

#### Indicator

```bash
# Stop and disable the indicator service
systemctl --user stop github-monitor-indicator
systemctl --user disable github-monitor-indicator

# Remove the service file
rm ~/.config/systemd/user/github-monitor-indicator.service

# Reload systemd
systemctl --user daemon-reload
```
