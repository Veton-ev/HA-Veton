#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# Veton Integration Updater
#
# Updates the Veton integration to the latest version.
# Run this after pulling new code from the repository.
#
# Usage:
#   ./update.sh [ha-config-dir]
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

# HA config directory
HA_CONFIG="${1:-}"
if [ -z "${HA_CONFIG}" ]; then
    if [ -d "/config" ]; then
        HA_CONFIG="/config"
    elif [ -d "/homeassistant" ]; then
        HA_CONFIG="/homeassistant"
    elif [ -d "$HOME/.homeassistant" ]; then
        HA_CONFIG="$HOME/.homeassistant"
    else
        echo "Usage: $0 <ha-config-dir>"
        exit 1
    fi
fi

DEST="${HA_CONFIG}/custom_components/veton"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${SCRIPT_DIR}/../custom_components/veton"

echo "=== Veton Integration Updater ==="

# Read current version
if [ -f "${DEST}/manifest.json" ]; then
    OLD_VER=$(python3 -c "import json; print(json.load(open('${DEST}/manifest.json'))['version'])" 2>/dev/null || echo "unknown")
else
    OLD_VER="not installed"
fi

NEW_VER=$(python3 -c "import json; print(json.load(open('${SRC}/manifest.json'))['version'])" 2>/dev/null || echo "unknown")

echo "Current: ${OLD_VER}"
echo "New:     ${NEW_VER}"
echo ""

if [ "${OLD_VER}" = "${NEW_VER}" ]; then
    echo "Already up to date."
    exit 0
fi

# Backup + update
if [ -d "${DEST}" ]; then
    BACKUP="${DEST}.backup.$(date +%Y%m%d%H%M%S)"
    echo "Backing up to ${BACKUP}..."
    cp -r "${DEST}" "${BACKUP}"
fi

echo "Updating..."
rm -rf "${DEST}"
cp -r "${SRC}" "${DEST}"

echo ""
echo "=== Update complete! ==="
echo "Restart Home Assistant to apply changes."
