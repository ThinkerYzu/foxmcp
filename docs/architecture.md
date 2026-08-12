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
│  - Windows      │
│  - History      │
│  - Bookmarks    │
│  - Navigation   │
│  - Content      │
│  - webRequest   │
└─────────────────┘
```

The Firefox extension acts as a bridge between WebExtensions APIs and MCP clients, enabling AI assistants and other tools to interact with browser functionality programmatically.

## Component Architecture

### 1. Firefox Extension

**Location**: `extension/`

**Manifest**: Manifest V2, extension ID `foxmcp@codemud.org`.

#### Background Script (`background.js`)
- **Persistent Background Page**: Declared `"persistent": true` in the manifest, so it runs for the lifetime of the browser session (this is a background page, not a service worker)
- **WebSocket Client**: Maintains the connection to the Python server and reconnects when it drops
- **Action Router**: Splits each incoming action on `.` and dispatches to the handler for that namespace
- **Response Manager**: Formats and sends responses back to the server

#### Content Script (`content.js`)
- **Page Injection**: Injected into all pages (`<all_urls>`) for content access
- **JavaScript Execution**: Executes custom scripts in page context
- **DOM Interaction**: Extracts text, HTML, and manipulates page content
- **Communication Bridge**: Relays data between page and background script

#### Popup Interface (`popup/`)
- **Configuration UI**: Connection settings
- **Real-time Status**: Live connection status and diagnostics
- **Storage Management**: Persists settings using `storage.sync`
- **Test Mode**: Override settings for development and testing

#### Options Page (`options.html`, `options.js`)
- Full settings page, opened in a tab (`options_ui.open_in_tab`), backed by the same `storage.sync` values as the popup

### 2. Python Server

**Location**: `server/`

#### WebSocket Server (`server.py`)
- **Connection Management**: Accepts the extension connection and tracks it as `self.extension_connection`
- **Request Correlation**: Maps request IDs to `asyncio.Future` objects in `self.pending_requests` and resolves them when the matching response arrives
- **Protocol Implementation**: WebSocket message protocol handling
- **Security**: Localhost-only binding
- **Lifecycle**: Graceful startup and shutdown, including cleanup of the extension connection

#### MCP Tools (`mcp_tools.py`)
- **MCP Tool Definitions**: 35 browser functions registered as MCP tools on a `FastMCP("FoxMCP")` instance
- **Parameter Validation**: Type-annotated tool signatures; FastMCP derives the schema
- **Response Formatting**: Each tool turns the raw browser response into a human-readable string
- **Error Handling**: Every tool checks for `error` in the response before reading data

### 3. Communication Protocols

#### WebSocket Protocol
```json
{
  "id": "unique-request-id",
  "type": "request|response|error",
  "action": "namespace.function",
  "data": {},
  "timestamp": "ISO-8601"
}
```

Actions are namespaced with a dot — `windows.get`, `tabs.list`, `bookmarks.create`, `requests.start_monitoring`. The prefix selects the handler in the extension. See [protocol.md](protocol.md) for the full specification.

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
    ↓ (WebSocket: content.execute_script)
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
- **Localhost Binding**: The server binds to `localhost` by default, and `--host` is forced back to localhost if given anything else
- **No External Access**: Not reachable from the network in the default configuration
- **Port Separation**: WebSocket and MCP listen on different ports

**Localhost binding excludes the network, not web pages.** A page the user visits runs inside their browser, so it can reach `127.0.0.1` — the same-origin policy does not stop it, and WebSocket handshakes are never preflighted. Each port handles this differently:

| Port | What stops a web page |
|---|---|
| Extension WebSocket | An origin allowlist: `websockets.serve(origins=[...])` accepts only `moz-extension://` origins and rejects anything else with a 403 during the handshake. See [Extension Connection Origin](#4-extension-connection-origin) |
| MCP HTTP | No CORS headers are sent, so preflighted requests are blocked; a `text/plain` request that would skip preflight is rejected for its content type; and the transport requires a session id that cross-origin JavaScript cannot read. These come from `fastmcp`/uvicorn rather than from FoxMCP, so `tests/integration/test_mcp_port_not_web_reachable.py` asserts them — a dependency upgrade that re-opens the port fails the suite |

Neither port authenticates local processes, which is deliberate — a process running as the user already has the browser profile and the script directory, so a shared secret between two components under that user's control would guard nothing.

