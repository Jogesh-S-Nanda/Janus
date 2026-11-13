#!/usr/bin/env bash
# =============================================================================
# usb_access.sh
# =============================================================================
# Description : Automates USB access setup for the FT232 Serial (UART) IC.
#               Performs the following steps:
#                 1. Detects the FT232 device via lsusb
#                 2. Writes a udev rule granting non-root read/write access
#                 3. Reloads udev so the rule takes effect immediately
#                 4. Adds the current user to the 'dialout' group
#                 5. Creates a sudoers exception so Python scripts can be run
#                    with sudo without requiring a password
#
# Usage       : bash usb_access.sh
#               (must be run as a user with sudo privileges)
#
# Requirements: lsusb, udevadm, usermod, visudo, python3
#
# Author      : nanda
# Version     : 1.0.0
# Date        : 2026-04-01
# =============================================================================
#
# Copyright 2026 nanda
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# =============================================================================

set -e  # Exit immediately if any command returns a non-zero status

# -----------------------------------------------------------------------------
# Configuration
# USB vendor and product IDs for the FT232 Serial (UART) IC
# (Future Technology Devices International, Ltd — ID 0403:6001)
# -----------------------------------------------------------------------------
VENDOR_ID="0403"
PRODUCT_ID="6001"

# Path to the udev rules file that grants non-root USB access
UDEV_RULE_FILE="/etc/udev/rules.d/99-usb-permissions.rules"

# The udev rule itself:
#   SUBSYSTEM=="usb"       — target USB devices only
#   ATTRS{idVendor}        — match by USB vendor ID
#   ATTRS{idProduct}       — match by USB product ID
#   MODE="0666"            — grant read/write to all users
#   GROUP="dialout"        — assign device to the dialout group
#   TAG+="uaccess"         — grant access to the currently logged-in desktop user
#                            without requiring a group membership re-login
#
# Note: udev matches USB devices via SUBSYSTEM=="usb" but serial port nodes
# (/dev/ttyUSBx) appear under SUBSYSTEM=="tty". Both rules are written so
# that permissions apply both to the raw USB endpoint and the tty node.
UDEV_RULE_USB="SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"${VENDOR_ID}\", ATTRS{idProduct}==\"${PRODUCT_ID}\", MODE=\"0666\", GROUP=\"dialout\", TAG+=\"uaccess\""
UDEV_RULE_TTY="SUBSYSTEM==\"tty\", ATTRS{idVendor}==\"${VENDOR_ID}\", ATTRS{idProduct}==\"${PRODUCT_ID}\", MODE=\"0666\", GROUP=\"dialout\", TAG+=\"uaccess\""

# Path to the drop-in sudoers file for the Python passwordless sudo exception
SUDOERS_FILE="/etc/sudoers.d/python-usb"

# -----------------------------------------------------------------------------
# Step 1: Locate the FT232 device
# Use lsusb to check whether the FT232 is currently connected. The script
# continues even if the device is absent so the udev rule is still installed.
# -----------------------------------------------------------------------------
echo "=== Searching for FT232 Serial (UART) device ==="

# grep returns non-zero if no match; '|| true' prevents set -e from aborting
LSUSB_LINE=$(lsusb | grep -i "${VENDOR_ID}:${PRODUCT_ID}" || true)

if [ -z "$LSUSB_LINE" ]; then
    echo "[WARNING] FT232 device (${VENDOR_ID}:${PRODUCT_ID}) not detected via lsusb."
    echo "          Make sure the device is plugged in. Continuing with setup anyway..."
else
    echo "[FOUND]   $LSUSB_LINE"
fi

# Identify the /dev/ttyUSB* character device node already mapped by the kernel.
# 'sort | head -n 1' selects the lowest-numbered node when multiple are present.
DEV_NODE=$(find /dev -maxdepth 1 -name "ttyUSB*" 2>/dev/null | sort | head -n 1 || true)
if [ -n "$DEV_NODE" ]; then
    echo "[INFO]    Device node: $DEV_NODE"
else
    echo "[INFO]    No /dev/ttyUSB* node found yet (will appear after udev reload)."
fi

# -----------------------------------------------------------------------------
# Step 2: Create / update the udev rule
# tee writes to the privileged path; stdout is suppressed with > /dev/null.
# Re-running this script safely overwrites any previous version of the rule.
# -----------------------------------------------------------------------------
echo ""
echo "=== Configuring udev rule: ${UDEV_RULE_FILE} ==="

printf '%s\n%s\n' "$UDEV_RULE_USB" "$UDEV_RULE_TTY" | sudo tee "$UDEV_RULE_FILE" > /dev/null
echo "[OK]      udev rule written (USB endpoint + tty node)."

# -----------------------------------------------------------------------------
# Step 3: Reload udev rules
# '--reload-rules' picks up the new file; 'trigger' re-evaluates already
# connected devices so the new permissions apply without unplugging.
# -----------------------------------------------------------------------------
echo ""
echo "=== Reloading udev rules ==="
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "[OK]      udev rules reloaded."

# -----------------------------------------------------------------------------
# Step 4: Add the current user to the 'dialout' group
# The dialout group owns serial/USB-serial device nodes on most Linux distros.
# The change takes effect at next login (newgrp or re-login required).
# -----------------------------------------------------------------------------
echo ""
echo "=== Adding ${USER} to the 'dialout' group ==="
sudo usermod -a -G dialout "$USER"
echo "[OK]      User added. (Re-login required for group change to take effect.)"

# -----------------------------------------------------------------------------
# Step 5: Sudoers exception for passwordless Python USB access
# Resolves the absolute path of python3 (falling back to python) so the
# NOPASSWD rule is tied to a specific binary, not a shell alias.
# visudo -c validates the file syntax before it is left in place — an invalid
# sudoers drop-in can lock out all sudo access, so this check is critical.
# -----------------------------------------------------------------------------
echo ""
echo "=== Adding sudoers exception for running Python without password ==="

# Resolve the real path of the Python interpreter
PYTHON_BIN=$(which python3 || which python)

# Format: <user> ALL=(ALL) NOPASSWD: <binary>
SUDOERS_LINE="${USER} ALL=(ALL) NOPASSWD: ${PYTHON_BIN}"

echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"  # sudoers files must not be world-writable

# Validate syntax — remove the file and abort if visudo reports an error
if sudo visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "[OK]      Sudoers rule written: ${SUDOERS_FILE}"
    echo "          You can now run:  sudo python3 your_script.py"
else
    echo "[ERROR]   visudo check failed — removing invalid sudoers file."
    sudo rm -f "$SUDOERS_FILE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Done — print a summary of everything that was configured
# -----------------------------------------------------------------------------
echo ""
echo "=== Setup complete ==="
echo "  udev rule : ${UDEV_RULE_FILE}"
echo "  sudoers   : ${SUDOERS_FILE}"
echo "  dialout   : ${USER} (re-login to activate group membership)"
if [ -n "$DEV_NODE" ]; then
    echo "  device    : ${DEV_NODE}"
fi