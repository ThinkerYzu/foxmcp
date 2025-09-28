#!/bin/bash

# FoxMCP Extension Installer
# Copyright (c) 2024 FoxMCP Project
# Licensed under the MIT License - see LICENSE file for details

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
XPI_FILE="$PROJECT_ROOT/dist/packages/foxmcp@codemud.org.xpi"
EXTENSION_ID="foxmcp@codemud.org"

usage() {
    echo "Usage: $0 <firefox-profile-directory>"
    echo ""
    echo "Install FoxMCP extension to a Firefox profile directory."
    echo ""
    echo "Arguments:"
    echo "  firefox-profile-directory    Path to Firefox profile directory"
    echo "                              (found in about:profiles page)"
    echo ""
    echo "Examples:"
    echo "  $0 ~/.mozilla/firefox/abc123.default-release"
    echo "  $0 /path/to/profile"
    echo ""
    echo "⚠️  IMPORTANT: Firefox must be completely closed before running this script."
    echo "   Profile modifications while Firefox is running may be ignored or cause issues."
    exit 1
}

error() {
    echo "❌ Error: $1" >&2
    exit 1
}

info() {
    echo "ℹ️  $1"
}

success() {
    echo "✅ $1"
}

# Check arguments
if [ $# -ne 1 ]; then
    usage
fi

PROFILE_DIR="$1"

# Validate profile directory
if [ ! -d "$PROFILE_DIR" ]; then
    error "Profile directory does not exist: $PROFILE_DIR"
fi

if [ ! -f "$PROFILE_DIR/prefs.js" ]; then
    error "Invalid Firefox profile directory (prefs.js not found): $PROFILE_DIR"
fi

# Check if XPI file exists
if [ ! -f "$XPI_FILE" ]; then
    error "XPI file not found: $XPI_FILE"
    echo "       Run 'make package' to build the extension first."
fi

# Create extensions directory if it doesn't exist
EXTENSIONS_DIR="$PROFILE_DIR/extensions"
if [ ! -d "$EXTENSIONS_DIR" ]; then
    info "Creating extensions directory: $EXTENSIONS_DIR"
    mkdir -p "$EXTENSIONS_DIR"
fi

# Copy XPI file to extensions directory
DEST_FILE="$EXTENSIONS_DIR/$EXTENSION_ID.xpi"

info "Installing FoxMCP extension..."
info "Source: $XPI_FILE"
info "Target: $DEST_FILE"

# Remove existing extension if present
if [ -f "$DEST_FILE" ]; then
    info "Removing existing extension..."
    rm "$DEST_FILE"
fi

# Copy new extension
cp "$XPI_FILE" "$DEST_FILE"

# Set appropriate permissions
chmod 644 "$DEST_FILE"

# Configure Firefox preferences to allow unsigned extensions
USER_JS="$PROFILE_DIR/user.js"
PREF_LINE='user_pref("xpinstall.signatures.required", false);'

info "Configuring Firefox preferences..."

# Check if user.js exists and if the preference is already set
if [ -f "$USER_JS" ] && grep -q "xpinstall.signatures.required" "$USER_JS"; then
    # Update existing preference
    if grep -q "$PREF_LINE" "$USER_JS"; then
        info "Preference already set correctly in user.js"
    else
        info "Updating existing xpinstall.signatures.required preference..."
        sed -i 's/user_pref("xpinstall.signatures.required".*);/user_pref("xpinstall.signatures.required", false);/' "$USER_JS"
    fi
else
    # Add new preference
    info "Adding xpinstall.signatures.required preference to user.js..."
    echo "$PREF_LINE" >> "$USER_JS"
fi

# Set appropriate permissions for user.js
chmod 644 "$USER_JS"

success "FoxMCP extension installed successfully!"
echo ""
echo "Configuration applied:"
echo "- Extension installed: $DEST_FILE"
echo "- Firefox preferences configured to allow unsigned extensions"
echo ""
echo "Next steps:"
echo "1. Start Firefox with this profile"
echo "2. Go to about:addons to verify the extension is installed"
echo "3. The extension should be automatically enabled"
echo ""
echo "⚠️  Remember: Only start Firefox AFTER this installation is complete."