#!/bin/bash

# FoxMCP GitHub Installation Script
# Copyright (c) 2024 FoxMCP Project
# Licensed under the MIT License - see LICENSE file for details

set -e

VERSION="v1.1.0"
GITHUB_REPO="ThinkerYzu/foxmcp"
GITHUB_API_URL="https://api.github.com/repos/$GITHUB_REPO/releases/tags/$VERSION"
GITHUB_RELEASE_URL="https://github.com/$GITHUB_REPO/releases/download/$VERSION"

# Color output functions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

error() {
    echo -e "${RED}❌ Error: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    FoxMCP Installation                      ║"
    echo "║              Firefox Browser Automation via MCP             ║"
    echo "║                        Version $VERSION                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_dependencies() {
    info "Checking system dependencies..."

    # Check for required commands
    for cmd in curl unzip python3; do
        if ! command -v "$cmd" &> /dev/null; then
            error "$cmd is required but not installed. Please install $cmd and try again."
        fi
    done

    # Check Python version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    python_major=$(echo "$python_version" | cut -d. -f1)
    python_minor=$(echo "$python_version" | cut -d. -f2)

    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 8 ]); then
        error "Python 3.8 or higher is required. Found Python $python_version"
    fi

    success "Dependencies check passed (Python $python_version)"
}

download_release() {
    info "Downloading FoxMCP $VERSION from GitHub..."

    # Create downloads directory
    mkdir -p foxmcp-downloads
    cd foxmcp-downloads

    # Download server package
    info "Downloading server package..."
    if ! curl -L -o foxmcp-server.zip "$GITHUB_RELEASE_URL/foxmcp-server.zip"; then
        error "Failed to download server package from $GITHUB_RELEASE_URL/foxmcp-server.zip"
    fi

    # Download Firefox extension
    info "Downloading Firefox extension..."
    if ! curl -L -o "foxmcp@codemud.org.xpi" "$GITHUB_RELEASE_URL/foxmcp@codemud.org.xpi"; then
        error "Failed to download Firefox extension from $GITHUB_RELEASE_URL/foxmcp@codemud.org.xpi"
    fi

    # Download install-xpi.sh script
    info "Downloading extension installation script..."
    if ! curl -L -o install-xpi.sh "https://raw.githubusercontent.com/$GITHUB_REPO/$VERSION/scripts/install-xpi.sh"; then
        error "Failed to download install-xpi.sh script"
    fi
    chmod +x install-xpi.sh

    # Download predefined scripts
    info "Downloading predefined scripts..."
    mkdir -p predefined-scripts-download

    # List of predefined scripts to download
    scripts=("gcal-cal-event-js.sh" "gcal-daily-events-js.sh" "gcal-monthly-events-js.sh" "dom-summarize.sh" "youtube-play-pause.sh")

    for script in "${scripts[@]}"; do
        if curl -L -o "predefined-scripts-download/$script" "https://raw.githubusercontent.com/$GITHUB_REPO/$VERSION/predefined-ex/$script"; then
            chmod +x "predefined-scripts-download/$script"
        else
            warning "Failed to download predefined script: $script (continuing anyway)"
        fi
    done

    success "Downloads completed successfully"
}

