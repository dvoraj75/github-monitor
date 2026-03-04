#!/usr/bin/env bash
#
# update.sh — Update github-monitor to the latest version
#
# This script:
#   1. Checks prerequisites (git, uv, systemctl)
#   2. Pulls the latest code from the remote repository
#   3. Re-installs the github-monitor package via uv tool install
#   4. Updates the systemd service file and restarts the service
#   5. Updates the system tray indicator service (if installed)
#
# Your configuration (~/.config/github-monitor/config.toml) is never touched.
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

TOTAL_STEPS=5

warn "DEPRECATED: This script is deprecated and will be removed in a future release."
warn "            Use 'pip install --upgrade github-monitor' or 'pipx upgrade github-monitor' instead."
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="github-monitor"

# --- Step 1: Check prerequisites --------------------------------------------

step 1 "Checking prerequisites"

errors=0

# Must be in the repo
if [[ ! -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    err "pyproject.toml not found in ${SCRIPT_DIR}"
    err "Please run this script from the github-monitor repository."
    exit 1
fi

# git
if command -v git &>/dev/null; then
    ok "git"
else
    err "git not found"
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

# systemctl (optional — update can still work without it)
if command -v systemctl &>/dev/null; then
    ok "systemctl"
else
    warn "systemctl not found — service restart will be skipped"
fi

if [[ "$errors" -gt 0 ]]; then
    echo
    err "Missing $errors required prerequisite(s). Please install them and re-run this script."
    exit 1
fi

# Check for indicator support (GTK3 + AppIndicator3)
install_indicator=false
if python3 -c "import gi; gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1')" 2>/dev/null; then
    install_indicator=true
fi

# --- Step 2: Pull latest code -----------------------------------------------

step 2 "Pulling latest code"

# Capture current version before pull
old_version=$(grep -Po '(?<=^version = ")[^"]+' "${SCRIPT_DIR}/pyproject.toml" 2>/dev/null || echo "unknown")
info "Current version: ${old_version}"

if ! git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree &>/dev/null; then
    # Not a git repo (e.g. downloaded as zip)
    warn "Not a git repository — skipping git pull."
    info "The package will be re-installed from the current source."
elif [[ -n "$(git -C "${SCRIPT_DIR}" status --porcelain 2>/dev/null)" ]]; then
    # Uncommitted changes — don't touch the tree
    warn "You have uncommitted changes — skipping git pull."
    info "The package will be re-installed from the current source."
    info "Commit or stash your changes and re-run to get the latest version."
else
    # Clean working tree — check which branch we're on
    current_branch=$(git -C "${SCRIPT_DIR}" symbolic-ref --short HEAD 2>/dev/null || echo "")

    do_pull=false

    if [[ -z "$current_branch" ]]; then
        # Detached HEAD
        warn "You are in detached HEAD state — skipping git pull."
        info "Check out a branch and re-run to get the latest version."
    elif [[ "$current_branch" == "main" ]]; then
        do_pull=true
    else
        warn "You are on branch '${current_branch}', not 'main'."
        echo -n "Pull latest changes into '${current_branch}' anyway? [y/N] "
        read -r answer
        if [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]; then
            do_pull=true
        else
            info "Skipping git pull. The package will be re-installed from the current source."
        fi
    fi

    if [[ "$do_pull" == true ]]; then
        info "Running: git pull"
        if git -C "${SCRIPT_DIR}" pull; then
            ok "Repository updated"
        else
            warn "git pull failed — continuing with current source."
            info "You may want to resolve git issues manually and re-run."
        fi
    fi
fi

new_version=$(grep -Po '(?<=^version = ")[^"]+' "${SCRIPT_DIR}/pyproject.toml" 2>/dev/null || echo "unknown")

if [[ "$old_version" != "$new_version" ]]; then
    info "Version: ${old_version} -> ${BOLD}${new_version}${NC}"
else
    info "Version: ${new_version} (unchanged)"
fi

# --- Step 3: Install the updated package ------------------------------------

step 3 "Installing updated package"

info "Running: uv tool install . --force --reinstall"
if [[ "$install_indicator" == true ]]; then
    uv tool install "${SCRIPT_DIR}" --force --reinstall --with "gbulb>=0.6"
else
    uv tool install "${SCRIPT_DIR}" --force --reinstall
fi

# Verify the binary is available
if command -v github-monitor &>/dev/null; then
    ok "github-monitor installed at $(command -v github-monitor)"
elif [[ -x "${HOME}/.local/bin/github-monitor" ]]; then
    ok "github-monitor installed at ${HOME}/.local/bin/github-monitor"
else
    err "github-monitor binary not found after installation"
    exit 1
fi

# --- Step 4: Update systemd service and restart ------------------------------

step 4 "Updating systemd service"

SERVICE_SRC="${SCRIPT_DIR}/systemd/github-monitor.service"
SERVICE_DST="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"

if [[ ! -f "${SERVICE_SRC}" ]]; then
    warn "Service file not found: ${SERVICE_SRC} — skipping service update."
elif ! command -v systemctl &>/dev/null; then
    warn "systemctl not available — skipping service update."
else
    mkdir -p "${SYSTEMD_USER_DIR}"
    cp "${SERVICE_SRC}" "${SERVICE_DST}"
    ok "Service file updated at ${SERVICE_DST}"

    info "Reloading systemd user daemon..."
    systemctl --user daemon-reload

    if systemctl --user is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "Restarting ${SERVICE_NAME}..."
        systemctl --user restart "${SERVICE_NAME}"

        # Give it a moment to start
        sleep 2
        ok "Service restarted"
    else
        info "Service is not enabled — skipping restart."
        info "To enable and start: systemctl --user enable --now ${SERVICE_NAME}"
    fi
fi

# --- Step 5: Update indicator service (if installed) -------------------------

step 5 "Updating system tray indicator"

INDICATOR_SERVICE_NAME="github-monitor-indicator"
INDICATOR_SERVICE_SRC="${SCRIPT_DIR}/systemd/${INDICATOR_SERVICE_NAME}.service"
INDICATOR_SERVICE_DST="${SYSTEMD_USER_DIR}/${INDICATOR_SERVICE_NAME}.service"

if [[ -f "${INDICATOR_SERVICE_DST}" ]]; then
    # Indicator systemd service is currently installed — update it
    if [[ -f "${INDICATOR_SERVICE_SRC}" ]]; then
        cp "${INDICATOR_SERVICE_SRC}" "${INDICATOR_SERVICE_DST}"
        ok "Indicator service file updated at ${INDICATOR_SERVICE_DST}"

        info "Reloading systemd user daemon..."
        systemctl --user daemon-reload

        if systemctl --user is-enabled --quiet "${INDICATOR_SERVICE_NAME}" 2>/dev/null; then
            info "Restarting ${INDICATOR_SERVICE_NAME}..."
            systemctl --user restart "${INDICATOR_SERVICE_NAME}"

            # Give it a moment to start
            sleep 2
            ok "Indicator service restarted"
        else
            info "Indicator service is not enabled — skipping restart."
            info "To enable and start: systemctl --user enable --now ${INDICATOR_SERVICE_NAME}"
        fi
    else
        warn "Service file not found: ${INDICATOR_SERVICE_SRC}"
    fi
elif [[ "$install_indicator" == true ]]; then
    info "Indicator service not currently installed."
    info "To install it, re-run ./install.sh or manually:"
    info "  cp ${INDICATOR_SERVICE_SRC} ${INDICATOR_SERVICE_DST}"
    info "  systemctl --user daemon-reload"
    info "  systemctl --user enable --now ${INDICATOR_SERVICE_NAME}"
else
    info "Indicator not available (missing GTK3/AppIndicator3 system packages)."
fi

# Clean up legacy XDG autostart file (from previous installations)
LEGACY_AUTOSTART="${HOME}/.config/autostart/github-monitor-indicator.desktop"
if [[ -f "${LEGACY_AUTOSTART}" ]]; then
    rm "${LEGACY_AUTOSTART}"
    ok "Removed legacy autostart file: ${LEGACY_AUTOSTART}"
fi

# --- Summary ------------------------------------------------------------------

echo
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD} Update complete!${NC}"
echo -e "${BOLD}============================================${NC}"
echo
echo -e "  Version: ${BOLD}${new_version}${NC}"
echo -e "  Binary:  $(command -v github-monitor 2>/dev/null || echo "${HOME}/.local/bin/github-monitor")"
if [[ -f "${INDICATOR_SERVICE_DST}" ]]; then
    echo -e "  Indicator: ${INDICATOR_SERVICE_DST}"
fi
echo

if command -v systemctl &>/dev/null && systemctl --user is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Service status:"
    systemctl --user status "${SERVICE_NAME}" --no-pager --lines=5 || true
    echo
fi

info "Useful commands:"
echo "  systemctl --user status github-monitor    # check status"
echo "  systemctl --user reload github-monitor    # reload config (no restart needed)"
echo "  journalctl --user -u github-monitor -f    # follow logs"
