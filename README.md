# FoxMCP - Firefox Extension MCP Integration

A Firefox extension that exposes browser functionality (history, tabs, bookmarks, navigation, content) to MCP (Model Context Protocol) clients via WebSocket communication. Features FastMCP server integration for seamless MCP tool access.

## Quick Start

```bash
# Install dependencies and build
make setup
make build

# Start the server
make run-server

# In another terminal, run tests
make test

# Run tests with Firefox extension loaded
make test-with-firefox

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

**Chrome:**
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `extension/` directory

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
- Click "Test Connection" button
- Should see "✅ Ping successful!" if working

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

### Bookmark Management
- `bookmarks.list` - Get all bookmarks
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
- `tabs_create(url, active=True, pinned=False)` - Create new tab
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
- `content_execute_script(tab_id, code)` - Execute JavaScript

### Using MCP Tools

1. **Start the server**:
   ```bash
   make run-server  # Starts both WebSocket (8765) and MCP (3000) servers
   
   # Or with custom ports:
   python server/server.py --port 9000 --mcp-port 4000
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

## Port Configuration

### Server Ports
- **WebSocket Port**: Default `8765` - Used for Firefox extension communication
- **MCP Port**: Default `3000` - Used for MCP client connections

### Configuring Extension
The Firefox extension includes an **Options Page** for easy port configuration:

1. **Access Options**:
   - Firefox: Right-click extension → "Manage Extension" → "Preferences"
   - Or go to `about:addons` → FoxMCP → "Preferences"

2. **Configure Connection**:
   - **Hostname**: Server hostname (default: `localhost`)
   - **WebSocket Port**: Server WebSocket port (default: `8765`)
   - **Advanced Options**: Retry intervals, timeouts, etc.

3. **Test Connection**: Built-in connection test with status indicator

4. **Automatic Reconnection**: Extension automatically reconnects when settings change

### Server Configuration
```python
# Default configuration
server = FoxMCPServer()  # WebSocket: 8765, MCP: 3000

# Custom ports
server = FoxMCPServer(port=9000, mcp_port=4000)

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

## Configuration

### Server Configuration
- **Host:** localhost (default)
- **Port:** 8765 (default)
- **Protocol:** WebSocket (ws://)

### Firefox Extension Permissions
- `tabs` - Tab management
- `history` - Browser history access
- `bookmarks` - Bookmark management  
- `activeTab` - Current tab content
- `storage` - Extension storage
- `<all_urls>` - All website access

## Testing

The project includes comprehensive test coverage with **77 tests** and **74% code coverage**:

- **Unit Tests (39):** Individual component testing
- **Integration Tests (38):** End-to-end WebSocket communication
- **Protocol Tests:** Message format validation
- **Ping-Pong Tests:** Connection validation
- **Firefox Integration Tests:** Real browser extension testing with dynamic port allocation
- **Live Server Tests:** Real WebSocket server communication testing

### Running Tests

```bash
# Run all tests with Firefox integration
make test-with-firefox

# Run all tests with coverage
make test

# Run unit tests only
make test-unit

# Run integration tests only  
make test-integration

# Custom Firefox path (recommended for testing)
FIREFOX_PATH=~/tmp/ff2/bin/firefox make test-with-firefox

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

## Troubleshooting

### Extension Not Connecting
1. Check server is running: `make status`
2. Verify WebSocket URL in browser console
3. Check browser permissions granted
4. Test with ping-pong: Click "Test Connection"

### Tests Failing
1. **Port conflicts resolved**: Tests now use dynamic port allocation
2. Install test dependencies: `make setup`
3. Check Python version compatibility (requires Python 3.7+)
4. For Firefox tests: Ensure custom Firefox path is correct: `FIREFOX_PATH=/path/to/firefox make test-with-firefox`

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

## License

MIT License - see LICENSE file for details.

## Implementation Status

### ✅ Completed Features
- **Firefox Extension**: Complete Firefox extension with manifest V2, persistent background script, content script, and popup UI
- **WebSocket Communication**: Bidirectional communication with auto-reconnect and configurable retry intervals
- **Browser API Integration**: Full WebExtensions API implementations for history, tabs, content, navigation, and bookmarks
- **Response Correlation**: UUID-based request/response correlation with async handling and timeouts
- **Configuration System**: Persistent configuration with UI controls for connection parameters
- **Comprehensive Test Suite**: 77 tests with 74% code coverage and robust Firefox integration
- **Build System**: Complete Makefile with development, testing, and XPI packaging commands
- **Production-Ready WebSocket Server**: Robust server with proper error handling and connection management

### ✅ Advanced Testing Infrastructure  
- **Real Firefox Integration**: Automated testing with temporary profiles and extension installation
- **Dynamic Port Allocation**: Conflict-free test execution with unique ports per test suite
- **Robust Fixture Management**: Proper async cleanup and resource management
- **Multi-Client Testing**: Concurrent connection handling and server resilience testing
- **Protocol Compliance**: Comprehensive message format and browser API coverage validation

### ⏳ In Progress
- **FastMCP Integration**: MCP protocol server implementation (framework ready, needs integration)

### 📋 Pending
- **Production Deployment**: Enhanced logging and multi-client support

### 📊 Test Results - ALL PASSING ✅
- **77 total tests** across comprehensive test suites
- **74% code coverage** of server components  
- **38 integration tests** including real Firefox browser communication
- **39 unit tests** covering individual component functionality
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