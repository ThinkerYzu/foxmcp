# Server Configuration

Complete guide to configuring and running the FoxMCP server.

## Starting the Server

```bash
# Quick start (both WebSocket and MCP servers)
make run-server

# Custom configuration
python server/server.py --port 9000 --mcp-port 4000
python server/server.py --no-mcp  # WebSocket only, disable MCP server
python server/server.py --stdio   # MCP on stdin/stdout, for a client that launches it
```

## Command Line Options

```bash
python server/server.py [options]

Options:
  --host HOST          Host to bind to (default: localhost, security-enforced)
  --port PORT          WebSocket port (default: 8765)
  --mcp-port MCP_PORT  MCP server port (default: 3000)
  --no-mcp             Disable MCP server
  --stdio              Serve MCP on stdin/stdout instead of HTTP
  --disable-tools GROUP[,GROUP...]
                       Tool groups to leave unregistered (default: none)
  --enable-tools TOOL[,TOOL...]
                       Individual tools to register anyway (default: none)
  -h, --help           Show help message
```

## Serving MCP over stdio

By default the server offers MCP over HTTP, which means starting it yourself and
leaving it running. `--stdio` offers the same tools on stdin and stdout instead,
so an MCP client can launch the server itself and shut it down again when it
exits — the way most clients expect to manage a server.

**Claude Code**, from the directory you want it scoped to:

```bash
claude mcp add --scope project foxmcp -- /path/to/foxmcp/venv/bin/python \
  /path/to/foxmcp/server/server.py --stdio
```

which writes a `.mcp.json` any MCP client can read:

```json
{
  "mcpServers": {
    "foxmcp": {
      "type": "stdio",
      "command": "/path/to/foxmcp/venv/bin/python",
      "args": ["/path/to/foxmcp/server/server.py", "--stdio"],
      "env": {}
    }
  }
}
```

Name `venv/bin/python` rather than `python`: the server needs the virtual
environment's packages, and a client launches the command with its own
environment, not your shell's. On Windows the interpreter is
`venv\Scripts\python.exe`.

The extension side does not change. The WebSocket server still listens on 8765,
the extension still connects to it, and every tool works as it does over HTTP.
Three things are different:

- **No HTTP listener.** Nothing serves port 3000, so `--mcp-port` is refused
  rather than silently ignored. `--no-mcp` is refused too, since it would leave
  stdio mode with nothing to serve.
