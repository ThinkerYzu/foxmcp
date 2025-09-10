# FoxMCP - Firefox Extension MCP Integration

A Firefox extension that exposes browser functionality (history, tabs, bookmarks, navigation, content, windows) to MCP (Model Context Protocol) clients via WebSocket communication. Features FastMCP server integration for seamless MCP tool access.

## Quick Start

```bash
# Install dependencies and build
make setup
make build

# Start the server
make run-server

# In another terminal, run tests
make test

# Run integration tests (includes Firefox extension testing)
make test-integration

# Load extension in browser
make load-extension
```

## Project Structure

```
foxmcp/
├── extension/          # Firefox extension (WebExtensions API)
├── server/            # Python WebSocket server
├── tests/             # Unit and integration tests
├── Makefile          # Build and development commands
└── docs/             # Documentation files
```

## Development Workflow

### 1. Setup Development Environment

```bash
make dev              # Install all dependencies
```

### 2. Build Extension

```bash
make build           # Build extension package in dist/
```

### 3. Load Extension in Browser

**Firefox:**
1. Go to `about:debugging`
2. Click "This Firefox"
3. Click "Load Temporary Add-on"
4. Select `extension/manifest.json`

### 4. Start Server

```bash
make run-server      # Start WebSocket server on localhost:8765
```

### 5. Test Communication

- Click the extension icon in browser toolbar
- Check connection status indicator
- Status shows "Connected" when extension communicates with server

### 6. Run Tests

```bash
make test           # Run all tests with coverage
make test-unit      # Unit tests only
make test-integration # Integration tests only
```

## Available Browser Functions

### History Management
- `history.query` - Search browser history
- `history.get_recent` - Get recent history items
- `history.delete_item` - Remove specific history entry
- `history.clear_range` - Clear history for time range

### Tab Management
- `tabs.list` - Get all open tabs
- `tabs.get_active` - Get currently active tab
- `tabs.create` - Open new tab
- `tabs.close` - Close specific tab
- `tabs.switch` - Switch to specific tab
- `tabs.duplicate` - Duplicate existing tab

### Content Access
- `content.get_text` - Extract page text content
- `content.get_html` - Get page HTML
- `content.get_title` - Get page title
- `content.get_url` - Get current URL
- `content.execute_script` - Run script on page

### Navigation Control
- `navigation.back` - Go back in history
- `navigation.forward` - Go forward in history
- `navigation.reload` - Reload current page
- `navigation.go_to_url` - Navigate to specific URL

### Window Management
- `windows.list` - Get all browser windows
- `windows.get` - Get specific window information
- `windows.get_current` - Get current active window
- `windows.get_last_focused` - Get most recently focused window
- `windows.create` - Create new browser window
- `windows.close` - Close specific window
- `windows.focus` - Bring window to front
- `windows.update` - Update window properties (resize, move, state)

### Bookmark Management
- `bookmarks.list` - Get all bookmarks (flattened from tree structure)
- `bookmarks.search` - Search bookmarks
- `bookmarks.create` - Add new bookmark
- `bookmarks.delete` - Remove bookmark
- `bookmarks.update` - Modify existing bookmark
- `bookmarks.create_folder` - Create bookmark folder

## WebSocket Protocol

All communication uses JSON messages over WebSocket:

```json
{
  "id": "unique-request-id",
  "type": "request|response|error",
  "action": "function_name",
  "data": {...},
  "timestamp": "ISO-8601"
}
```

See `protocol.md` for complete message specifications.

## MCP Integration

FoxMCP now includes FastMCP integration that transforms browser functions into callable MCP tools:

### MCP Server
- **WebSocket Server**: Port 8765 (default) for Firefox extension communication
- **MCP Server**: Port 3000 (default) for MCP client connections
- **FastMCP Tools**: All browser functions exposed as MCP tools

### Available MCP Tools

#### Tab Management
- `tabs_list()` - List all open tabs
- `tabs_create(url, active=True, pinned=False, window_id=None)` - Create new tab (optionally in specific window)
- `tabs_close(tab_id)` - Close specific tab
- `tabs_switch(tab_id)` - Switch to specific tab

#### History Operations
- `history_query(query, max_results=50)` - Search browser history
- `history_get_recent(count=10)` - Get recent history items
- `history_delete_item(url)` - Delete specific history item

#### Bookmark Management
- `bookmarks_list(folder_id=None)` - List bookmarks
- `bookmarks_search(query)` - Search bookmarks
- `bookmarks_create(title, url, parent_id=None)` - Create bookmark
- `bookmarks_delete(bookmark_id)` - Delete bookmark

