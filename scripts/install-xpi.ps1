#requires -Version 5.1
#
# FoxMCP Extension Installer (Windows PowerShell)
# Copyright (c) 2024 FoxMCP Project
# Licensed under the MIT License - see LICENSE file for details
#
# Installs the FoxMCP XPI extension into a Firefox profile directory.
#
# Usage: .\scripts\install-xpi.ps1 <firefox-profile-directory>
#
# The profile directory is found in about:profiles in Firefox.
# Firefox must be completely closed before running this script.
#
# param:
#   ProfileDirectory  Path to Firefox profile directory

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProfileDirectory
)

$ErrorActionPreference = 'Stop'

$EXTENSION_ID = "foxmcp@codemud.org"
$PROJECT_ROOT = (Split-Path -Parent $PSScriptRoot)
$XPI_FILE = Join-Path $PROJECT_ROOT "dist/packages/foxmcp@codemud.org.xpi"

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO]  $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK]    $Message" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Validate arguments
# ---------------------------------------------------------------------------
if (-not (Test-Path -Path $ProfileDirectory -PathType Container)) {
    Write-ErrorMsg "Profile directory does not exist: $ProfileDirectory"
    exit 1
}

if (-not (Test-Path -Path (Join-Path $ProfileDirectory "prefs.js") -PathType Leaf)) {
    Write-ErrorMsg "Invalid Firefox profile directory (prefs.js not found): $ProfileDirectory"
    exit 1
}

# Check if XPI file exists
if (-not (Test-Path -Path $XPI_FILE -PathType Leaf)) {
    Write-ErrorMsg "XPI file not found: $XPI_FILE"
    Write-Host "       Run the package build to create the extension first." -ForegroundColor Yellow
    exit 1
}

# Create extensions directory if it doesn't exist
$extensionsDir = Join-Path $ProfileDirectory "extensions"
if (-not (Test-Path -Path $extensionsDir -PathType Container)) {
    Write-Info "Creating extensions directory: $extensionsDir"
    New-Item -ItemType Directory -Path $extensionsDir -Force | Out-Null
}

# Destination file path
$destFile = Join-Path $extensionsDir "$EXTENSION_ID.xpi"

Write-Info "Installing FoxMCP extension..."
Write-Info "Source: $XPI_FILE"
Write-Info "Target: $destFile"

# Remove existing extension if present
if (Test-Path -Path $destFile -PathType Leaf) {
    Write-Info "Removing existing extension..."
    Remove-Item -Path $destFile -Force
}

# Copy new extension
Copy-Item -Path $XPI_FILE -Destination $destFile -Force

# Configure Firefox preferences to allow unsigned extensions
$userJs = Join-Path $ProfileDirectory "user.js"
$prefLine = 'user_pref("xpinstall.signatures.required", false);'

Write-Info "Configuring Firefox preferences..."

if (Test-Path -Path $userJs -PathType Leaf) {
    $content = Get-Content -Path $userJs -Raw
    if ($content -match 'xpinstall\.signatures\.required') {
        if ($content -match ([RegEx]::Escape($prefLine))) {
            Write-Info "Preference already set correctly in user.js"
        } else {
            Write-Info "Updating existing xpinstall.signatures.required preference..."
            $newContent = $content -replace 'user_pref\("xpinstall\.signatures\.required".*\);', $prefLine
            Set-Content -Path $userJs -Value $newContent -Encoding UTF8
        }
    } else {
        Write-Info "Adding xpinstall.signatures.required preference to user.js..."
        Add-Content -Path $userJs -Value $prefLine -Encoding UTF8
    }
} else {
    Write-Info "Adding xpinstall.signatures.required preference to user.js..."
    Set-Content -Path $userJs -Value $prefLine -Encoding UTF8
}

Write-Success "FoxMCP extension installed successfully!"
Write-Host ""
Write-Info "Configuration applied:"
Write-Host "- Extension installed: $destFile"
Write-Host "- Firefox preferences configured to allow unsigned extensions"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Start Firefox with this profile"
Write-Host "2. Go to about:addons - FoxMCP is listed but DISABLED"
Write-Host "3. Enable it. Firefox requires this for any extension installed into a"
Write-Host "   profile from outside the browser, and nothing here can do it for you."
Write-Host "4. The extension connects to the server as soon as it is enabled"
Write-Host ""
Write-Warning "Remember: Only start Firefox AFTER this installation is complete."
