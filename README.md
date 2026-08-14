# FoxMCP - Firefox Browser Automation via MCP

A Firefox extension that exposes browser functionality to AI assistants and automation tools through the Model Context Protocol (MCP). Control tabs, history, bookmarks, navigation, content, and windows programmatically.

## ⚠️ Privacy Notice

**FoxMCP enables AI access to your browser data.** Use only with trusted AI services and consider using dedicated browser profiles for testing.

## Features

- **Complete Browser Control**: Tabs, windows, navigation, bookmarks, history
- **Web Request Monitoring**: Monitor and analyze HTTP requests with configurable filtering
- **Content Access**: Extract text, HTML, execute JavaScript in pages
- **MCP Integration**: Works with Claude Desktop, Claude Code, and other MCP clients
- **Custom Scripts**: Execute parameterized scripts in browser tabs
- **Real-time Communication**: WebSocket-based with automatic reconnection
- **Security**: Localhost-only operation with comprehensive input validation. Web pages are kept off both ports deliberately; see [SECURITY.md](SECURITY.md) for the threat model

## Quick Start

### Option 1: Install from GitHub Release (Recommended)

```bash
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.2.0/install-from-github.sh | bash
```

This script automatically:
- Downloads the latest v1.2.0 release binaries
- Sets up Python virtual environment and dependencies
- Downloads the Firefox extension and installation script
- Creates CLAUDE.md for Claude Code integration
- Downloads Google Calendar automation scripts to predefined-scripts/ directory
- Optionally connects to Claude Code
- Creates a startup script for easy server management

**Install Firefox Extension:**

After running the installation script, install the FoxMCP extension from Firefox Add-ons:
- Visit: https://addons.mozilla.org/en-US/firefox/addon/foxmcp/
- Click "Add to Firefox"

### Option 2: Install from Source

#### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/ThinkerYzu/foxmcp.git
cd foxmcp

# Create venv/ and install the server dependencies into it
make install
```

Python 3.10 or newer is required — `fastmcp` 3 does not install on anything older.
Development and CI run 3.14, and 3.12 is verified. `make install` creates `venv/` and
installs `server/requirements.txt` into it; use `make setup` instead if you also want
to run the test suite, which adds `tests/requirements.txt`.

You also need `make`, `zip` and Python's `venv` module, none of which a stock Ubuntu
has: `sudo apt install make zip python3-venv`. Without `python3-venv`, `make install`
stops at "The virtual environment was not created successfully"; without `zip`,
`make package` cannot build the XPI.

#### 2. Build & Install Extension

```bash
# Build and package extension
make package
```

**Your Firefox channel decides which methods are available.** Release and Beta
builds enforce extension signing and ignore `xpinstall.signatures.required`, so an
unsigned XPI cannot be installed permanently on them — only Nightly, Developer
Edition and unbranded builds honour that preference, which Methods 2 and 3 depend
on. On Release or Beta, either install the signed copy from
[Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/foxmcp/), or use
Method 1, which loads an unsigned XPI temporarily until Firefox restarts.

**Install in Firefox (Method 1 - Temporary Add-on)**:
1. Open Firefox
2. Go to `about:debugging`
3. Click "This Firefox"
4. Click "Load Temporary Add-on"
5. Select `dist/packages/foxmcp@codemud.org.xpi`

**Install in Firefox (Method 2 - Persistent with Preferences)**:
1. Open Firefox
2. Go to `about:config` (accept the warning)
3. Set `xpinstall.signatures.required` to `false`
4. Set `extensions.experiments.enabled` to `true` (if needed)
5. Go to `about:addons`
6. Click gear icon (⚙️) → "Install Add-on From File"
7. Select `dist/packages/foxmcp@codemud.org.xpi`

**Install in Firefox (Method 3 - Automated Script)**:
```bash
# IMPORTANT: Close Firefox completely first!
# Find your profile directory in about:profiles, then:
./scripts/install-xpi.sh /path/to/firefox/profile
```

This script automatically:
- Installs the extension to your Firefox profile
- Configures Firefox to allow unsigned extensions
- Handles existing installations and preferences

**Then enable it by hand.** Start Firefox, open `about:addons`, and turn FoxMCP on.
Firefox installs an extension dropped into a profile in the disabled state and
requires a person to enable it — no script can do that step, and until you do, the
extension is present, listed, and not running. Methods 1 and 2 install through the
browser, so they do not need it.

**Note**: Method 1 requires reinstalling after Firefox restarts. Method 2 requires manual preference changes. Method 3 is the least manual of the persistent options, on a channel that allows unsigned extensions — but it still needs that one click.

### 3. Start Server

**If you used the GitHub installation script:**
```bash
# Use the provided startup script
./start-foxmcp.sh
```

**If you installed from source:**
```bash
# Start both WebSocket and MCP servers
make run-server