#### Navigation Control
- `navigation_back(tab_id)` - Navigate back in tab
- `navigation_forward(tab_id)` - Navigate forward in tab
- `navigation_reload(tab_id, bypass_cache=False)` - Reload tab
- `navigation_go_to_url(tab_id, url)` - Navigate to URL

#### Content Access
- `content_get_text(tab_id)` - Extract page text content
- `content_get_html(tab_id)` - Get page HTML source
- `content_execute_script(tab_id, script)` - Execute JavaScript directly
- `content_execute_predefined(tab_id, script_name, script_args="")` - Execute predefined external scripts

#### Window Management
- `list_windows(populate=True)` - List all browser windows with optional tab details
- `get_window(window_id, populate=True)` - Get specific window information
- `get_current_window(populate=True)` - Get current active window
- `get_last_focused_window(populate=True)` - Get most recently focused window
- `create_window(url=None, window_type="normal", state="normal", focused=True, width=None, height=None, top=None, left=None, incognito=False)` - Create new browser window
- `close_window(window_id)` - Close specific window
- `focus_window(window_id)` - Bring window to front and focus it
- `update_window(window_id, state=None, focused=None, width=None, height=None, top=None, left=None)` - Update window properties

#### Debugging Tools
- `debug_websocket_status()` - Check browser extension connection status

### Predefined Script Execution

The `content_execute_predefined()` tool allows execution of external scripts that generate JavaScript dynamically. This provides a powerful way to create reusable, parameterized browser automation scripts.

#### Setup
1. **Configure Script Directory**: Set the `FOXMCP_EXT_SCRIPTS` environment variable to point to your scripts directory:
   ```bash
   export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
   ```

2. **Create Executable Scripts**: Scripts must be executable and output JavaScript to stdout:
   ```bash
   #!/bin/bash
   # get_page_info.sh
   info_type="${1:-title}"
   case "$info_type" in
     "title") echo "document.title" ;;
     "url") echo "window.location.href" ;;
     "text") echo "document.body.innerText.substring(0, 500)" ;;
   esac
   ```

#### Usage Examples

**No Arguments (Empty String)**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "simple_script.sh",
    "script_args": ""
  }
}
```

**Single Argument**:
```json
{
  "name": "content_execute_predefined", 
  "arguments": {
    "tab_id": 123,
    "script_name": "get_page_info.sh",
    "script_args": "[\"title\"]"
  }
}
```

**Multiple Arguments with Spaces**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "add_message.sh", 
    "script_args": "[\"Hello World!\", \"my-element\", \"red\"]"
  }
}
```

#### Security Features
- ✅ **Path Traversal Protection**: Script names cannot contain `..`, `/`, or `\`
- ✅ **Character Validation**: Only alphanumeric, underscore, dash, and dot allowed
- ✅ **Directory Containment**: Resolved paths must stay within `FOXMCP_EXT_SCRIPTS`
- ✅ **Executable Validation**: Scripts must have execute permissions
- ✅ **JSON Validation**: Arguments must be valid JSON array of strings

#### Argument Formats
- **Empty string**: `""` → No arguments
- **Empty array**: `"[]"` → No arguments  
- **JSON array**: `"[\"arg1\", \"arg2\"]"` → Multiple arguments

### MCP Parameter Format

FoxMCP uses **direct parameter format** (no `params` wrapper). External MCP agents should send:

#### ✅ Correct Format
```json
{
  "method": "tools/call",
  "params": {
    "name": "history_get_recent",
    "arguments": {"count": 10}
  }
}
```

#### ❌ Incorrect Format  
```json
{
  "method": "tools/call",
  "params": {
    "name": "history_get_recent", 
    "arguments": {"params": {"count": 10}}  // Wrong: nested params
  }
}
```

### Using MCP Tools

1. **Start the server**:
   ```bash
   make run-server  # Starts both WebSocket (8765) and MCP (3000) servers

   # Or with custom configuration:
   python server/server.py --port 9000 --mcp-port 4000
   python server/server.py --no-mcp  # WebSocket only, disable MCP server
   ```

2. **Configure Firefox extension** (if using non-default ports):
   - Right-click extension icon → **"Manage Extension"** → **"Preferences"**
   - Set **Hostname**: `localhost`
   - Set **WebSocket Port**: `8765` (or your custom port)
   - Click **"Save Settings"** → Extension automatically reconnects

3. **Connect Firefox extension** (loads automatically when Firefox starts with extension)

4. **Connect MCP client** to `http://localhost:3000` and use the tools

