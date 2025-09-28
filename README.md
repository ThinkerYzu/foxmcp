# FoxMCP - Firefox Browser Automation via MCP

A Firefox extension that exposes browser functionality to AI assistants and automation tools through the Model Context Protocol (MCP). Control tabs, history, bookmarks, navigation, content, and windows programmatically.

## ⚠️ Privacy Notice

**FoxMCP enables AI access to your browser data.** Use only with trusted AI services and consider using dedicated browser profiles for testing.

## Features

- **Complete Browser Control**: Tabs, windows, navigation, bookmarks, history
- **Content Access**: Extract text, HTML, execute JavaScript in pages
- **MCP Integration**: Works with Claude, ChatGPT, and other MCP clients
- **Custom Scripts**: Execute parameterized scripts in browser tabs
- **Real-time Communication**: WebSocket-based with automatic reconnection
- **Security**: Localhost-only operation with comprehensive input validation

## Quick Start

### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/your-repo/foxmcp.git
cd foxmcp

# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Build & Install Extension

```bash
# Build extension
make build

# Install in Firefox:
# 1. Open Firefox
# 2. Go to about:debugging
# 3. Click "This Firefox"
# 4. Click "Load Temporary Add-on"
# 5. Select extension/foxmcp.xpi
```

### 3. Start Server

```bash
# Start both WebSocket and MCP servers
make run-server

# Or manually:
python server/server.py
```

The server will start on:
- **WebSocket**: `localhost:8765` (for Firefox extension)
- **MCP Server**: `localhost:3000` (for AI clients)

### 4. Connect Your AI Client

**For Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "foxmcp": {
      "command": "python",
      "args": ["/path/to/foxmcp/server/server.py", "--mcp-only"],
      "cwd": "/path/to/foxmcp"
    }
  }
}
```

**For Other MCP Clients**:
Connect to `http://localhost:3000`

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

# Debug mode
python server/server.py --debug
```

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

## Documentation

- **[API Reference](docs/api-reference.md)** - Complete function reference
- **[Configuration](docs/configuration.md)** - Server and extension setup
- **[Custom Scripts](docs/scripts.md)** - Create reusable automation scripts
- **[Development](docs/development.md)** - Development setup and workflow
- **[Architecture](docs/architecture.md)** - System design and components
- **[Protocol](docs/protocol.md)** - WebSocket message format

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
1. Verify server is running: `curl http://localhost:8765`
2. Check extension popup for connection status
3. Review browser console for errors

### MCP Client Issues
1. Check MCP server: `curl http://localhost:3000`
2. Verify client configuration matches server ports
3. Enable debug logging: `python server/server.py --debug`

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