### 2. Extension Security
- **Broad Permissions**: The extension requests `tabs`, `windows`, `history`, `bookmarks`, `activeTab`, `storage`, `webRequest`, and `<all_urls>`. This is deliberately wide — the extension exists to expose browser state — and it is the reason the server must stay on localhost. Treat an installed FoxMCP as granting its MCP client the same reach over the browser that you have.
- **Sandboxing**: Content scripts run in the standard isolated content-script context

### 3. Script Security

Enforced in `mcp_tools.py` before a predefined script runs:

- **Opt-in**: Scripts are disabled unless `FOXMCP_EXT_SCRIPTS` is set
- **Name Filtering**: Script names must match `^[a-zA-Z0-9._-]+$` and may not contain `/`, `\`, or `..`
- **Path Containment**: The resolved absolute path must stay inside the scripts directory
- **Executable Check**: The file must exist and be executable
- **Timeout Protection**: Scripts are killed after 30 seconds
- **Execution Isolation**: Scripts run as separate subprocesses
- **Audit Logging**: Every invocation is logged at `INFO` with script name, arguments and tab; every refusal and failure at `WARNING`. Arguments are truncated at 120 characters; the generated JavaScript is never logged, only its size. See [`scripts.md`](scripts.md#what-gets-logged)

### 4. Extension Connection Origin

Only browser extensions may connect to the WebSocket port. `server.py` passes an allowlist to `websockets.serve()`:

```python
EXTENSION_ORIGIN_PATTERN = re.compile(r'moz-extension://.+')
```

- **Scheme, not identity**: Firefox generates a per-install UUID, so the extension's origin differs on every profile — `moz-extension://8690897d-…` on one machine, something else on the next. Matching the scheme lets any legitimate install pass
- **Rejected during the handshake**: The connection never reaches `handle_extension_connection`, which matters because that function closes the existing extension connection to admit a new one — a rejection arriving any later would itself be a denial of service
- **Matched with `fullmatch()`**: The trailing `.+` is required; a bare prefix pattern rejects everything, including the extension
- **Rejections are logged** at warning level with the offending origin. The library logs them only in debug mode, which would make a legitimate extension that stopped connecting look identical to a server that was never reached

This does not stop a *malicious installed extension*, which can send a `moz-extension://` origin of its own. That is a different threat — it requires the user to install hostile software, at which point the browser is already compromised.

Tested in `tests/integration/test_connection_origin.py`. Test clients standing in for the extension must use `connect_as_extension()` from `tests/test_config.py`; a plain `websockets.connect()` is refused.

## Concurrency and Limits

### 1. Connection Management
- **Single Extension Connection**: One extension connection at a time. When a new one arrives, the server closes the existing connection first, which prevents connection races between two browsers or a stale socket.
- **MCP Clients**: Served by FastMCP. There is no per-client state — all clients share the one extension connection, and requests from different clients interleave.
- **Reconnection Logic**: The extension retries indefinitely by default (`maxRetries: -1`, subject to an absolute ceiling) and reconnects when settings change.

### 2. Request Handling
- **Async Processing**: All operations are asynchronous
- **Concurrent Requests**: Multiple requests can be in flight on the single socket at once; responses are matched by `id`, not by order, so a slow request does not block the others
- **Timeouts**: `send_request_and_wait` defaults to 30 seconds and **returns** an `{"error": ...}` dict on expiry rather than raising — callers must check for `error` before reading data
- **Cleanup**: Every exit path removes its entry from `pending_requests`

### 3. Known Limits
- **No queuing or retry**: A request sent while the extension is disconnected fails immediately; nothing is buffered for later delivery
- **No response caching**: Every tool call is a fresh round trip to the browser
- **No message size limit configured**: The `websockets` library default applies

## Extension Points

### 1. Adding New Browser Functions

Both halves must be changed. One without the other is a silent failure.

**Step 1: Extension** (`background.js`) — add a `case` to the handler for the namespace, or a new `handle<Namespace>Action` function plus a `case` in `handleMessage`'s router:

```javascript
case 'windows.new_function':
  if (!data.windowId) {
    sendError(id, 'INVALID_PARAMETER', 'windowId is required for windows.new_function');
    return;
  }
  const result = await browser.windows.someFunction(data.windowId);
  sendResponse(id, action, { result });
  break;
```

