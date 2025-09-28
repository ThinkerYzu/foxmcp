# FoxMCP Architecture

Overview of the FoxMCP system architecture, components, and data flow.

## System Overview

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

## Component Architecture

### 1. Firefox Extension

**Location**: `extension/`

#### Background Script (`background.js`)
- **Service Worker**: Runs in background, persists across browser sessions
- **WebSocket Client**: Maintains connection to Python server
- **API Handler**: Processes incoming requests and calls WebExtensions APIs
- **Response Manager**: Formats and sends responses back to server

#### Content Script (`content.js`)
- **Page Injection**: Injected into web pages for content access
- **JavaScript Execution**: Executes custom scripts in page context
- **DOM Interaction**: Extracts text, HTML, and manipulates page content
- **Communication Bridge**: Relays data between page and background script

#### Popup Interface (`popup/`)
- **Configuration UI**: User-friendly settings interface
- **Real-time Status**: Live connection status and diagnostics
- **Storage Management**: Persists settings using `storage.sync` API
- **Test Mode**: Override settings for development and testing

### 2. Python Server

**Location**: `server/`

#### WebSocket Server (`server.py`)
- **Connection Management**: Handles extension connections and reconnections
- **Message Routing**: Routes messages between extension and MCP clients
- **Protocol Implementation**: WebSocket message protocol handling
- **Security**: Localhost-only binding and input validation

#### FastMCP Integration (`fastmcp_tools.py`)
- **MCP Tool Definitions**: Converts browser functions to MCP tools
- **Parameter Validation**: Validates tool parameters and types
- **Response Formatting**: Formats browser responses for MCP clients
- **Error Handling**: Comprehensive error handling and reporting

#### Utilities (`utils.py`)
- **Helper Functions**: Common utilities for message handling
- **Validation**: Input validation and sanitization
- **Logging**: Structured logging and debugging support

### 3. Communication Protocols

#### WebSocket Protocol
```json
{
  "id": "unique-request-id",
  "type": "request|response|error",
  "action": "function_name",
  "data": {...},
  "timestamp": "ISO-8601"
}
```

#### MCP Protocol
- **Standard MCP Tools**: Browser functions exposed as MCP tools
- **Parameter Schema**: Type-safe parameter definitions
- **Result Formatting**: Consistent response formatting
- **Error Codes**: Standardized error handling

## Data Flow

### 1. MCP Client → Browser

```
MCP Client
    ↓ (MCP tool call)
FastMCP Server
    ↓ (WebSocket message)
Python Server
    ↓ (WebSocket)
Firefox Extension
    ↓ (WebExtensions API)
Browser Function
    ↓ (Result)
Firefox Extension
    ↓ (WebSocket response)
Python Server
    ↓ (MCP tool result)
FastMCP Server
    ↓ (MCP response)
MCP Client
```

### 2. Predefined Scripts Flow

```
MCP Client
    ↓ (content_execute_predefined tool)
Python Server
    ↓ (Execute external script)
External Script
    ↓ (JavaScript code output)
Python Server
    ↓ (WebSocket: content_execute_script)
Firefox Extension
    ↓ (Inject into content script)
Page JavaScript Context
    ↓ (Execution result)
Firefox Extension
    ↓ (WebSocket response)
Python Server
    ↓ (MCP tool result)
MCP Client
```

## Security Architecture

### 1. Network Security
- **Localhost Binding**: All servers bind only to `127.0.0.1`
- **No External Access**: Cannot be accessed from network
- **Port Isolation**: Default ports for different services

### 2. Extension Security
- **Content Security Policy**: Strict CSP in manifest
- **Permission Model**: Minimal required permissions
- **Input Validation**: All inputs validated before processing
- **Sandboxing**: Content scripts run in isolated context

### 3. Script Security
- **Path Validation**: Predefined scripts path traversal protection
- **Character Filtering**: Only safe characters allowed in script names
- **Timeout Protection**: Scripts timeout after 30 seconds
- **Execution Isolation**: Scripts run in separate processes

## Scalability Considerations

### 1. Connection Management
- **Single Extension Connection**: One extension per server instance
- **Multiple MCP Clients**: Multiple clients can connect to same server
- **Reconnection Logic**: Automatic reconnection on connection loss

### 2. Performance Optimization
- **Async Processing**: All operations are asynchronous
- **Message Queuing**: WebSocket messages queued for reliability
- **Resource Cleanup**: Automatic cleanup of resources
- **Caching**: Response caching where appropriate