### Complete Workflow
```
MCP Client → FastMCP Server → WebSocket → Firefox Extension → Browser API
```

## Server Configuration

### Command Line Options
```bash
python server/server.py [options]

Options:
  --host HOST          Host to bind to (default: localhost, security-enforced)
  --port PORT          WebSocket port (default: 8765)
  --mcp-port MCP_PORT  MCP server port (default: 3000)
  --no-mcp             Disable MCP server
  -h, --help           Show help message
```

### Security Features
- **Localhost-only binding**: Both WebSocket and MCP servers bind to `localhost` only for security
- **Host enforcement**: Any attempt to bind to external interfaces (e.g., `0.0.0.0`) is automatically changed to `localhost` with a warning
- **Default secure configuration**: No configuration required for secure localhost-only operation

### Server Ports
- **WebSocket Port**: Default `8765` - Used for Firefox extension communication
- **MCP Port**: Default `3000` - Used for MCP client connections

### Configuring Extension
The Firefox extension includes comprehensive configuration options with **storage.sync** persistence:

1. **Access Options**:
   - **Options Page**: Right-click extension → "Manage Extension" → "Preferences"
   - **Popup Interface**: Click extension icon for quick configuration
   - Or go to `about:addons` → FoxMCP → "Preferences"

2. **Configure Connection**:
   - **Hostname**: Server hostname (default: `localhost`)
   - **WebSocket Port**: Server WebSocket port (default: `8765`)
   - **Advanced Options**: Retry intervals, max retries, ping timeouts
   - **Test Configuration**: Built-in test override system for development

3. **Features**:
   - **Real-time storage sync**: Configuration changes persist across browser restarts
   - **Connection Status**: Real-time connection status monitoring
   - **Status Indicators**: Live connection status with retry attempt information
   - **Automatic Reconnection**: Extension automatically reconnects when settings change
   - **Configuration Preservation**: Test settings maintained during normal use

### Programmatic Server Configuration
```python
# Default configuration (localhost-only, secure)
server = FoxMCPServer()  # WebSocket: localhost:8765, MCP: localhost:3000

# Custom ports (still localhost-only)
server = FoxMCPServer(host="localhost", port=9000, mcp_port=4000)

# WebSocket only (disable MCP)
server = FoxMCPServer(port=8765, start_mcp=False)
```

## Development Commands

```bash
# Setup and Installation
make setup              # Install all dependencies
make install           # Install server dependencies only
make dev               # Setup development environment

# Building and Packaging
make build             # Build extension package
make package           # Create distributable ZIP files

# Testing
make test              # Run all tests
make test-unit         # Run unit tests only
make test-integration  # Run integration tests only
make check             # Run linting + tests

# Development
make run-server        # Start WebSocket server
make load-extension    # Show instructions for loading extension
make lint              # Run Python linting
make format            # Format Python code

# Maintenance
make clean             # Clean build artifacts
make clean-all         # Deep clean including dependencies
make status            # Show project status
```

## Legacy Configuration Reference

