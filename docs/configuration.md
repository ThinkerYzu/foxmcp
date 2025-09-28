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
  -h, --help           Show help message
```

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
claude mcp add foxmcp http://localhost:3000/mcp/
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

```bash
# Override default ports
export FOXMCP_WEBSOCKET_PORT=8765
export FOXMCP_MCP_PORT=3000

# Debug mode
export FOXMCP_DEBUG=1
```

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

```python
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('foxmcp.log'),
        logging.StreamHandler()
    ]
)

# Server will use configured logging
server = FoxMCPServer()
```

## Performance Tuning

### WebSocket Configuration

```python
# Adjust WebSocket settings for performance
server = FoxMCPServer(
    max_size=1000000,  # Max message size
    ping_interval=20,  # Ping interval (seconds)
    ping_timeout=10,   # Ping timeout (seconds)
    close_timeout=10   # Close timeout (seconds)
)
```

### MCP Server Optimization

```python
# Configure FastMCP server
server = FoxMCPServer(
    mcp_workers=4,     # Number of worker threads
    mcp_timeout=30,    # Request timeout
    mcp_max_requests=100  # Max concurrent requests
)
```

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
   # Test MCP server
   curl http://localhost:3000/health

   # Check MCP server logs
   python server/server.py --debug
   ```

### Debug Mode

```bash
# Enable verbose logging
python server/server.py --debug

# Or set environment variable
export FOXMCP_DEBUG=1
python server/server.py
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

## Monitoring and Health Checks

### Health Endpoints

```bash
# Check WebSocket server
curl http://localhost:8765/health

# Check MCP server
curl http://localhost:3000/health

# Get server status
curl http://localhost:8765/status
```

### Metrics Collection

```python
# Enable metrics collection
server = FoxMCPServer(
    enable_metrics=True,
    metrics_port=9090
)

# Access metrics at http://localhost:9090/metrics
```