- **The server lives as long as the client.** Closing the client ends the
  process, and the next client starts a new one. That has two consequences worth
  reading before you choose this mode: [One session at a
  time](#one-session-at-a-time) and [The reconnect gap](#the-reconnect-gap).
- **stdout carries the protocol.** All logging goes to stderr, where your client
  keeps its MCP server logs.

### One session at a time

The extension dials a single WebSocket port, so a single server can serve it.
That is true in either mode. In HTTP mode it is a setup decision you make once.
Under `--stdio` it becomes a limit on how you work, because every client that
launches a server launches its own.

Two `claude` sessions in two terminals means two servers. The first binds 8765
and gets the browser. The second exits with an error naming the port, and that
client has no browser tools at all:

```
terminal 1:  claude  ->  server starts, binds 8765, extension attaches
terminal 2:  claude  ->  server exits: "Cannot listen on localhost:8765"
```

That is a normal way to work rather than a misconfiguration, and the server
cannot solve it. A second server on another port would have nothing to serve,
because the extension is configured to dial one address.

Mixing modes collides the same way: a standing HTTP-mode server holds 8765, so a
client's `--stdio` server cannot start. If you want several clients at once, run
one server in HTTP mode and point them all at `http://localhost:3000/mcp/`.

### The reconnect gap

The extension opens the WebSocket connection, not the server. The server only
listens on 8765 and waits. Over HTTP that ordering never matters, because you
start the server once and leave it running: it is up before Firefox connects and
still up after. Under `--stdio` the server is the short-lived side, alive only
while your MCP client is, and the two have no way to coordinate.

Two things follow, and neither is fixed in the server.

**A tool call in the first few seconds fails.** The server accepts MCP requests
as soon as your client launches it, but the extension is somewhere in its
five-second retry cycle and has not connected yet. A tool call in that window
returns `No extension connection available` immediately rather than waiting for
the browser. Run it again.

**The extension slows down without a server, but does not give up.** It retries
every Retry Interval for 50 attempts, about four minutes at the default five
seconds, and then every 30 seconds for as long as the server stays away. Leaving
Firefox open and your editor closed is the normal case, so a server that comes
back is picked up on the next attempt:

```
12:00  editor exits, server dies
12:00  extension starts retrying, every 5s
12:04  50 attempts spent, extension retries every 30s
13:00  editor starts, server comes back
13:00  extension connects on its next attempt, within 30s
```

**A request monitor does not survive the gap.** The extension clears every monitor
it holds, and everything they captured, whenever the connection to the server ends,
which under `--stdio` is each time your client exits. Start monitoring, read what it
caught, and stop it within the one client session; a `monitor_id` from an earlier
session answers `MONITOR_NOT_FOUND`. See
[How long a monitor lives](web-request-monitoring.md#how-long-a-monitor-lives).

To get it back, open the extension popup and press **Reconnect**, which resets
the counter and dials again (and clears any monitors, as any other end of the
connection does). Restarting the extension or Firefox does the same
thing the slow way.

**Raise the Retry Interval if you use this mode.** The extension's options page
accepts 1000 to 60000 ms. The 50-attempt budget is spent at whatever rate you
set, so 60000 ms buys 50 minutes of quiet instead of four:

| Retry Interval | Budget before it stops | Delay picking up a new server |
|---|---|---|
| 5000 ms (default) | 4 minutes | up to 5 seconds |
| 30000 ms | 25 minutes | up to 30 seconds |
| 60000 ms (max) | 50 minutes | up to 1 minute |

The cost is the third column: a longer interval means the extension takes longer
to notice the server your client just started, which widens the first problem
while narrowing the second.

**Which mode to use.** It depends on how long your client lives, not on which
client it is.

A desktop client you open in the morning and leave running, such as Claude
Desktop, holds one server all day. The gap opens once, at startup, and the
extension has reconnected long before you ask for anything.

A terminal client is the opposite. Every `claude` invocation starts a server and
kills it on exit, so a morning of short sessions cycles the server all morning.
Each session pays the first-call gap, and the time between sessions comes out of
the 50-attempt budget. This is the case the example command at the top of this
section configures, which is why it is worth saying plainly.

If that is how you work, HTTP mode avoids all of it: one server, started once,
outliving every client and every session, with no port to contend for.

## Reducing the Tool Surface

Every tool's description sits in an MCP client's context for the whole session,
whether or not the tool is ever called. The full set of 39 tools costs roughly
5,850 tokens. `--disable-tools` leaves a group unregistered, so a client never
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
| `tabs` | list, create, close, switch, move, capture_screenshot, group, ungroup, groups_update, groups_query | 2,166 |
| `windows` | list, get, get_current, create, close, focus, update | 949 |
| `requests` | start_monitoring, stop_monitoring, list_captured, get_content | 795 |
| `bookmarks` | list, search, create, create_folder, update, delete | 703 |
| `navigation` | back, forward, reload, go_to_url | 430 |
| `content` | get_text, get_html, execute_script, execute_predefined | 421 |
| `history` | query, get_recent, delete_item | 304 |
| `debug` | websocket_status | 78 |

All groups are on by default. An unrecognized group name is an error rather than
a warning, so a typo cannot silently leave the group enabled.

Disabling a group hides its tools; it does not restrict the extension, which
still holds the same browser permissions. This is a context-size option, not a
security boundary — see [architecture.md](architecture.md#security-architecture).

### Keeping one tool out of a disabled group

Sometimes a single tool is the reason to keep a group, and the rest of it is
dead weight — a screenshot of the page, without the nine tab tools that manage
tabs. `--enable-tools` names tools to register even though their group is
disabled:

```bash
# The page tools, plus a screenshot, and no tab management
python server/server.py --disable-tools tabs --enable-tools tabs_capture_screenshot
```

Names are the ones the client sees, as listed in
[api-reference.md](api-reference.md#available-mcp-tools). Naming a tool whose
group is enabled anyway does nothing, but a name that matches no tool is an
error, on the same reasoning as an unknown group: the symptom would otherwise be
the one tool you wanted quietly missing.

Most tools take a `tab_id` that in practice comes from `tabs_list`, so enabling
one of those on its own leaves you with a tool you have no way to address.
`tabs_capture_screenshot` is the exception that makes the example above work: it
captures the visible tab and takes no tab ID at all.

### Setting both from the environment

Both lists can be set through the environment, for clients that launch the
server through a wrapper whose arguments you do not control:

```bash
export FOXMCP_DISABLE_TOOLS=bookmarks,history
export FOXMCP_ENABLE_TOOLS=tabs_capture_screenshot
```

`--disable-tools` overrides `FOXMCP_DISABLE_TOOLS`, and `--enable-tools`
overrides `FOXMCP_ENABLE_TOOLS`, when both are given.

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

Or let the client start the server for you — see
[Serving MCP over stdio](#serving-mcp-over-stdio), where step 1 is the client's
job and step 3 does not apply.

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

The server reads three environment variables. `FOXMCP_EXT_SCRIPTS` points at the
directory holding predefined scripts:

```bash
export FOXMCP_EXT_SCRIPTS=/path/to/predefined/
```

`FOXMCP_DISABLE_TOOLS` names tool groups to leave unregistered, and
`FOXMCP_ENABLE_TOOLS` names individual tools to register anyway — see
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
`retryInterval` (5000 ms) and `maxRetries` (`-1`). Both are also editable from the
extension popup. Changing the source values requires a rebuild.

`-1` retries forever: 50 attempts at `retryInterval`, then one every 30 seconds
(`FAST_RETRIES` and `SLOW_RETRY_INTERVAL` in the same file). A positive value stops
after that many attempts, until you press **Reconnect** in the popup or restart the
extension. This matters most under `--stdio`, where the server comes and goes with
your client: see [The reconnect gap](#the-reconnect-gap).

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