**Step 2: MCP Tool** (`mcp_tools.py`) — register the tool and build the request explicitly:

```python
@self.mcp.tool()
async def new_function(window_id: int) -> str:
    """New browser function

    Args:
        window_id: The ID of the window

    Returns:
        String describing the outcome
    """
    request = {
        "id": str(uuid.uuid4()),
        "type": "request",
        "action": "windows.new_function",
        "data": {"windowId": window_id},
        "timestamp": datetime.now().isoformat()
    }

    response = await self.websocket_server.send_request_and_wait(request)

    if "error" in response:
        return f"Error: {response['error']}"

    return f"Result: {response.get('data', {}).get('result')}"
```

**Step 3**: add the permission to `manifest.json` if the API needs one, document the action in [protocol.md](protocol.md) and the tool in [api-reference.md](api-reference.md), and add an integration test.

### 2. Custom Script Integration

A predefined script is a program whose **stdout is JavaScript**. The server runs it, then injects what it printed.

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
    script_args='["arg1", "arg2"]'
)
```

See [scripts.md](scripts.md) for the full guide.

## Testing Architecture

### 1. Unit Tests
- **Server Components**: Test individual server functions
- **Protocol Validation**: Test message format validation

### 2. Integration Tests
- **End-to-End**: Test complete MCP → Browser flow
- **Extension Communication**: Test WebSocket communication
- **Browser APIs**: Test actual browser function calls with real Firefox
- **Script Execution**: Test predefined script execution

### 3. Test Infrastructure
- **Centralized Fixtures**: Shared test setup in `conftest.py`
- **Port Coordination**: `port_coordinator.py` allocates ports dynamically, and `FoxMCPServer` detects pytest to avoid the default MCP port — so the suite can run while a development server is up
- **Firefox Management**: Automated temporary profile creation and extension installation via `setup_and_start_firefox()`
- **Cleanup**: Automatic resource cleanup after tests

## Configuration Architecture

### 1. Server Configuration

Constructed in code:

```python
server = FoxMCPServer(
    host="localhost",      # Security: localhost only
    port=8765,             # WebSocket port
    mcp_port=3000,         # MCP server port (None → 3000, or dynamic under pytest)
    start_mcp=True         # Enable MCP integration
)
```

Or from the command line:

```bash
python server/server.py --host localhost --port 8765 --mcp-port 3000
python server/server.py --no-mcp          # WebSocket only
```

### 2. Extension Configuration
- **storage.sync**: Persistent configuration across browser restarts
- **UI Configuration**: Real-time configuration via popup and options page
- **Test Overrides**: Development configuration overrides
- **Auto-reconnection**: Automatic reconnection on setting changes

### 3. Environment Configuration

```bash
# Required for predefined scripts; without it, the feature is disabled
export FOXMCP_EXT_SCRIPTS="/path/to/scripts"
```

This is the only environment variable the server reads. Host and ports are set through the constructor or the command-line flags above.

## Deployment

### 1. Development

```bash
make dev                # Setup environment
make build              # Build extension
make run-server         # Start server
```

### 2. Distribution
- **Extension Packaging**: XPI file, published to the Firefox Add-ons store and attached to GitHub releases
- **Server**: Run from the checkout with its virtual environment; `scripts/install-from-github.sh` sets this up for end users
- **Versioning**: Extension and server are released together — the WebSocket protocol is the compatibility boundary between them

### 3. Observability

Python `logging` at INFO level, in the default text format, to stderr. `claudebugzilla/start.sh` redirects this to a log file. There are no health endpoints, no metrics collection, and no structured log format.

## Future Architecture Considerations

These are not implemented. They are recorded as directions that have been considered, not as plans.

### 1. Multi-Browser Support
- **Browser Abstraction**: Common interface for different browsers
- **Protocol Standardization**: Browser-agnostic messaging
- **Extension Variants**: Browser-specific extension implementations

### 2. Production Hardening
- **Health Checks**: HTTP health endpoints for the WebSocket and MCP servers
- **Metrics**: Connection counts, request rates, response times, error rates
- **Structured Logging**: JSON-formatted logs with request tracing across components
- **Containerization**: A Docker image bundling the server and its dependencies

### 3. Enhanced Security
- **Authentication**: User authentication for MCP clients
- **Authorization**: Role-based access control over the tool surface
- **Audit Logging**: A record of which client invoked which tool