### Default Server Settings
- **Host:** `localhost` (security-enforced, cannot be changed)
- **WebSocket Port:** `8765` (configurable via `--port`)
- **MCP Port:** `3000` (configurable via `--mcp-port`)
- **Protocol:** WebSocket (ws://localhost:port)

### Firefox Extension Permissions
- `tabs` - Tab management
- `history` - Browser history access
- `bookmarks` - Bookmark management
- `activeTab` - Current tab content
- `storage` - Extension storage
- `<all_urls>` - All website access

## Testing

The project includes comprehensive test coverage with **91 tests** and **74% code coverage**:

- **Unit Tests (47):** Individual component testing
- **Integration Tests (44):** End-to-end WebSocket communication
- **Protocol Tests:** Message format validation
- **Ping-Pong Tests:** Connection validation
- **Firefox Integration Tests:** Real browser extension testing with dynamic port allocation
- **Live Server Tests:** Real WebSocket server communication testing
- **UI Synchronization Tests:** Automated validation of popup/options storage sync via test helper protocol

### Running Tests

```bash
# Run all tests with coverage
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run specific integration test suites
cd tests && python -m pytest integration/test_live_server_communication.py -v
cd tests && python -m pytest integration/test_firefox_extension_communication.py -v
```

**Test Infrastructure Features:**
- **Dynamic port allocation** prevents test conflicts
- **Robust fixture management** with proper async cleanup
- **Firefox integration testing** with temporary profiles
- **Real WebSocket communication** between server and extension

Coverage reports are generated in `tests/htmlcov/`.

### Test Helper Protocol

The extension includes a **test helper protocol** for automated UI validation via WebSocket messages:

```javascript
// Get popup display state
{
  "id": "test_001",
  "type": "request",
  "action": "test.get_popup_state",
  "data": {}
}

// Validate UI-storage synchronization  
{
  "id": "test_002", 
  "type": "request",
  "action": "test.validate_ui_sync",
  "data": {
    "expectedValues": {
      "hostname": "localhost",
      "testPort": 7777
    }
  }
}
```

**Available test helpers:**
- `test.get_popup_state` - Get current popup display values and test override status
- `test.get_options_state` - Get options page configuration and warning states
- `test.get_storage_values` - Retrieve raw storage.sync values
- `test.validate_ui_sync` - Validate UI components show expected storage values
- `test.refresh_ui_state` - Trigger UI refresh for testing scenarios

This enables **automated testing** of storage synchronization without browser automation tools.

## Troubleshooting

### Extension Not Connecting
1. Check server is running: `make status`
2. Verify WebSocket URL in browser console
3. Check browser permissions granted
4. Verify connection: Check status in extension popup

### MCP Agent Issues

#### "Unable to get recent history" Response
1. **Check WebSocket connection**:
   ```json
   {
     "method": "tools/call",
     "params": {
       "name": "debug_websocket_status",
       "arguments": {}
     }
   }
   ```

2. **Verify parameter format** - Use direct parameters:
   - ✅ Correct: `{"count": 5}`
   - ❌ Wrong: `{"params": {"count": 5}}`

3. **Check server logs** for WebSocket response debugging:
   ```
   🔍 DEBUG - Recent history WebSocket response: {...}
   ```

#### Parameter Format Errors
Common issues with external MCP agents:
- **Nested params**: Don't wrap parameters in a `params` object
- **String instead of JSON**: Send JSON objects, not strings
- **Wrong field names**: Use `arguments` not `params` in MCP requests

#### Tool Discovery Issues
1. Use `tools/list` to see available tools
2. History tools: `history_query`, `history_get_recent`, `history_delete_item`
3. All tools use direct parameter format (no wrapper)

### Tests Failing
1. **Port conflicts resolved**: Tests now use dynamic port allocation
2. Install test dependencies: `make setup`
3. Check Python version compatibility (requires Python 3.7+)
4. For Firefox integration tests: Set custom Firefox path if needed: `FIREFOX_PATH=/path/to/firefox make test-integration`

### Build Issues
1. Clean and rebuild: `make clean && make build`
2. Check file permissions
3. Verify directory structure

### Test Infrastructure Issues
- **Dynamic ports**: Integration tests automatically allocate unique ports (9000-10999 range)
- **Fixture cleanup**: All async fixtures properly clean up resources
- **Firefox integration**: Temporary profiles are automatically created and cleaned up
- **Coverage reports**: Generated in `tests/htmlcov/` after test runs

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test: `make check`
4. Submit pull request

## Implementation Status

### 📊 Test Results - ALL PASSING ✅
- **91 total tests** across comprehensive test suites
- **74% code coverage** of server components
- **44 integration tests** including real Firefox browser communication and automated UI validation
- **47 unit tests** covering individual component functionality
- **All browser API functions tested** and verified working
- **Real WebSocket communication confirmed** between server and Firefox extension

## Architecture

```
┌─────────────────┐    WebSocket     ┌──────────────────┐    MCP Protocol    ┌─────────────┐
│                 │   (Port 8765)    │                  │                    │             │
│  Firefox        │◄────────────────►│  Python Server   │◄──────────────────►│ MCP Client  │
│  Extension      │                  │  (FastMCP)       │                    │             │
│                 │                  │                  │                    │             │
└─────────────────┘                  └──────────────────┘                    └─────────────┘
        │
        ▼
┌─────────────────┐
│                 │
│ WebExtensions   │
│ APIs            │
│  - Tabs         │
│  - History      │
│  - Bookmarks    │
│  - Navigation   │
│  - Content      │
└─────────────────┘
```

The Firefox extension acts as a bridge between WebExtensions APIs and MCP clients, enabling AI assistants and other tools to interact with browser functionality programmatically.