extract_and_setup() {
    info "Setting up FoxMCP server..."

    # Extract server package
    if ! unzip -q foxmcp-server.zip; then
        error "Failed to extract server package"
    fi

    # Move server files to parent directory
    cd ..
    mkdir -p server
    cp -r foxmcp-downloads/server-package/* server/

    # Create proper directory structure for install-xpi.sh
    mkdir -p dist/packages
    mkdir -p scripts

    # Move files to expected locations
    cp foxmcp-downloads/"foxmcp@codemud.org.xpi" dist/packages/
    cp foxmcp-downloads/install-xpi.sh scripts/

    # Create predefined scripts directory and move downloaded scripts
    mkdir -p predefined-scripts
    if [ -d foxmcp-downloads/predefined-scripts-download ]; then
        cp foxmcp-downloads/predefined-scripts-download/* predefined-scripts/ 2>/dev/null || true
    fi

    # Clean up downloads directory
    rm -rf foxmcp-downloads

    success "Server files extracted and organized with proper directory structure"
}

setup_python_environment() {
    info "Setting up Python virtual environment..."

    # Create virtual environment
    python3 -m venv venv

    # Activate virtual environment and install dependencies
    source venv/bin/activate

    if [ -f server/requirements.txt ]; then
        info "Installing Python dependencies..."
        pip install -r server/requirements.txt
        success "Python dependencies installed"
    else
        warning "server/requirements.txt not found, skipping dependency installation"
    fi

    deactivate
}

setup_claude_integration() {
    info "Setting up Claude Code integration..."

    # Create CLAUDE.md file
    cat > CLAUDE.md << 'EOF'
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

1. Start the FoxMCP server: `./start-foxmcp.sh`
2. Connect Claude Code: `claude mcp add --transport http foxmcp http://localhost:3000/mcp/`
3. Install and enable the Firefox extension using `./scripts/install-xpi.sh`
4. Begin automating your browser tasks!
EOF

    # Ensure predefined scripts directory exists
    mkdir -p predefined-scripts


    success "Claude Code integration setup complete"
}

create_start_script() {
    info "Creating startup script..."

    cat > start-foxmcp.sh << 'EOF'
#!/bin/bash

# FoxMCP Startup Script
echo "🚀 Starting FoxMCP Server..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run install-from-github.sh first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Set predefined scripts directory
export FOXMCP_EXT_SCRIPTS="$(pwd)/predefined-scripts/"

# Start the server
echo "📡 Starting WebSocket (8765) and MCP (3000) servers..."
echo "📁 Predefined scripts directory: $FOXMCP_EXT_SCRIPTS"
python server/server.py

# Deactivate when done
deactivate
EOF

    chmod +x start-foxmcp.sh
    success "Startup script created: start-foxmcp.sh"
}

setup_claude_code_connection() {
    echo ""
    info "Claude Code MCP Connection Setup"
    echo ""
    echo "Would you like to automatically connect FoxMCP to Claude Code?"
    echo "This will run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    echo ""

    read -p "Connect to Claude Code now? (y/N): " -r < /dev/tty

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Connecting FoxMCP to Claude Code..."

        # Check if claude command exists
        if ! command -v claude &> /dev/null; then
            warning "Claude Code CLI not found. Please install Claude Code first:"
            echo "   • Visit: https://claude.com/claude-code"
            echo "   • After installation, run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
            return
        fi

        # Attempt to connect
        if claude mcp add --transport http foxmcp http://localhost:3000/mcp/; then
            success "FoxMCP successfully connected to Claude Code!"
            echo ""
            echo -e "${GREEN}🎉 You're all set! You can now use FoxMCP in Claude Code.${NC}"
        else
            warning "Failed to connect to Claude Code. You can manually connect later with:"
            echo "   • claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
        fi
    else
        info "Skipping Claude Code connection. You can connect manually later with:"
        echo "   • claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    fi
}

print_installation_guide() {
    echo ""
    echo -e "${GREEN}🎉 FoxMCP Installation Complete!${NC}"
    echo ""
    echo -e "${BLUE}📋 Next Steps:${NC}"
    echo ""
    echo "1. 🔧 Install Firefox Extension:"
    echo "   • Open Firefox and go to about:profiles"
    echo "   • Find your profile directory path"
    echo "   • Close all Firefox windows completely"
    echo "   • Run: ./scripts/install-xpi.sh /path/to/your/firefox/profile"
    echo "   • Restart Firefox"
    echo "   • Go to about:addons and enable the FoxMCP extension (it's disabled by default)"
    echo ""
    echo "2. 🚀 Start FoxMCP Server:"
    echo "   • Run: ./start-foxmcp.sh"
    echo "   • Server will start on ports 8765 (WebSocket) and 3000 (MCP)"
    echo ""
    echo "3. 🤖 Connect Claude Code (if not already connected):"
    echo "   • Run: claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
    echo ""
    echo -e "${BLUE}📁 Files created in current directory:${NC}"
    echo "   • start-foxmcp.sh                - Server startup script"
    echo "   • CLAUDE.md                      - Claude Code integration guide"
    echo "   • server/                        - Server code directory"
    echo "     ├── server.py                  - Main server script"
    echo "     ├── mcp_tools.py               - MCP tool definitions"
    echo "     └── requirements.txt           - Python dependencies"
    echo "   • venv/                          - Python virtual environment"
    echo "   • predefined-scripts/            - Directory for custom browser scripts"
    echo "   • dist/packages/foxmcp@codemud.org.xpi - Firefox extension (proper path)"
    echo "   • scripts/install-xpi.sh         - Extension installation script"
    echo ""
    echo -e "${BLUE}📚 Documentation:${NC}"
    echo "   • GitHub: https://github.com/$GITHUB_REPO"
    echo "   • Issues: https://github.com/$GITHUB_REPO/issues"
    echo ""
    echo -e "${YELLOW}⚠️  Important Notes:${NC}"
    echo "   • Close Firefox completely before installing the extension"
    echo "   • The extension requires unsigned extension support"
    echo "   • Server binds to localhost only for security"
    echo ""
    echo -e "${GREEN}✨ Ready to automate Firefox with AI! ✨${NC}"
}

main() {
    print_header

    # Check if we're in an empty directory or user confirmation
    if [ "$(ls -A . 2>/dev/null)" ]; then
        warning "Current directory is not empty."
        echo "FoxMCP will be installed in the current directory: $(pwd)"

        read -p "Continue? (y/N): " -r < /dev/tty
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Installation cancelled."
            exit 0
        fi
    fi

    info "Installing FoxMCP $VERSION in: $(pwd)"

    check_dependencies
    download_release
    extract_and_setup
    setup_python_environment
    setup_claude_integration
    create_start_script
    setup_claude_code_connection
    print_installation_guide
}

# Handle script interruption
trap 'echo -e "\n${RED}Installation interrupted${NC}"; exit 1' INT

# Run main function
main "$@"