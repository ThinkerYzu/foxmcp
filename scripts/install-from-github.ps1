#requires -Version 5.1
#
# FoxMCP GitHub Installation Script (Windows PowerShell)
# Copyright (c) 2024 FoxMCP Project
# Licensed under the MIT License - see LICENSE file for details
#
# Mirrors scripts/install-from-github.sh for Windows. Downloads the release
# archives from GitHub, verifies their checksums, sets up a Python virtual
# environment with the server dependencies, and creates a startup script.
#
# Usage: .\scripts\install-from-github.ps1
#        .\scripts\install-from-github.ps1 -NonInteractive

[CmdletBinding()]
param(
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

$script:VERSION = "v1.4.0"
$script:GITHUB_REPO = "ThinkerYzu/foxmcp"
$script:GITHUB_API_URL = "https://api.github.com/repos/$($script:GITHUB_REPO)/releases/tags/$($script:VERSION)"
if ($env:FOXMCP_RELEASE_URL) {
    $script:GITHUB_RELEASE_URL = $env:FOXMCP_RELEASE_URL
} else {
    $script:GITHUB_RELEASE_URL = "https://github.com/$($script:GITHUB_REPO)/releases/download/$($script:VERSION)"
}

if ($env:FOXMCP_SOURCE_URL) {
    $script:GITHUB_SOURCE_URL = $env:FOXMCP_SOURCE_URL
} else {
    $script:GITHUB_SOURCE_URL = "https://raw.githubusercontent.com/$($script:GITHUB_REPO)/$($script:VERSION)"
}

# ---------------------------------------------------------------------------
# Color / output helpers
# ---------------------------------------------------------------------------
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

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN]  $Message" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------
function Check-Dependencies {
    Write-Info "Checking system dependencies..."

    # Python 3
    if (!(Get-Command python -ErrorAction SilentlyContinue)) {
        if (!(Get-Command python3 -ErrorAction SilentlyContinue)) {
            Write-ErrorMsg "python is required but not installed. Please install Python 3.10+ and try again."
            exit 1
        }
        $script:PYTHON_CMD = "python3"
    } else {
        $script:PYTHON_CMD = "python"
    }

    # Check Python version
    $pythonVersionRaw = & $script:PYTHON_CMD --version 2>&1
    $pythonVersion = $pythonVersionRaw -replace '^Python\s+','' -replace '\s+$',''
    $parts = $pythonVersion -split '\.'
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
        Write-ErrorMsg "Python 3.10 or higher is required (fastmcp 3 needs it). Found Python $pythonVersion"
        exit 1
    }

    # Check venv module availability (probe a temp directory)
    $venvProbe = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Path $venvProbe -Force | Out-Null
    try {
        $venvResult = & $script:PYTHON_CMD -m venv $venvProbe 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorMsg "python cannot create virtual environments. On Windows ensure python3-venv equivalent is installed."
            exit 1
        }
    } finally {
        Remove-Item -Path $venvProbe -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Success "Dependencies check passed (Python $pythonVersion)"
}