### 3. Resource Limits
- **Message Size**: Maximum WebSocket message size limits
- **Timeout Handling**: Request timeouts prevent hanging
- **Memory Management**: Automatic garbage collection
- **Process Isolation**: External scripts run in separate processes

## Extension Points

### 1. Adding New Browser Functions

**Step 1: Extension** (`background.js`)
```javascript
actions.new_function = async (data) => {
    const result = await browser.someAPI.someFunction(data.param);
    return { success: true, result };
};
```

**Step 2: MCP Tool** (`fastmcp_tools.py`)
```python
@app.tool()
def new_function(param: str) -> str:
    """New browser function"""
    return send_browser_request({
        "action": "new_function",
        "data": {"param": param}
    })
```

### 2. Custom Script Integration

**Script Creation**
```bash
#!/bin/bash
echo "(function() { return 'Custom functionality'; })()"
```

**MCP Tool Usage**
```python
result = content_execute_predefined(
    tab_id=123,
    script_name="custom_script.sh",
    script_args=["arg1", "arg2"]
)
```

## Testing Architecture

### 1. Unit Tests
- **Server Components**: Test individual server functions
- **Protocol Validation**: Test message format validation
- **Utility Functions**: Test helper functions and utilities

### 2. Integration Tests
- **End-to-End**: Test complete MCP → Browser flow
- **Extension Communication**: Test WebSocket communication
- **Browser APIs**: Test actual browser function calls
- **Script Execution**: Test predefined script execution

### 3. Test Infrastructure
- **Centralized Fixtures**: Shared test setup in `conftest.py`
- **Port Coordination**: Isolated test ports prevent conflicts
- **Firefox Management**: Automated Firefox profile creation
- **Cleanup**: Automatic resource cleanup after tests

## Configuration Architecture

### 1. Server Configuration
```python
server = FoxMCPServer(
    host="localhost",      # Security: localhost only
    port=8765,            # WebSocket port
    mcp_port=3000,        # MCP server port
    start_mcp=True        # Enable MCP integration
)
```

### 2. Extension Configuration
- **storage.sync**: Persistent configuration across browser restarts
- **UI Configuration**: Real-time configuration via popup interface
- **Test Overrides**: Development configuration overrides
- **Auto-reconnection**: Automatic reconnection on setting changes

### 3. Environment Configuration
```bash
# Required for predefined scripts
export FOXMCP_EXT_SCRIPTS="/path/to/scripts"

# Optional server configuration
export FOXMCP_WEBSOCKET_PORT=8765
export FOXMCP_MCP_PORT=3000
export FOXMCP_DEBUG=1
```

## Deployment Architecture

### 1. Development Deployment
```bash
# Local development
make dev                # Setup environment
make build             # Build extension
make run-server        # Start server
```

### 2. Production Considerations
- **Extension Packaging**: XPI file for distribution
- **Server Packaging**: Python package with dependencies
- **Security Hardening**: Production security configuration
- **Monitoring**: Health checks and logging

### 3. Docker Deployment
```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8765 3000
CMD ["python", "server/server.py"]
```

## Monitoring and Observability

### 1. Logging
- **Structured Logging**: JSON-formatted logs
- **Log Levels**: DEBUG, INFO, WARNING, ERROR
- **Component Tracing**: Track requests across components
- **Error Tracking**: Comprehensive error logging

### 2. Metrics
- **Connection Metrics**: Active connections, reconnections
- **Request Metrics**: Request rate, response time, errors
- **Resource Metrics**: Memory usage, CPU usage
- **Custom Metrics**: Business-specific metrics

### 3. Health Checks
```bash
# WebSocket server health
curl http://localhost:8765/health

# MCP server health
curl http://localhost:3000/health

# Extension connection status
# Available through WebSocket /status endpoint
```

## Future Architecture Considerations

### 1. Multi-Browser Support
- **Browser Abstraction**: Common interface for different browsers
- **Protocol Standardization**: Browser-agnostic messaging
- **Extension Variants**: Browser-specific extension implementations

### 2. Distributed Architecture
- **Server Clustering**: Multiple server instances
- **Load Balancing**: Request distribution across servers
- **State Management**: Shared state across server instances

### 3. Enhanced Security
- **Authentication**: User authentication for MCP clients
- **Authorization**: Role-based access control
- **Encryption**: End-to-end encryption for sensitive data
- **Audit Logging**: Comprehensive audit trail