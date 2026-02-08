#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# Veton Integration Installer
#
# Installs the Veton EV Charger integration on an existing
# Home Assistant instance (HA OS, Container, or Core).
#
# Usage:
#   ssh root@<ha-ip> 'curl -sSL https://your-server/install.sh | bash'
#
# Or from the HA terminal add-on:
#   bash /path/to/install.sh
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

# HA config directory — auto-detect
if [ -d "/config" ]; then
    HA_CONFIG="/config"
elif [ -d "/homeassistant" ]; then
    HA_CONFIG="/homeassistant"
elif [ -d "$HOME/.homeassistant" ]; then
    HA_CONFIG="$HOME/.homeassistant"
else
    echo "Error: Cannot find Home Assistant config directory."
    echo "Expected /config, /homeassistant, or ~/.homeassistant"
    exit 1
fi

DEST="${HA_CONFIG}/custom_components/veton"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${SCRIPT_DIR}/../custom_components/veton"

echo "=== Veton EV Charger Installer ==="
echo "HA config: ${HA_CONFIG}"
echo "Source:    ${SRC}"
echo ""

# Check source exists
if [ ! -d "${SRC}" ]; then
    echo "Error: Integration source not found at ${SRC}"
    echo "Make sure you're running this from the veton-ha/haos-build/ directory."
    exit 1
fi

# Backup existing installation if present
if [ -d "${DEST}" ]; then
    BACKUP="${DEST}.backup.$(date +%Y%m%d%H%M%S)"
    echo "Backing up existing installation to ${BACKUP}..."
    mv "${DEST}" "${BACKUP}"
fi

# Install
echo "Installing Veton integration..."
mkdir -p "$(dirname "${DEST}")"
cp -r "${SRC}" "${DEST}"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Restart Home Assistant"
echo "  2. Go to Settings > Devices & Services > Add Integration"
echo "  3. Search for 'Veton EV Charger'"
echo "  4. Follow the setup wizard"
echo ""