# ---------------------------------------------------------------------------
# Download release archives
# ---------------------------------------------------------------------------
function Download-Release {
    Write-Info "Downloading FoxMCP $($script:VERSION) from GitHub..."

    $downloadDir = Join-Path (Get-Location) "foxmcp-downloads"
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    Push-Location $downloadDir

    try {
        # Download server package
        Write-Info "Downloading server package..."
        $serverZipUrl = "$($script:GITHUB_RELEASE_URL)/foxmcp-server.zip"
        try {
            Invoke-WebRequest -Uri $serverZipUrl -OutFile "foxmcp-server.zip" -ErrorAction Stop
        } catch {
            Write-ErrorMsg "Failed to download server package from $serverZipUrl"
            exit 1
        }

        # Download Firefox extension
        Write-Info "Downloading Firefox extension..."
        $xpiUrl = "$($script:GITHUB_RELEASE_URL)/foxmcp@codemud.org.xpi"
        try {
            Invoke-WebRequest -Uri $xpiUrl -OutFile "foxmcp@codemud.org.xpi" -ErrorAction Stop
        } catch {
            Write-ErrorMsg "Failed to download Firefox extension from $xpiUrl"
            exit 1
        }

        # Download SHA256SUMS
        Write-Info "Downloading checksums..."
        $sumsUrl = "$($script:GITHUB_RELEASE_URL)/SHA256SUMS"
        try {
            Invoke-WebRequest -Uri $sumsUrl -OutFile "SHA256SUMS" -ErrorAction Stop
        } catch {
            Write-ErrorMsg "Failed to download SHA256SUMS"
            exit 1
        }

        # Verify checksums
        Write-Info "Verifying release archive checksums..."
        $expected = @{ "foxmcp-server.zip" = $null; "foxmcp@codemud.org.xpi" = $null }
        $entries = @{}
        $valid = $true
        foreach ($line in Get-Content SHA256SUMS) {
            if ($line -match '^([0-9a-fA-F]{64})\s+(\*?)(.+)$') {
                $hash = $matches[1]
                $name = $matches[3]
                if ($expected.ContainsKey($name)) {
                    $entries[$name] = $hash
                }
            }
        }

        if ($entries.Count -ne 2) {
            Write-ErrorMsg "Invalid SHA256SUMS: expected exactly both release archives"
            exit 1
        }

        foreach ($name in $expected.Keys) {
            if (-not $entries.ContainsKey($name)) {
                Write-ErrorMsg "Invalid SHA256SUMS: missing entry for $name"
                exit 1
            }
            $actual = Get-FileHash -Path $name -Algorithm SHA256 | Select-Object -ExpandProperty Hash
            if ($actual -ne $entries[$name]) {
                Write-ErrorMsg "Release checksum verification failed for $name"
                exit 1
            }
        }

        Write-Success "Checksums verified"

        # Validate archives
        Write-Info "Validating server archive..."
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop 2>$null
        try {
            [System.IO.Compression.ZipFile]::ExtractToDirectory("$downloadDir/foxmcp-server.zip", "$downloadDir/server-package-test")
        } catch {
            Write-ErrorMsg "Invalid server archive"
            exit 1
        }
        Remove-Item -Path "$downloadDir/server-package-test" -Recurse -Force -ErrorAction SilentlyContinue

        Write-Info "Validating extension archive..."
        try {
            [System.IO.Compression.ZipFile]::ExtractToDirectory("$downloadDir/foxmcp@codemud.org.xpi", "$downloadDir/xpi-test")
        } catch {
            Write-ErrorMsg "Invalid extension archive"
            exit 1
        }
        Remove-Item -Path "$downloadDir/xpi-test" -Recurse -Force -ErrorAction SilentlyContinue

        # Copy install-xpi.ps1 from local scripts directory
        Write-Info "Copying extension installation script..."
        $installXpiSrc = Join-Path $PSScriptRoot "install-xpi.ps1"
        if (-not (Test-Path -Path $installXpiSrc -PathType Leaf)) {
            Write-ErrorMsg "install-xpi.ps1 not found at $installXpiSrc"
            exit 1
        }
        Copy-Item -Path $installXpiSrc -Destination "install-xpi.ps1" -Force
        Write-Success "Copied install-xpi.ps1"

        # Download predefined scripts
        Write-Info "Downloading predefined scripts..."
        $predefinedDir = Join-Path $downloadDir "predefined-scripts-download"
        New-Item -ItemType Directory -Path $predefinedDir -Force | Out-Null

        $scripts = @(
            "gcal-cal-event-js.sh",
            "gcal-daily-events-js.sh",
            "gcal-monthly-events-js.sh",
            "dom-summarize.sh",
            "youtube-play-pause.sh",
            "set-file-input.py"
        )

        foreach ($scriptName in $scripts) {
            $scriptUrl = "$($script:GITHUB_SOURCE_URL)/predefined-ex/$scriptName"
            try {
                Invoke-WebRequest -Uri $scriptUrl -OutFile (Join-Path $predefinedDir $scriptName) -ErrorAction Stop
                Write-Success "Downloaded $scriptName"
            } catch {
                Write-Warning "Failed to download predefined script: $scriptName (continuing anyway)"
            }
        }

        Write-Success "Downloads completed successfully"
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Extract and organize files
# ---------------------------------------------------------------------------
function Extract-And-Setup {
    Write-Info "Setting up FoxMCP server..."

    $downloadDir = Join-Path (Get-Location) "foxmcp-downloads"

    # Extract server package
    $serverExtract = Join-Path $downloadDir "server-package"
    New-Item -ItemType Directory -Path $serverExtract -Force | Out-Null
    Expand-Archive -Path (Join-Path $downloadDir "foxmcp-server.zip") -DestinationPath $serverExtract -Force -ErrorAction SilentlyContinue

    # Move server files to parent directory
    New-Item -ItemType Directory -Path "server" -Force | Out-Null
    Copy-Item -Path (Join-Path $serverExtract "*") -Destination "server/" -Recurse -Force

    # Create proper directory structure
    New-Item -ItemType Directory -Path "dist/packages" -Force | Out-Null
    New-Item -ItemType Directory -Path "scripts" -Force | Out-Null

    # Move files to expected locations
    Copy-Item -Path (Join-Path $downloadDir "foxmcp@codemud.org.xpi") -Destination "dist/packages/" -Force
    Copy-Item -Path (Join-Path $downloadDir "install-xpi.ps1") -Destination "scripts/" -Force

    # Create predefined scripts directory and move downloaded scripts
    New-Item -ItemType Directory -Path "predefined-scripts" -Force | Out-Null
    $predefinedDir = Join-Path $downloadDir "predefined-scripts-download"
    if (Test-Path $predefinedDir) {
        Copy-Item -Path (Join-Path $predefinedDir "*") -Destination "predefined-scripts/" -Force -ErrorAction SilentlyContinue
    }

    # Clean up downloads directory
    Remove-Item -Path $downloadDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Success "Server files extracted and organized with proper directory structure"
}

# ---------------------------------------------------------------------------
# Set up Python virtual environment
# ---------------------------------------------------------------------------
function Setup-PythonEnvironment {
    Write-Info "Setting up Python virtual environment..."

    # Create virtual environment
    & $script:PYTHON_CMD -m venv venv

    # Activate virtual environment and install dependencies
    $venvPython = Join-Path (Get-Location) "venv\Scripts\python.exe"

    if (Test-Path "server/requirements.txt") {
        Write-Info "Installing Python dependencies..."
        & $venvPython -m pip install -r server/requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorMsg "Failed to install Python dependencies"
            exit 1
        }
        Write-Success "Python dependencies installed"
    } else {
        Write-Warning "server/requirements.txt not found, skipping dependency installation"
    }
}

# ---------------------------------------------------------------------------
# Set up Claude Code integration (CLAUDE.md)
# ---------------------------------------------------------------------------
function Setup-ClaudeIntegration {
    Write-Info "Setting up Claude Code integration..."

    $claudeMd = @'
This project provides Firefox browser automation via MCP (Model Context Protocol).

## Me

Add your personal information and work context here.

## Tools
- foxmcp: provides access to Firefox browser automation. Browser automation tools
  (tabs management, navigation, content scripts) can be used freely without
  explicit permission for work-related tasks.

## Foxmcp Predefined External Scripts
A predefined external script is defined at the server side of foxmcp.
To call a script, use `content_execute_predefined(tab_id, "script_name", "[\"arg1\", \"arg2\"]")`.
The last argument is a stringified JSON array of strings.

### Available Predefined Scripts

**dom-summarize.sh** - Simplify DOM tree for AI agent understanding
- Usage: `content_execute_predefined(tab_id, "dom-summarize.sh", "[]")` (all visible elements)
- Usage: `content_execute_predefined(tab_id, "dom-summarize.sh", "[\"onscreen\"]")` (viewport only)
- Usage: `content_execute_predefined(tab_id, "dom-summarize.sh", "[\"onscreen\", \"withpos\"]")` (with positions)
- Returns: Hierarchical structure of visible interactive elements (input, textarea, select, button, a, option)
- Features: Assigns persistent dsid attributes for element reference, flattens non-interesting containers
- Use case: Helps AI agents understand page components without parsing full HTML

**youtube-play-pause.sh** - Control YouTube video playback
- Usage: `content_execute_predefined(tab_id, "youtube-play-pause.sh", "[]")` (toggle play/pause)
- Usage: `content_execute_predefined(tab_id, "youtube-play-pause.sh", "[\"play\"]")` (play video)
- Usage: `content_execute_predefined(tab_id, "youtube-play-pause.sh", "[\"pause\"]")` (pause video)
- Returns: JSON with success status, action taken, video state, current time, and duration
- Use case: Control YouTube playback without user interaction
- Note: Must be used on a YouTube video page

### Available Google Calendar Scripts

**gcal-cal-event-js.sh** - Extract specific event details
- Usage: `content_execute_predefined(tab_id, "gcal-cal-event-js.sh", "[\"Event Title\", \"8\", \"11:30am\"]")`
- Arguments: [event_title, day_of_month, time]
- Example: `content_execute_predefined(tab_id, "gcal-cal-event-js.sh", "[\"Team Lunch\", \"15\", \"12:00pm\"]")`
- Returns: Detailed event information including attendees, meeting links, and location

**gcal-daily-events-js.sh** - Get all events for a specific day
- Usage: `content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"8\"]")` (current month/year)
- Usage: `content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"15\", \"10\"]")` (October 15, current year)
- Usage: `content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"25\", \"12\", \"2024\"]")` (December 25, 2024)
- Arguments: [day] or [day, month] or [day, month, year]
- Returns: All events for the specified day with chronological sorting

**gcal-monthly-events-js.sh** - Extract entire month view
- Usage: `content_execute_predefined(tab_id, "gcal-monthly-events-js.sh", "[]")` (no arguments)
- Returns: All events grouped by day for current month view with summary statistics

### Important Notes for Claude Code:
1. **Always use Google Calendar tab**: Make sure the active tab is on calendar.google.com
2. **Ensure month view**: For monthly scripts, make sure calendar is in month view
3. **Check calendar is loaded**: Wait for calendar to fully load before running scripts
4. **Handle errors gracefully**: Scripts return error messages if calendar elements aren't found
5. **Arguments are strings**: All arguments must be passed as strings in the JSON array

### Common Usage Patterns:
```javascript
// Get today's events (assuming today is the 15th)
content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"15\"]")

// Get specific meeting details
content_execute_predefined(tab_id, "gcal-cal-event-js.sh", "[\"Weekly Standup\", \"16\", \"9:00am\"]")

// Get full month overview
content_execute_predefined(tab_id, "gcal-monthly-events-js.sh", "[]")
```

Add your custom predefined scripts to the predefined-scripts/ directory.

## Browser Content Scripts

When injecting JavaScript content scripts into browser tabs, always wrap the code in an anonymous function to avoid namespace pollution:

```javascript
(function() {
  // Your script code here
  const elements = document.querySelectorAll('*');
  // ... rest of script
})();
```

This prevents variable declarations from polluting the global namespace and avoids conflicts with existing page scripts.

## Browser Automation

All browser automation tools via foxmcp can be used autonomously for work-related tasks without explicit permission:
- Tab management (create, switch, close)
- Navigation (URLs, back/forward, reload)
- Content extraction (text, HTML)
- Script execution for automation
  - There are predefined external scripts in predefined-scripts/
- History and bookmark access
- Element interaction and form submission
- Window management (create, close, focus, list)

Use these tools proactively to help with workflow management and information retrieval.

## Getting Started

1. Start the FoxMCP server: `.\start-foxmcp.ps1`
2. Connect Claude Code: `claude mcp add --transport http foxmcp http://localhost:3000/mcp/`
3. Install and enable the Firefox extension using `.\scripts\install-xpi.ps1`
4. Begin automating your browser tasks!
'@

    Set-Content -Path "CLAUDE.md" -Value $claudeMd -Encoding UTF8

    # Ensure predefined scripts directory exists
    New-Item -ItemType Directory -Path "predefined-scripts" -Force | Out-Null

    Write-Success "Claude Code integration setup complete"
}

# ---------------------------------------------------------------------------
# Create the startup script (start-foxmcp.ps1)
# ---------------------------------------------------------------------------
function Create-StartScript {
    Write-Info "Creating startup script..."

    $startScript = @'
#requires -Version 5.1

# FoxMCP Startup Script
Write-Host "Starting FoxMCP Server..." -ForegroundColor Cyan

# Check if virtual environment exists
$venvDir = Join-Path $PSScriptRoot "venv"
if (!(Test-Path $venvDir)) {
    Write-Host "[ERROR] Virtual environment not found. Run install-from-github.ps1 first." -ForegroundColor Red
    exit 1
}

# Activate virtual environment
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
& $activateScript

# Set predefined scripts directory
$env:FOXMCP_EXT_SCRIPTS = Join-Path $PSScriptRoot "predefined-scripts"

Write-Host "Starting WebSocket (8765) and MCP (3000) servers..." -ForegroundColor Cyan
Write-Host ("Predefined scripts directory: " + $env:FOXMCP_EXT_SCRIPTS) -ForegroundColor Cyan
python (Join-Path $PSScriptRoot "..\server\server.py")

# Deactivate when done
deactivate
'@

    Set-Content -Path "start-foxmcp.ps1" -Value $startScript -Encoding UTF8

    Write-Success "Startup script created: start-foxmcp.ps1"
}

# ---------------------------------------------------------------------------
# Set up Claude Code connection (optional, interactive)
# ---------------------------------------------------------------------------
function Setup-ClaudeCodeConnection {
    if ($NonInteractive) {
        Write-Info "Skipping optional Claude Code connection in non-interactive mode"
        return
    }

    Write-Host ""
    Write-Info "Claude Code MCP Connection Setup"
    Write-Host ""
    Write-Host "Would you like to automatically connect FoxMCP to Claude Code?"
    Write-Host "This will run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    Write-Host ""

    $reply = Read-Host "Connect to Claude Code now? (y/N)"

    if ($reply -match '^[Yy]$') {
        Write-Info "Connecting FoxMCP to Claude Code..."

        if (!(Get-Command claude -ErrorAction SilentlyContinue)) {
            Write-Warning "Claude Code CLI not found. Please install Claude Code first:"
            Write-Host "   * Visit: https://claude.com/claude-code"
            Write-Host "   * After installation, run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
            return
        }

        try {
            & claude mcp add --transport http foxmcp http://localhost:3000/mcp/
            Write-Host "[OK] FoxMCP successfully connected to Claude Code!"
            Write-Host ""
            Write-Host "You're all set! You can now use FoxMCP in Claude Code." -ForegroundColor Green
        } catch {
            Write-Warning "Failed to connect to Claude Code. You can manually connect later with:"
            Write-Host "   * claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
        }
    } else {
        Write-Info "Skipping Claude Code connection. You can connect manually later with:"
        Write-Host "   * claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    }
}

# ---------------------------------------------------------------------------
# Print installation guide
# ---------------------------------------------------------------------------
function Print-InstallationGuide {
    Write-Host ""
    Write-Host "[OK] FoxMCP Installation Complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "[INFO] Next Steps:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. [INSTALL] Install Firefox Extension:"
    Write-Host "   * Open Firefox and go to about:profiles"
    Write-Host "   * Find your profile directory path"
    Write-Host "   * Close all Firefox windows completely"
    Write-Host "   * Run: .\scripts\install-xpi.ps1 /path/to/your/firefox/profile"
    Write-Host "   * Restart Firefox"
    Write-Host "   * Go to about:addons and enable the FoxMCP extension (it's disabled by default)"
    Write-Host ""
    Write-Host "2. [START] Start FoxMCP Server:"
    Write-Host "   * Run: .\start-foxmcp.ps1"
    Write-Host "   * Server will start on ports 8765 (WebSocket) and 3000 (MCP)"
    Write-Host ""
    Write-Host "3. [CONNECT] Connect Claude Code (if not already connected):"
    Write-Host "   * Run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    Write-Host ""
    Write-Host "[INFO] Files created in current directory:" -ForegroundColor Cyan
    Write-Host "   * start-foxmcp.ps1                - Server startup script"
    Write-Host "   * CLAUDE.md                      - Claude Code integration guide"
    Write-Host "   * server/                        - Server code directory"
    Write-Host "     |-- server.py                   - Main server script"
    Write-Host "     |-- mcp_tools.py                - MCP tool definitions"
    Write-Host "     |-- requirements.txt            - Python dependencies"
    Write-Host "   * venv/                          - Python virtual environment"
    Write-Host "   * predefined-scripts/            - Directory for custom browser scripts"
    Write-Host "   * dist/packages/foxmcp@codemud.org.xpi - Firefox extension"
    Write-Host "   * scripts/install-xpi.ps1         - Extension installation script"
    Write-Host ""
    Write-Host "[INFO] Documentation:" -ForegroundColor Cyan
    Write-Host "   * GitHub: https://github.com/$($script:GITHUB_REPO)"
    Write-Host "   * Issues: https://github.com/$($script:GITHUB_REPO)/issues"
    Write-Host ""
    Write-Warning "IMPORTANT NOTES:"
    Write-Host "   * Close Firefox completely before installing the extension"
    Write-Host "   * The extension requires unsigned extension support"
    Write-Host "   * Server binds to localhost only for security"
    Write-Host ""
    Write-Host "[OK] Ready to automate Firefox with AI! [OK]" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
function Main {
    # Check if we're in an empty directory or user confirmation
    $items = Get-ChildItem -Path (Get-Location) -Force -ErrorAction SilentlyContinue
    if ($items) {
        Write-Warning "Current directory is not empty."
        Write-Host "FoxMCP will be installed in the current directory: $(Get-Location)"

        if ($NonInteractive) {
            Write-ErrorMsg "Non-interactive installation requires an empty directory"
            exit 1
        }

        $reply = Read-Host "Continue? (y/N)"
        if ($reply -notmatch '^[Yy]$') {
            Write-Host "Installation cancelled."
            exit 0
        }
    }

    Write-Info "Installing FoxMCP $($script:VERSION) in: $(Get-Location)"

    Check-Dependencies
    Download-Release
    Extract-And-Setup
    Setup-PythonEnvironment
    Setup-ClaudeIntegration
    Create-StartScript
    Setup-ClaudeCodeConnection
    Print-InstallationGuide
}

# Handle script interruption (Ctrl+C)
$host.UI.RawUI.FlushInputBuffer()
try {
    Main
} catch {
    Write-Host "`n[ERROR] Installation interrupted" -ForegroundColor Red
    exit 1
}
