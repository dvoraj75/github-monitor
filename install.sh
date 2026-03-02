#!/usr/bin/env bash
#
# install.sh — Install github-monitor as a systemd user service
#
# This script:
#   1. Checks prerequisites (Python 3.13+, uv, notify-send, D-Bus)
#   2. Installs the github-monitor package via uv tool install
#   3. Interactively creates ~/.config/github-monitor/config.toml
#   4. Installs and enables the systemd user service
#
# Safe to re-run (idempotent).
#

set -euo pipefail

# --- Colors & helpers --------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}::${NC} $*"; }
ok()    { echo -e "${GREEN}OK${NC} $*"; }
warn()  { echo -e "${YELLOW}WARNING${NC} $*"; }
err()   { echo -e "${RED}ERROR${NC} $*" >&2; }
step()  { echo -e "\n${BOLD}[$1/$TOTAL_STEPS] $2${NC}"; }

TOTAL_STEPS=4

CONFIG_DIR="${HOME}/.config/github-monitor"
CONFIG_FILE="${CONFIG_DIR}/config.toml"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="github-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Step 1: Check prerequisites --------------------------------------------

step 1 "Checking prerequisites"

errors=0

# Python 3.13+
if command -v python3 &>/dev/null; then
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    py_major=$(echo "$py_version" | cut -d. -f1)
    py_minor=$(echo "$py_version" | cut -d. -f2)
    if [[ "$py_major" -lt 3 ]] || { [[ "$py_major" -eq 3 ]] && [[ "$py_minor" -lt 13 ]]; }; then
        err "Python 3.13+ is required (found $py_version)"
        errors=$((errors + 1))
    else
        ok "Python $py_version"
    fi
else
    err "python3 not found"
    info "Install Python 3.13+: https://www.python.org/downloads/"
    errors=$((errors + 1))
fi

# uv
if command -v uv &>/dev/null; then
    uv_version=$(uv --version 2>/dev/null | head -1)
    ok "uv ($uv_version)"
else
    err "uv not found"
    info "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    errors=$((errors + 1))
fi

# notify-send
if command -v notify-send &>/dev/null; then
    ok "notify-send"
else
    warn "notify-send not found (desktop notifications will not work)"
    info "Install it: sudo apt install libnotify-bin"
fi

