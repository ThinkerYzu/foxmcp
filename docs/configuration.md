# Server Configuration

Complete guide to configuring and running the FoxMCP server.

## Starting the Server

```bash
# Quick start (both WebSocket and MCP servers)
make run-server

# Custom configuration
python server/server.py --port 9000 --mcp-port 4000
python server/server.py --no-mcp  # WebSocket only, disable MCP server
```

## Command Line Options

```bash
python server/server.py [options]

Options:
  --host HOST          Host to bind to (default: localhost, security-enforced)
  --port PORT          WebSocket port (default: 8765)
  --mcp-port MCP_PORT  MCP server port (default: 3000)
  --no-mcp             Disable MCP server
  --disable-tools GROUP[,GROUP...]
                       Tool groups to leave unregistered (default: none)
  -h, --help           Show help message
```

## Reducing the Tool Surface

Every tool's description sits in an MCP client's context for the whole session,
whether or not the tool is ever called. The full set of 35 tools costs roughly
4,700 tokens. `--disable-tools` leaves a group unregistered, so a client never
sees it:

```bash
# A setup that only drives tabs and reads pages
python server/server.py --disable-tools bookmarks,history,requests
```

The groups, and what each costs when enabled. The token figures estimate the
serialized name, description and input schema of each tool at four characters per
token, so treat them as proportions rather than exact counts:

| Group | Tools | ~Tokens |
|---|---|---|
| `tabs` | list, create, close, switch, move, capture_screenshot | 1,195 |
| `windows` | list, get, get_current, create, close, focus, update | 948 |
| `bookmarks` | list, search, create, create_folder, update, delete | 703 |
| `requests` | start_monitoring, stop_monitoring, list_captured, get_content | 693 |
| `content` | get_text, get_html, execute_script, execute_predefined | 421 |
| `navigation` | back, forward, reload, go_to_url | 380 |
| `history` | query, get_recent, delete_item | 304 |
| `debug` | websocket_status | 58 |

All groups are on by default. An unrecognized group name is an error rather than
a warning, so a typo cannot silently leave the group enabled.

The same list can be set through the environment, for clients that launch the
server through a wrapper whose arguments you do not control:

```bash
export FOXMCP_DISABLE_TOOLS=bookmarks,history
```

`--disable-tools` overrides `FOXMCP_DISABLE_TOOLS` when both are given.

