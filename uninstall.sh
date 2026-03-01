#!/usr/bin/env bash
#
# uninstall.sh — Remove github-monitor systemd service and package
#
# This script:
#   1. Stops and disables the systemd user service
#   2. Removes the systemd unit file
#   3. Uninstalls the github-monitor package
#   4. Optionally removes the configuration directory
#

set -euo pipefail

# --- Colors & helpers --------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}::${NC} $*"; }
ok()    { echo -e "${GREEN}OK${NC} $*"; }
warn()  { echo -e "${YELLOW}WARNING${NC} $*"; }
err()   { echo -e "${RED}ERROR${NC} $*" >&2; }
step()  { echo -e "\n${BOLD}[$1/$TOTAL_STEPS] $2${NC}"; }

TOTAL_STEPS=4

CONFIG_DIR="${HOME}/.config/github-monitor"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="github-monitor"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"

echo -e "${BOLD}Uninstalling github-monitor${NC}"
echo

# --- Step 1: Stop and disable the service ------------------------------------

step 1 "Stopping and disabling the systemd service"

if systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Stopping ${SERVICE_NAME}..."
    systemctl --user stop "${SERVICE_NAME}"
    ok "Service stopped"
else
    info "Service is not running."
fi

if systemctl --user is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
    info "Disabling ${SERVICE_NAME}..."
    systemctl --user disable "${SERVICE_NAME}"
    ok "Service disabled"
else
    info "Service is not enabled."
fi

# --- Step 2: Remove the systemd unit file ------------------------------------

step 2 "Removing systemd unit file"

if [[ -f "${SERVICE_FILE}" ]]; then
    rm "${SERVICE_FILE}"
    ok "Removed ${SERVICE_FILE}"
    systemctl --user daemon-reload
    info "Reloaded systemd user daemon."
else
    info "Unit file not found at ${SERVICE_FILE} (already removed)."
fi

# --- Step 3: Uninstall the package -------------------------------------------

step 3 "Uninstalling github-monitor package"

if uv tool list 2>/dev/null | grep -q "${SERVICE_NAME}"; then
    uv tool uninstall "${SERVICE_NAME}"
    ok "Package uninstalled via uv"
elif [[ -x "${HOME}/.local/bin/github-monitor" ]]; then
    rm "${HOME}/.local/bin/github-monitor"
    ok "Removed ${HOME}/.local/bin/github-monitor"
else
    info "Package not found (already uninstalled)."
fi

# --- Step 4: Optionally remove config ----------------------------------------

step 4 "Configuration cleanup"

if [[ -d "${CONFIG_DIR}" ]]; then
    echo -e "${YELLOW}Config directory exists:${NC} ${CONFIG_DIR}"
    echo -n "Remove it? This will delete your config.toml including your token. [y/N] "
    read -r answer
    if [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]; then
        rm -rf "${CONFIG_DIR}"
        ok "Removed ${CONFIG_DIR}"
    else
        info "Keeping ${CONFIG_DIR}"
    fi
else
    info "Config directory not found (already removed)."
fi

# --- Summary ------------------------------------------------------------------

echo
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD} Uninstall complete!${NC}"
echo -e "${BOLD}============================================${NC}"
echo
if [[ -d "${CONFIG_DIR}" ]]; then
    info "Config directory was preserved at ${CONFIG_DIR}"
    info "To remove it manually: rm -rf ${CONFIG_DIR}"
fi