# D-Bus session bus
if [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    ok "D-Bus session bus"
else
    warn "DBUS_SESSION_BUS_ADDRESS is not set (D-Bus interface will not work)"
    info "This is normal if you're running via SSH. The service will use D-Bus when started in a desktop session."
fi

# Optional: System tray indicator prerequisites (GTK3 + AppIndicator3)
install_indicator=false
if python3 -c "import gi; gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1')" 2>/dev/null; then
    ok "GTK3 + AppIndicator3 (system tray indicator supported)"
    install_indicator=true
else
    warn "GTK3 or AppIndicator3 not found — system tray indicator will not be installed"
    info "To install indicator support later:"
    info "  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 libcairo2-dev libgirepository1.0-dev"
    info "  uv sync --extra indicator"
fi

if [[ "$errors" -gt 0 ]]; then
    echo
    err "Missing $errors required prerequisite(s). Please install them and re-run this script."
    exit 1
fi

# --- Step 2: Install the package ---------------------------------------------

step 2 "Installing github-monitor"

if [[ ! -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    err "pyproject.toml not found in ${SCRIPT_DIR}"
    err "Please run this script from the github-monitor repository root."
    exit 1
fi

info "Running: uv tool install . --force"
if [[ "$install_indicator" == true ]]; then
    info "Including system tray indicator support"
    uv tool install "${SCRIPT_DIR}" --force --with "gbulb>=0.6"
else
    uv tool install "${SCRIPT_DIR}" --force
fi

# Verify the binary is available
if command -v github-monitor &>/dev/null; then
    ok "github-monitor installed at $(command -v github-monitor)"
elif [[ -x "${HOME}/.local/bin/github-monitor" ]]; then
    ok "github-monitor installed at ${HOME}/.local/bin/github-monitor"
    warn "${HOME}/.local/bin is not in your PATH — the systemd service will still work,"
    warn "but you won't be able to run 'github-monitor' from the command line."
    info "Add to your shell profile: export PATH=\"\$HOME/.local/bin:\$PATH\""
else
    err "github-monitor binary not found after installation"
    exit 1
fi

# --- Step 3: Configure -------------------------------------------------------

step 3 "Setting up configuration"

mkdir -p "${CONFIG_DIR}"

write_config=true

if [[ -f "${CONFIG_FILE}" ]]; then
    warn "Config file already exists: ${CONFIG_FILE}"
    echo -n "Overwrite it? [y/N] "
    read -r answer
    if [[ "${answer,,}" != "y" && "${answer,,}" != "yes" ]]; then
        info "Keeping existing config."
        write_config=false
    fi
fi

if [[ "$write_config" == true ]]; then
    echo
    info "Let's configure github-monitor."
    info "You'll need a GitHub personal access token with 'repo' scope."
    info "Create one at: https://github.com/settings/tokens"
    echo

    # GitHub token
    while true; do
        echo -n "GitHub personal access token: "
        read -r github_token
        if [[ -n "$github_token" ]]; then
            break
        fi
        warn "Token is required."
    done

    # GitHub username
    while true; do
        echo -n "GitHub username: "
        read -r github_username
        if [[ -n "$github_username" ]]; then
            break
        fi
        warn "Username is required."
    done

    # Poll interval
    echo -n "Poll interval in seconds [300]: "
    read -r poll_interval
    poll_interval="${poll_interval:-300}"

    # Repos filter
    echo -n "Filter to specific repos (comma-separated, e.g. owner/repo1,owner/repo2) [all]: "
    read -r repos_input

    # Build repos array
    if [[ -z "$repos_input" ]]; then
        repos_toml="[]"
    else
        repos_toml="["
        first=true
        IFS=',' read -ra repo_list <<< "$repos_input"
        for repo in "${repo_list[@]}"; do
            repo=$(echo "$repo" | xargs) # trim whitespace
            if [[ -n "$repo" ]]; then
                if [[ "$first" == true ]]; then
                    first=false
                else
                    repos_toml+=", "
                fi
                repos_toml+="\"${repo}\""
            fi
        done
        repos_toml+="]"
    fi

    # Write config
    cat > "${CONFIG_FILE}" <<EOF
# GitHub personal access token
# Required scopes: repo (for private repos) or public_repo (public only)
github_token = "${github_token}"

# Your GitHub username
github_username = "${github_username}"

# Polling interval in seconds (default: 300 = 5 minutes)
poll_interval = ${poll_interval}

# Optional: filter to specific repos (owner/name format)
# If empty, monitors all repos where you have review requests
repos = ${repos_toml}
EOF

    chmod 600 "${CONFIG_FILE}"
    ok "Config written to ${CONFIG_FILE} (permissions: 600)"
fi

# --- Step 4: Install systemd service -----------------------------------------

step 4 "Installing systemd user service"

mkdir -p "${SYSTEMD_USER_DIR}"

SERVICE_SRC="${SCRIPT_DIR}/systemd/github-monitor.service"
SERVICE_DST="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"

if [[ ! -f "${SERVICE_SRC}" ]]; then
    err "Service file not found: ${SERVICE_SRC}"
    exit 1
fi

cp "${SERVICE_SRC}" "${SERVICE_DST}"
ok "Service file installed to ${SERVICE_DST}"

info "Reloading systemd user daemon..."
systemctl --user daemon-reload

info "Enabling and starting ${SERVICE_NAME}..."
systemctl --user enable --now "${SERVICE_NAME}"

# Give it a moment to start
sleep 2

# --- Summary ------------------------------------------------------------------

echo
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD} Installation complete!${NC}"
echo -e "${BOLD}============================================${NC}"
echo
echo -e "  Config:  ${CONFIG_FILE}"
echo -e "  Service: ${SERVICE_DST}"
echo -e "  Binary:  $(command -v github-monitor 2>/dev/null || echo "${HOME}/.local/bin/github-monitor")"
echo

info "Service status:"
systemctl --user status "${SERVICE_NAME}" --no-pager --lines=5 || true

echo
info "Useful commands:"
echo "  systemctl --user status github-monitor    # check status"
echo "  systemctl --user reload github-monitor    # reload config (no restart needed)"
echo "  systemctl --user restart github-monitor   # full restart"
echo "  journalctl --user -u github-monitor -f    # follow logs"
echo "  systemctl --user stop github-monitor      # stop the service"
echo "  ./update.sh                               # update to latest version"
echo "  ./uninstall.sh                            # uninstall everything"
