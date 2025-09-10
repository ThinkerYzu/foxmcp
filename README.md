# FoxMCP - Firefox Extension MCP Integration

A Firefox extension that exposes browser functionality (history, tabs, bookmarks, navigation, content, windows) to MCP (Model Context Protocol) clients via WebSocket communication. Features FastMCP server integration for seamless MCP tool access.

You may aware that this project is helped by Claude Code. By asking
Claude Code to update several documents periodically, it understands
the goal of the project pretty well. Check CLAUDE.md.

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

## Using FoxMCP with Claude Code

Claude Code provides built-in MCP support that makes it easy to use FoxMCP browser tools directly in your coding sessions.

### Setup Steps

1. **Start the FoxMCP server**:
   ```bash
   make run-server
   # Server starts on localhost:8765 (WebSocket) and localhost:3000 (MCP)
   ```

2. **Load the Firefox extension**:

   **Option A: Temporary Extension (Development)**
   - Go to `about:debugging` in Firefox
   - Click "This Firefox" → "Load Temporary Add-on"
   - Select `extension/manifest.json`

   **Option B: Install XPI Package (Permanent)**
   - Build the package: `make package`
   - Go to `about:config` in Firefox and set `xpinstall.signatures.required` to `false`
   - Go to `about:addons`
   - Click the gear icon → "Install Add-on From File"
   - Select `dist/packages/foxmcp@codemud.org.xpi`

   - Verify connection status shows "Connected" in extension popup

3. **Configure Claude Code MCP**:
   ```bash
   # Add FoxMCP server to Claude Code
   claude mcp add foxmcp http://localhost:3000

   # Verify it was added
   claude mcp list
   ```

4. **Use browser tools in Claude Code**:
   Once configured, you can use browser functions directly in your conversations:

   ```
   User: "Can you check what tabs I have open?"
   Claude: I'll check your open browser tabs using the tabs_list tool.
   ```

   Claude Code will automatically call the `tabs_list()` MCP tool and show you all your open Firefox tabs.

## Predefined Scripts

Predefined scripts are external executable scripts that generate JavaScript code dynamically and execute it in browser tabs. This powerful feature allows you to create reusable, parameterized browser automation scripts that can be called via the `content_execute_predefined` MCP tool.

### How Predefined Scripts Work

1. **Script Execution**: External script runs with optional arguments
2. **JavaScript Generation**: Script outputs JavaScript code to stdout
3. **Browser Injection**: Generated JavaScript is executed in the specified browser tab
4. **Result Return**: Execution result is returned to the caller

### Creating Predefined Scripts

#### 1. Setup Script Directory

Set the environment variable to point to your scripts directory:
```bash
export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
```

#### 2. Create Executable Script

Scripts must be executable and output JavaScript to stdout:

**Simple Example** (`get_title.sh`):
```bash
#!/bin/bash
# Simple script that gets page title
echo "document.title"
```

**Parameterized Example** (`get_page_info.sh`):
```bash
#!/bin/bash
# Script that takes info type as argument
info_type="${1:-title}"
case "$info_type" in
  "title") echo "document.title" ;;
  "url") echo "window.location.href" ;;
  "text") echo "document.body.innerText.substring(0, 500)" ;;
  *) echo "document.title + ' - Unknown info type'" ;;
esac
```

**Advanced Example** (`add_banner.sh`):
```bash
#!/bin/bash
# Script that adds a banner with custom message and color
message="${1:-Hello World!}"
color="${2:-blue}"
cat << EOF
(function() {
  const banner = document.createElement('div');
  banner.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:${color};color:white;text-align:center;padding:10px;z-index:9999;';
  banner.textContent = '${message}';
  document.body.insertBefore(banner, document.body.firstChild);
  return 'Banner added: ${message}';
})()
EOF
```

#### 3. Make Scripts Executable

```bash
chmod +x /path/to/your/scripts/*.sh
```

### Using Predefined Scripts

#### Via MCP Tools