# Or the same thing by hand — note the interpreter, which is the one make uses
venv/bin/python server/server.py
```

Neither needs the virtual environment activated: both name `venv/bin/python`
directly. Activating it first (`source venv/bin/activate`) is fine too.

The server will start on:
- **WebSocket**: `localhost:8765` (for Firefox extension)
- **MCP Server**: `localhost:3000` (for AI clients)

### 4. Connect Your AI Client

**For Claude Code**:
```bash
claude mcp add --transport http foxmcp http://localhost:3000/mcp/
```

**For Other MCP Clients**:
Connect to `http://localhost:3000/mcp/`

## Basic Usage

Once connected, you can control Firefox through natural language:

```
"List all open tabs"
"Create a new tab with example.com"
"Get the text content from the current page"
"Search my browsing history for python tutorials"
"Take a screenshot of the current tab"
"Execute JavaScript: document.title"
```

## Available Functions

### Tab Management
- List, create, close, and switch between tabs
- Take screenshots of tabs (PNG/JPEG)
- Cross-window tab creation
- Reorder tabs, or move them into another window — including gathering the tabs for one
  site into a window of their own

### Content Interaction
- Extract page text and HTML
- Execute JavaScript in pages
- Run custom predefined scripts

### Navigation
- Back, forward, reload pages
- Navigate to specific URLs
- Cache control options

### History & Bookmarks
- Search browsing history
- List and search bookmarks
- Create and delete bookmarks
- Create bookmark folders and organize bookmarks hierarchically
- Update bookmark and folder titles and URLs

### Web Request Monitoring
- Monitor HTTP requests with URL pattern filtering
- Capture response headers and bodies, including the document load
- Text bodies come back as text — JSON and `text/*` by default, configurable per
  monitor. A binary response reports its size, not its bytes
- Start, list, read and stop; several monitors can run at once. Captured data lives
  in the extension for as long as it runs, and nothing is written to disk

### Window Management
- List, create, close, and focus windows
- Resize and position windows
- Window state management (minimize, maximize)

## Configuration

### Server Options

```bash
# Custom ports
python server/server.py --port 9000 --mcp-port 4000

# WebSocket only (no MCP)
python server/server.py --no-mcp

# Bind a different host
python server/server.py --host 127.0.0.1

# Offer fewer tools, to keep them out of the MCP client's context
python server/server.py --disable-tools bookmarks,history
```

