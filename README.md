# FoxMCP - Browser Extension MCP Integration

A browser extension that exposes browser functionality (history, tabs, bookmarks, navigation, content) to MCP (Model Context Protocol) clients via WebSocket communication.

## Quick Start

```bash
# Install dependencies and build
make setup
make build

# Start the server
make run-server

# In another terminal, run tests
make test

# Load extension in browser
make load-extension
```

## Project Structure

```
foxmcp/
├── extension/          # Browser extension (Chrome/Firefox)
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

### Extension Permissions
- `tabs` - Tab management
- `history` - Browser history access
- `bookmarks` - Bookmark management  
- `activeTab` - Current tab content
- `storage` - Extension storage
- `<all_urls>` - All website access

## Testing

The project includes comprehensive test coverage:

- **Unit Tests:** Individual component testing
- **Integration Tests:** End-to-end WebSocket communication
- **Protocol Tests:** Message format validation
- **Ping-Pong Tests:** Connection validation

Run with coverage:
```bash
make test
# Coverage report generated in tests/htmlcov/
```

## Troubleshooting

### Extension Not Connecting
1. Check server is running: `make status`
2. Verify WebSocket URL in browser console
3. Check browser permissions granted
4. Test with ping-pong: Click "Test Connection"

### Tests Failing
1. Install test dependencies: `make setup`
2. Check Python version compatibility
3. Verify no port conflicts: `netstat -ln | grep 8765`

### Build Issues
1. Clean and rebuild: `make clean && make build`
2. Check file permissions
3. Verify directory structure

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test: `make check`
4. Submit pull request

## License

MIT License - see LICENSE file for details.

## Implementation Status

### ✅ Completed Features
- **Browser Extension**: Complete Chrome extension with manifest V3, background service worker, content script, and popup UI
- **WebSocket Communication**: Bidirectional communication with auto-reconnect and configurable retry intervals
- **Browser API Integration**: Full implementations for history, tabs, content, navigation, and bookmarks APIs
- **Response Correlation**: UUID-based request/response correlation with async handling and timeouts
- **Configuration System**: Persistent configuration with UI controls for connection parameters
- **Test Infrastructure**: Comprehensive unit and integration tests with 70% code coverage
- **Build System**: Complete Makefile with development, testing, and packaging commands

### ⏳ In Progress
- **FastMCP Integration**: MCP protocol server implementation (framework ready, needs integration)

### 📋 Pending
- **End-to-end Testing**: Integration testing with real browser extension and MCP client
- **Production Deployment**: Enhanced logging and multi-client support

### 📊 Test Results
- **55 tests passing**, 1 skipped (requires live browser extension)
- **70% code coverage** across server components
- **All browser API handlers implemented** and tested

## Architecture

```
┌─────────────────┐    WebSocket     ┌──────────────────┐    MCP Protocol    ┌─────────────┐
│                 │   (Port 8765)    │                  │                    │             │
│  Browser        │◄────────────────►│  Python Server   │◄──────────────────►│ MCP Client  │
│  Extension      │                  │  (FastMCP)       │                    │             │
│                 │                  │                  │                    │             │
└─────────────────┘                  └──────────────────┘                    └─────────────┘
        │
        ▼
┌─────────────────┐
│                 │
│  Browser APIs   │
│  - Tabs         │
│  - History      │
│  - Bookmarks    │
│  - Navigation   │
│  - Content      │
└─────────────────┘
```

The extension acts as a bridge between browser APIs and MCP clients, enabling AI assistants and other tools to interact with browser functionality programmatically.