**No Arguments**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "get_title.sh",
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
    "script_args": "[\"url\"]"
  }
}
```

**Multiple Arguments**:
```json
{
  "name": "content_execute_predefined",
  "arguments": {
    "tab_id": 123,
    "script_name": "add_banner.sh",
    "script_args": "[\"Welcome to our site!\", \"green\"]"
  }
}
```

#### Via Claude Code

Once configured with Claude Code, you can use natural language:

```
User: "Add a red banner saying 'Under Maintenance' to the current page"
Claude: I'll add a maintenance banner to your page using a predefined script.
```

Claude Code will call:
```
content_execute_predefined(tab_id=current_tab, script_name="add_banner.sh", script_args=["Under Maintenance", "red"])
```

### Script Output Types

Predefined scripts output JavaScript code that gets executed in the browser tab:

```bash
#!/bin/bash
# All script output is treated as JavaScript and executed in the browser
echo "document.title"
```

```bash
#!/bin/bash
# You can return values from your JavaScript
echo "(function() { return 'Script completed: ' + document.title; })()"
```

```bash
#!/bin/bash
# Or execute actions and return status messages
echo "document.body.style.backgroundColor = 'lightblue'; 'Background changed successfully'"
```

### Security Features

- ✅ **Path Traversal Protection**: Script names cannot contain `..`, `/`, or `\`
- ✅ **Character Validation**: Only alphanumeric, underscore, dash, and dot allowed
- ✅ **Directory Containment**: Scripts must be within `FOXMCP_EXT_SCRIPTS` directory
- ✅ **Executable Validation**: Scripts must have execute permissions
- ✅ **JSON Validation**: Arguments must be valid JSON array of strings
- ✅ **Timeout Protection**: Scripts timeout after 30 seconds

### Best Practices

1. **Error Handling**: Always include error handling in your scripts
2. **Validation**: Validate input arguments before using them
3. **Documentation**: Add comments explaining what your script does
4. **Testing**: Test scripts independently before using with FoxMCP
5. **Security**: Never accept untrusted input or execute dangerous commands

### Example Script Collection

Create a collection of useful scripts:

**`extract_links.sh`** - Extract all links from page:
```bash
#!/bin/bash
echo "Array.from(document.links).map(link => ({text: link.textContent.trim(), url: link.href})).slice(0, 10)"
```

**`highlight_text.sh`** - Highlight text on page:
```bash
#!/bin/bash
search_text="${1:-example}"
echo "document.body.innerHTML = document.body.innerHTML.replace(new RegExp('${search_text}', 'gi'), '<mark>\$&</mark>'); 'Highlighted: ${search_text}'"
```

**`page_stats.sh`** - Get page statistics:
```bash
#!/bin/bash
echo "({title: document.title, links: document.links.length, images: document.images.length, words: document.body.innerText.split(/\s+/).length})"
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

For detailed development commands, see the **Development Commands** section below.

**Quick development cycle:**
1. `make dev` - Setup environment
2. `make build` - Build extension
3. Load extension in Firefox (see **Using FoxMCP with Claude Code** section for instructions)
4. `make run-server` - Start server
5. `make test` - Run tests


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


### Example Usage Scenarios

Use Claude Code as an example.

**Research Assistant**:
```
User: "I'm researching React hooks. Can you help me organize my browser?"
Claude: I'll help you organize your research. Let me first see what tabs you have open, then we can bookmark the useful ones and close the rest.
```

**Code Review Helper**:
```
User: "I have a GitHub PR open. Can you extract the diff and help me review it?"
Claude: I'll find your GitHub tab and extract the page content so we can review the code changes together.
```

**Development Workflow**:
```
User: "Open the local dev server and the documentation in separate windows"
Claude: I'll create two browser windows - one for your localhost:3000 development server and another for the documentation.
```


## Server Configuration

### Starting the Server

```bash
# Quick start (both WebSocket and MCP servers)
make run-server

# Custom configuration
python server/server.py --port 9000 --mcp-port 4000
python server/server.py --no-mcp  # WebSocket only, disable MCP server
```

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

### MCP Client Connection

1. **Start the server** (both WebSocket and MCP servers)
2. **Load Firefox extension** (connects automatically to WebSocket)
3. **Connect MCP client** to `http://localhost:3000`

**Complete Workflow**:
```
MCP Client → FastMCP Server → WebSocket → Firefox Extension → Browser API
```

**Security Notes**:
- FoxMCP only binds to localhost for security
- All browser interactions require user consent through extension permissions
- Scripts can only run on pages where the extension has permission
- No external network access - all communication stays local

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

### Claude Code MCP Issues

If MCP tools aren't working in Claude Code:

1. **Check server status**: Ensure FoxMCP server is running on port 3000
2. **Verify extension**: Firefox extension should show "Connected" status
3. **Test connection**: Use `debug_websocket_status()` tool to check connectivity
4. **Check Claude Code logs**: Look for MCP connection errors in Claude Code output

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
│  - Windows      │
└─────────────────┘
```

The Firefox extension acts as a bridge between WebExtensions APIs and MCP clients, enabling AI assistants and other tools to interact with browser functionality programmatically.
