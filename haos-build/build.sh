#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# Veton HA OS Image Builder
#
# Builds a custom Home Assistant OS image for Raspberry Pi with
# the Veton EV Charger integration pre-installed.
#
# Prerequisites:
#   - Docker (for building HA OS)
#   - git
#   - ~10 GB free disk space
#
# Usage:
#   ./build.sh [rpi4|rpi3|rpi5]
#
# Output:
#   ./output/haos_veton-<board>-<version>.img.xz
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

BOARD="${1:-rpi4}"
HAOS_VERSION="14.2"  # Pin to a known-good HA OS version
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"
WORK_DIR="${SCRIPT_DIR}/.work"

echo "=== Veton HA OS Image Builder ==="
echo "Board:   ${BOARD}"
echo "HA OS:   ${HAOS_VERSION}"
echo ""

# ── Step 1: Clone HA OS if not present ───────────────────────────
if [ ! -d "${WORK_DIR}/operating-system" ]; then
    echo "[1/5] Cloning Home Assistant OS..."
    mkdir -p "${WORK_DIR}"
    git clone --depth 1 --branch "${HAOS_VERSION}" \
        https://github.com/home-assistant/operating-system.git \
        "${WORK_DIR}/operating-system"
else
    echo "[1/5] HA OS source already present."
fi

# ── Step 2: Prepare rootfs overlay ───────────────────────────────
echo "[2/5] Preparing rootfs overlay with Veton integration..."
OVERLAY_DIR="${WORK_DIR}/overlay"
VETON_DEST="${OVERLAY_DIR}/root/custom_components/veton"

rm -rf "${OVERLAY_DIR}"
mkdir -p "${VETON_DEST}"

# Copy the integration files
cp -r "${SCRIPT_DIR}/../custom_components/veton/"* "${VETON_DEST}/"

# Create a first-boot script that copies the integration into HA config
mkdir -p "${OVERLAY_DIR}/etc/cont-init.d"
cat > "${OVERLAY_DIR}/etc/cont-init.d/veton-install.sh" << 'FIRSTBOOT'
#!/bin/bash
# Veton first-boot installer — copies the custom integration into HA config
DEST="/config/custom_components/veton"
SRC="/root/custom_components/veton"

if [ -d "$SRC" ] && [ ! -d "$DEST" ]; then
    echo "[Veton] Installing custom integration..."
    mkdir -p "$(dirname "$DEST")"
    cp -r "$SRC" "$DEST"
    echo "[Veton] Integration installed. Will be available after HA restart."
fi
FIRSTBOOT
chmod +x "${OVERLAY_DIR}/etc/cont-init.d/veton-install.sh"

echo "   Integration files copied to overlay."

# ── Step 3: Create HA config defaults ────────────────────────────
echo "[3/5] Creating default HA configuration..."
HA_CONFIG_DIR="${OVERLAY_DIR}/root/ha-defaults"
mkdir -p "${HA_CONFIG_DIR}"

# Default configuration.yaml with Veton branding
cat > "${HA_CONFIG_DIR}/configuration.yaml" << 'HACONFIG'
# Veton EV Charger — Home Assistant Configuration
# This file is auto-generated. Modify with care.

homeassistant:
  name: "Veton EV Charger"
  unit_system: metric
  currency: EUR
  country: BE
  time_zone: Europe/Brussels

# Core integrations
default_config:

# Energy dashboard
energy:

# Veton EV Charger — auto-triggers setup wizard on first boot
veton_setup:

# Logging — set to warning for production
logger:
  default: warning
  logs:
    custom_components.veton: info
HACONFIG

# Branding: custom instance name
cat > "${HA_CONFIG_DIR}/customize.yaml" << 'CUSTOMIZE'
# Veton branded customizations
CUSTOMIZE

echo "   Default HA config created."

# ── Step 4: Build the image ──────────────────────────────────────
echo "[4/5] Building HA OS image for ${BOARD}..."
echo ""
echo "   This can take 30-60 minutes on first build."
echo "   Subsequent builds use Docker cache and are faster."
echo ""

cd "${WORK_DIR}/operating-system"

# Inject our overlay into the build
# HA OS uses Buildroot — we add files via BR2_ROOTFS_OVERLAY
export BR2_ROOTFS_OVERLAY="${OVERLAY_DIR}"

# Build for the target board
sudo docker run --rm --privileged \
    -v "${PWD}:/build" \
    -v "${OVERLAY_DIR}:/overlay:ro" \
    -e BOARD_ID="${BOARD}" \
    homeassistant/amd64-builder:latest \
    --target /build \
    --board "${BOARD}" \
    || {
        echo ""
        echo "=========================================="
        echo "Docker build failed."
        echo ""
        echo "Alternative: Build manually with the HA OS"
        echo "builder. See instructions in README."
        echo "=========================================="
        echo ""
        echo "For a simpler approach, use the manual"
        echo "installation method instead (see below)."
        exit 1
    }

# ── Step 5: Collect output ───────────────────────────────────────
echo "[5/5] Collecting build output..."
mkdir -p "${OUTPUT_DIR}"

# Find and copy the built image
IMG_FILE=$(find "${WORK_DIR}/operating-system/release" -name "*.img.xz" | head -1)
if [ -n "${IMG_FILE}" ]; then
    cp "${IMG_FILE}" "${OUTPUT_DIR}/haos_veton-${BOARD}-${HAOS_VERSION}.img.xz"
    echo ""
    echo "=== Build complete! ==="
    echo "Image: ${OUTPUT_DIR}/haos_veton-${BOARD}-${HAOS_VERSION}.img.xz"
    echo ""
    echo "Flash to SD card with:"
    echo "  balena-etcher ${OUTPUT_DIR}/haos_veton-${BOARD}-${HAOS_VERSION}.img.xz"
    echo ""
else
    echo ""
    echo "Build completed but image not found in expected location."
    echo "Check ${WORK_DIR}/operating-system/release/ for output files."
fi