Disabling a group hides its tools; it does not restrict the extension, which
still holds the same browser permissions. This is a context-size option, not a
security boundary — see [architecture.md](architecture.md#security-architecture).

## Security Features

- **Localhost-only binding**: Both WebSocket and MCP servers bind to `localhost` only for security
- **Host enforcement**: Any attempt to bind to external interfaces (e.g., `0.0.0.0`) is automatically changed to `localhost` with a warning
- **Default secure configuration**: No configuration required for secure localhost-only operation

## Server Ports

- **WebSocket Port**: Default `8765` - Used for Firefox extension communication
- **MCP Port**: Default `3000` - Used for MCP client connections

## Configuring Extension

The Firefox extension includes comprehensive configuration options with **storage.sync** persistence:

### 1. Access Options

- **Options Page**: Right-click extension → "Manage Extension" → "Preferences"
- **Popup Interface**: Click extension icon for quick configuration
- Or go to `about:addons` → FoxMCP → "Preferences"

### 2. Configure Connection

- **Hostname**: Server hostname (default: `localhost`)
- **WebSocket Port**: Server WebSocket port (default: `8765`)
- **Advanced Options**: Retry intervals, max retries, ping timeouts
- **Test Configuration**: Built-in test override system for development

### 3. Features

- **Real-time storage sync**: Configuration changes persist across browser restarts
- **Connection Status**: Real-time connection status monitoring
- **Status Indicators**: Live connection status with retry attempt information
- **Automatic Reconnection**: Extension automatically reconnects when settings change
- **Configuration Preservation**: Test settings maintained during normal use

## Programmatic Server Configuration

```python
# Default configuration (localhost-only, secure)
server = FoxMCPServer()  # WebSocket: localhost:8765, MCP: localhost:3000

# Custom ports (still localhost-only)
server = FoxMCPServer(host="localhost", port=9000, mcp_port=4000)

# WebSocket only (disable MCP)
server = FoxMCPServer(port=8765, start_mcp=False)
```

## MCP Client Connection

1. **Start the server** (both WebSocket and MCP servers)
2. **Load Firefox extension** (connects automatically to WebSocket)
3. **Connect MCP client** to `http://localhost:3000`

### Supported MCP Clients

**Claude Code**:
```bash
claude mcp add --transport http foxmcp http://localhost:3000/mcp/
```

**Other MCP Clients**:
Connect directly to `http://localhost:3000/mcp/`

**Complete Workflow**:
```
MCP Client → FastMCP Server → WebSocket → Firefox Extension → Browser API
```

## Environment Variables

### Required for Predefined Scripts

```bash
# Set path to your custom scripts directory
export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
```

### Optional Configuration

The server reads two environment variables. `FOXMCP_EXT_SCRIPTS` points at the
directory holding predefined scripts:

```bash
export FOXMCP_EXT_SCRIPTS=/path/to/predefined/
```

`FOXMCP_DISABLE_TOOLS` names tool groups to leave unregistered — see
[Reducing the Tool Surface](#reducing-the-tool-surface).

Ports are set on the command line, not through the environment — see
[Multiple Server Instances](#multiple-server-instances).

## Multiple Server Instances

You can run multiple FoxMCP servers on different ports:

```bash
# Server 1 - Default ports
python server/server.py

# Server 2 - Custom ports
python server/server.py --port 8766 --mcp-port 3001

# Server 3 - WebSocket only
python server/server.py --port 8767 --no-mcp
```

## Docker Configuration

```dockerfile
FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

# Expose ports
EXPOSE 8765 3000

# Run server
CMD ["python", "server/server.py"]
```

```bash
# Build and run
docker build -t foxmcp .
docker run -p 8765:8765 -p 3000:3000 foxmcp
```

## Configuration Files

FoxMCP supports configuration files for persistent settings:

### `config.json` (Optional)

```json
{
  "server": {
    "host": "localhost",
    "websocket_port": 8765,
    "mcp_port": 3000,
    "enable_mcp": true
  },
  "security": {
    "localhost_only": true,
    "allow_external": false
  },
  "scripts": {
    "directory": "/path/to/scripts",
    "timeout": 30
  },
  "logging": {
    "level": "INFO",
    "file": "foxmcp.log"
  }
}
```

```bash
# Use configuration file
python server/server.py --config config.json
```

## Logging Configuration

### Basic Logging

```python
import logging

# Set log level
logging.basicConfig(level=logging.INFO)

# Start server with logging
server = FoxMCPServer()
```

### Advanced Logging

Importing `server.server` calls `logging.basicConfig(level=logging.INFO)` at module
level, so a later `basicConfig()` call does nothing. Reconfigure the root logger
instead:

```python
import logging
from server.server import FoxMCPServer

root = logging.getLogger()
root.setLevel(logging.DEBUG)
root.addHandler(logging.FileHandler('foxmcp.log'))

server = FoxMCPServer()
```

## Tuning

`FoxMCPServer` takes only `host`, `port`, `mcp_port`, and `start_mcp`. WebSocket frame
sizes, ping intervals, and MCP concurrency are not exposed — the server accepts the
`websockets` and FastMCP defaults.

Two things you can change:

**Request timeout.** `send_request_and_wait` waits 30 seconds by default. Pass
`timeout` to override it for a slow call:

```python
response = await server.send_request_and_wait(request, timeout=60.0)
```

A timeout returns an error dict rather than raising, so callers must check for
`"error"` in the response.

**Extension reconnection.** `CONFIG` at the top of `extension/background.js` sets
`retryInterval` (5000 ms) and `maxRetries` (`-1`, meaning retry forever). Both are also
editable from the extension popup. Changing the source values requires a rebuild.

## Troubleshooting Configuration

### Common Issues

1. **Port already in use**:
   ```bash
   # Check what's using the port
   lsof -i :8765

   # Use different port
   python server/server.py --port 8766
   ```

2. **Extension can't connect**:
   - Check server is running: `curl http://localhost:8765`
   - Verify extension configuration matches server ports
   - Check browser console for connection errors

3. **MCP client connection issues**:
   ```bash
   # Reach the MCP server
   curl http://localhost:3000
   ```

   The server logs to stdout, so run it in the foreground to watch connections
   arrive.

### Debug Logging

The server logs at `INFO`. There is no verbosity flag — the level is set in
`server/server.py`.

For extension-side detail, set `ENABLE_DEBUG_LOGGING_TO_SERVER = true` near the top of
`extension/background.js`. The extension then forwards its logs over the WebSocket and
the server prints them under `----- EXTENSION DEBUG LOG -----`. Rebuild after the edit,
and set it back to `false` before committing:

```bash
make clean && make package && rm -rf dist/profile-cache/*
```

## Security Configuration

### Production Deployment

```python
# Production configuration
server = FoxMCPServer(
    host="localhost",      # Never use 0.0.0.0 in production
    enable_cors=False,     # Disable CORS for security
    require_auth=True,     # Enable authentication
    ssl_cert="cert.pem",   # Use SSL certificates
    ssl_key="key.pem"
)
```

### Development vs Production

```python
import os

# Environment-based configuration
if os.getenv("ENVIRONMENT") == "production":
    server = FoxMCPServer(
        host="localhost",
        enable_debug=False,
        require_auth=True
    )
else:
    server = FoxMCPServer(
        host="localhost",
        enable_debug=True,
        require_auth=False
    )
```

## Checking Server Health

There are no health, status, or metrics HTTP endpoints. Three things tell you whether
the pair is connected:

| Check | How | Tells you |
|---|---|---|
| `debug_websocket_status` | Call the MCP tool | Whether the extension is connected right now |
| Extension popup | Click the toolbar icon | Connection state from the browser's side |
| `make status` | From the project root | Whether port 8765 is in use |

The server logs connections and disconnections to stdout, so running it in the
foreground is the quickest way to watch the socket come and go.