All 35 tools are offered by default, costing an MCP client roughly 4,700 tokens of
context. `--disable-tools` leaves a group unregistered: `windows`, `tabs`,
`bookmarks`, `navigation`, `content`, `requests`, `history`, `debug`. See
[docs/configuration.md](docs/configuration.md#reducing-the-tool-surface) for what
each group costs.

### Extension Configuration

Click the FoxMCP extension icon to configure:
- Server connection settings
- Retry intervals and timeouts
- Development/test mode options

## Custom Scripts

Create reusable JavaScript automation with external scripts:

### 1. Setup Script Directory
```bash
export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
```

### 2. Create Executable Script
```bash
#!/bin/bash
# highlight_text.sh - Highlight text on page
search_text="${1:-example}"
echo "(function() {
  // JavaScript to highlight text
  return 'Highlighted: ' + search_text;
})()"
```

### 3. Use via MCP
```
"Run the highlight_text script with 'important' as the search term"
```

### 4. Claude Code Integration
The `claude-ex/` directory contains example CLAUDE.md templates that help Claude Code understand how to create predefined external scripts. Copy `claude-ex/CLAUDE.md.template` to your project's CLAUDE.md to enable Claude Code to:
- Understand your script creation workflow
- Help you create new predefined external scripts
- Provide context about foxmcp tools and capabilities

### 5. Available Predefined Scripts

The `predefined-ex/` directory includes ready-to-use scripts. To use them, point `FOXMCP_EXT_SCRIPTS` to the `predefined-ex/` directory:

```bash
export FOXMCP_EXT_SCRIPTS="/path/to/foxmcp/predefined-ex"
```

**YouTube Control** (`youtube-play-pause.sh`):
- Control YouTube video playback (play, pause, or toggle)
- Returns JSON with video state and playback position
- Usage: `youtube-play-pause.sh [play|pause|toggle]`

**Google Calendar Scripts**:
- `gcal-daily-events-js.sh` - Extract events for a specific day
- `gcal-monthly-events-js.sh` - Extract events for the entire month
- `gcal-cal-event-js.sh` - Extract detailed event information

**DOM Simplification** (`dom-summarize.sh`):
- Simplify complex DOM trees for AI agent understanding
- Shows only visible interactive elements
- Usage: `dom-summarize.sh [onscreen] [withpos]`

See [docs/scripts.md](docs/scripts.md) for detailed documentation on creating and using predefined scripts.

## Documentation

- **[API Reference](docs/api-reference.md)** - Complete function reference
- **[Web Request Monitoring](docs/web-request-monitoring.md)** - HTTP request monitoring and analysis
- **[Configuration](docs/configuration.md)** - Server and extension setup
- **[Custom Scripts](docs/scripts.md)** - Create reusable automation scripts
- **[Development](docs/development.md)** - Development setup and workflow
- **[Architecture](docs/architecture.md)** - System design and components
- **[Protocol](docs/protocol.md)** - WebSocket message format
- **[Security Policy](SECURITY.md)** - Threat model and how to report a vulnerability

## Development

```bash
# Setup development environment
make dev

# Run tests
make test

# Development cycle
make build && make run-server
```

See [Development Guide](docs/development.md) for detailed instructions.

## Security

- **Localhost Only**: Server binds only to localhost interface
- **Input Validation**: All inputs sanitized and validated
- **Script Security**: Predefined scripts use secure path validation
- **Permission Model**: Extension uses minimal required permissions

## Troubleshooting

### Extension Not Connecting
1. Verify the WebSocket server is running: `curl -i http://localhost:8765`.
   A healthy answer is **426 Upgrade Required** — that is the WebSocket server
   turning away a plain HTTP request. Connection refused means it is not running
2. Check extension popup for connection status
3. Review browser console for errors

The server accepts WebSocket connections only from `moz-extension://` origins, so a
handshake from anything but the extension is rejected with 403 and logged.

### MCP Client Issues
1. Check the MCP server: `curl -i http://localhost:3000/mcp/`. A **307** redirect to
   `/mcp` means it is up; **connection refused** means it is not. A bare
   `curl http://localhost:3000` answers 404, which also proves the port is live
2. Verify client configuration matches server ports
3. Run the server in the foreground and watch its log output

### Permission Errors
1. Ensure virtual environment is activated
2. Check file permissions: `chmod +x scripts/*.sh`
3. Verify Firefox extension is properly installed

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Run the test suite: `make test`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**For detailed documentation, configuration options, and advanced usage, see the [docs/](docs/) directory.**