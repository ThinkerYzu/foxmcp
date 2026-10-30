# Server Configuration

Complete guide to configuring and running the FoxMCP server.

## Starting the Server

The Python distribution provides the `foxmcp` command (also run by
`uvx foxmcp`) with the same options below. Install from PyPI with uvx;
see the [README](../README.md#run-with-uvx-over-stdio). Source and GitHub archive
installations continue to use `python server/server.py`.

```bash
# Quick start (both WebSocket and MCP servers)
make run-server

# Custom configuration
python server/server.py --port 9000 --mcp-port 4000
python server/server.py --no-mcp  # WebSocket only, disable MCP server
python server/server.py --stdio   # MCP on stdin/stdout, for a client that launches it
python server/server.py --stdio --single-instance  # Share across chats; start automatically
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
  --single-instance    Automatically start or join a shared server (requires --stdio)
  --single-instance-idle-timeout SECONDS
                       Stop the shared server after this long without clients (default: 60)
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
  /path/to/foxmcp/server/server.py --stdio --single-instance
```

which writes a `.mcp.json` any MCP client can read:

```json
{
  "mcpServers": {
    "foxmcp": {
      "type": "stdio",
      "command": "/path/to/foxmcp/venv/bin/python",
      "args": ["/path/to/foxmcp/server/server.py", "--stdio", "--single-instance"],
      "env": {}
    }
  }
}
```

Name `venv/bin/python` rather than `python`: the server needs the virtual
environment's packages, and a client launches the command with its own
environment, not your shell's. On Windows the interpreter is
`venv\Scripts\python.exe`.

### Sharing one server across chats

`--stdio --single-instance` serves MCP in each chat's own process and forwards
browser commands to the server holding the Firefox connection. It queries
`/discovery` on the configured extension port, checks the forwarding protocol
version, then connects to `/proxy` on that same port. No discovery files, file
locks or internal MCP HTTP port are needed.

If no server is running, the client starts a detached background worker. Binding
the extension port elects the owner; a contender that loses retries discovery.
On Windows, the local WMI provider starts the worker outside the client's Job
Object so closing or killing the first chat leaves the others connected.

An automatically started worker stops 60 seconds after its last proxy leaves.
Change that interval with `--single-instance-idle-timeout SECONDS`; the first
launch sets it. A new chat during that interval reuses the Firefox connection.
If a manually started HTTP or plain stdio server already owns the port, clients
join it instead. Proxy disconnects never change a manual server's lifetime.

Each client keeps its own tool selection, `FOXMCP_EXT_SCRIPTS` directory and
local-file transfer service. Shared browser servers need a compatible forwarding
protocol, not identical tool settings or the same checkout. Monitors belong to
the proxy that started them and are stopped when it disconnects, including when
a reply creating the monitor arrives after the client has gone.

A crashed worker is replaced on the next launch; existing MCP clients need
reconnecting. Browser actions are never replayed. An older server without
`/discovery` and `/proxy` must be restarted before it can be shared. The
extension's reconnect delay still applies after a worker has stopped.

Worker logs are `instance-PORT.log` in `%LOCALAPPDATA%\foxmcp` on Windows,
or `$XDG_RUNTIME_DIR/foxmcp` (`~/.cache/foxmcp` when unset) on Unix.

### Plain stdio

The extension side does not change. The WebSocket server still listens on 8765,
the extension still connects to it, and every tool works as it does over HTTP.
Without `--single-instance`, three things are different:

- **No MCP HTTP listener.** Nothing serves port 3000, so `--mcp-port` is refused
  rather than silently ignored. `--no-mcp` is refused too, since it would leave
  stdio mode with nothing to serve.
- **The server lives as long as the client.** Closing the client ends the
  process, and the next client starts a new one. That has two consequences worth
  reading before you choose this mode: [One session at a
  time](#one-session-at-a-time) and [The reconnect gap](#the-reconnect-gap).
- **stdout carries the protocol.** All logging goes to stderr, where your client
  keeps its MCP server logs.

### One session at a time

Each profile's extension dials one WebSocket endpoint. A server can accept
[several Firefox profiles](#connecting-multiple-firefox-profiles-to-one-server).
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

Use `--stdio --single-instance` to share the browser server automatically.
A second independent server on another port would have nothing to serve,
because the extension is configured to dial one address.

A second plain `--stdio` process still collides with a standing HTTP server
on 8765. A `--stdio --single-instance` client joins that server instead. For several clients, use
`--stdio --single-instance` everywhere, or run one server in HTTP mode and point
them all at `http://localhost:3000/mcp/`.

### The reconnect gap

The extension opens the WebSocket connection, not the server. The server only
listens on 8765 and waits. Over HTTP that ordering never matters, because you
start the server once and leave it running: it is up before Firefox connects and
still up after. Under `--stdio` the server is the short-lived side, alive only
while your MCP client is, and the two have no way to coordinate.

Three things follow from that lifecycle.

**A tool call before the browser reconnects fails.** The server accepts MCP requests
as soon as your client launches it, but the extension is somewhere in its
retry cycle (one second by default) and has not connected yet. A tool call in that window
returns `No extension connection available` immediately rather than waiting for
the browser. Run it again.

**The extension keeps retrying at the configured interval.** Retries continue
every second by default, without a limit or a slower phase. Leaving Firefox
open and your editor closed is the normal case, so a server that comes back
is picked up on the next attempt:

```
12:00  editor exits, server dies
12:00  extension starts retrying, every 1s
13:00  editor starts, server comes back
13:00  extension connects on its next attempt, within 1s
```

**A request monitor does not survive the gap.** The extension clears every monitor
it holds, and everything they captured, whenever the connection to the server ends,
which under `--stdio` is each time your client exits. Start monitoring, read what it
caught, and stop it within the one client session; a `monitor_id` from an earlier
session answers `MONITOR_NOT_FOUND`. See
[How long a monitor lives](web-request-monitoring.md#how-long-a-monitor-lives).

Both the popup and Options accept a Reconnect Interval from 100 to 30000 ms.
A shorter interval picks up a new server sooner. There is no manual Reconnect
button; changes apply automatically after a short pause.

**Which mode to use.** It depends on how long your client lives, not on which
client it is.

A desktop client you open in the morning and leave running, such as Claude
Desktop, holds one server all day. The gap opens once, at startup, and the
extension has reconnected long before you ask for anything.

A terminal client is the opposite. Every `claude` invocation starts a server and
kills it on exit, so a morning of short sessions cycles the server all morning.
Each plain stdio session pays the first-call gap; the wait is bounded by the
configured interval regardless of how long the editor has been closed.

Use `--single-instance` to share an automatically started server, or keep an HTTP
server running if the browser connection should stay up between work sessions.

## Firefox container selection

Call `containers_list` for opaque `cookie_store_id` values scoped to the connected
profile. Supply an ID to `tabs_create` or `tabs_list`; the latter combines it with
any window filter. `firefox-default` is the normal store. Omission preserves
existing behavior. Named/default selection into private windows and explicit
`firefox-private` creation are refused; private filtering requires existing access.

The extension requires `contextualIdentities` and `cookies` permissions. Installing
it can enable Firefox containers. If the feature is disabled later, container
operations return `CONTAINERS_UNAVAILABLE`; FoxMCP does not change preferences.
Update the extension and server together, and restart existing shared workers
when upgrading from protocol ID 1 to 2. The tab-list response contract changed.

`--disable-tools containers` hides container discovery/management tools. Tab
selection remains available with known IDs. Containers are persistent profile
resources shared across clients; disconnects never remove them. Removal clears
stored site data and refuses open tabs. See [API reference](api-reference.md#firefox-containers).

## Connecting multiple Firefox profiles to one server

One FoxMCP server can serve several Firefox profiles at the same time. Each
profile runs its own extension and connects to the same WebSocket endpoint.
Use compatible server and extension builds in every profile; the current source
requires protocol 4. An older published build may need updating to support this
setup.

1. **Start one server.** For example, from a configured source checkout:

   ```bash
   python server/server.py --port 8765 --mcp-port 3000
   ```

   Leave it running. This example serves Firefox connections on port `8765`
   and MCP clients at `http://localhost:3000/mcp/`.

2. **Open each Firefox profile.** Keep each profile running in its own Firefox
   instance. Install or load the compatible FoxMCP extension separately in
   every profile.

3. **Point every extension at the same server.** In each profile, open the
   FoxMCP popup or Options and set **Host** to `localhost` and **Port** to
   `8765`. Valid edits save automatically. These fields address the browser
   WebSocket listener, not the MCP HTTP listener. If the server uses a custom
   `--port`, enter that same port in every profile. See
   [Configuring Extension](#configuring-extension).

4. **Check every profile is connected.** Each extension should show Connected
   after registration. If one does not, check its Host/Port and protocol
   diagnostics while keeping the server and that Firefox instance running.

5. **Discover profiles from your MCP client.** Connect the client to
   `http://localhost:3000/mcp/` and call `profiles_list(populate=True)`. Each
   connected profile appears with its own `profile_id`, name, windows and tabs.
   Pass the selected ID to browser tools, for example
   `tabs_list(profile_id=1)`, using an ID from the discovery result. See
   [Selecting a Firefox profile](#selecting-a-firefox-profile) for ID lifetimes
   and name lookup.

Several MCP clients can use this same server and discover the same profiles.
For clients that launch through stdio, use
[`--stdio --single-instance`](#serving-mcp-over-stdio) to share a browser server.
A separate server per Firefox profile is optional; see
[Multiple Server Instances](#multiple-server-instances) when separate endpoints
are desired.

## Selecting a Firefox profile

All connected profiles are visible through `profiles_list(populate=True)`, including
their windows and tabs. Pass the selected `profile_id` to every browser tool.
Window/tab IDs alone are insufficient: the same numbers can exist in several
profiles. There is no shared current-profile setting between agents.

The server reads Firefox's own names locally: a nonempty registered
`profiles.ini` name takes precedence over the profile-manager SQLite label.
Group metadata supplies names for profiles without a registered INI name.
Names retain their exact spelling and case. It matches the extension Origin UUID
against the profile's persisted extension UUID map. The server searches standard
Windows/macOS locations and Linux legacy, XDG, Snap and Flatpak locations. Custom
profile paths are found when referenced by metadata in those locations. On
Linux, if multiple paths share a UUID, the server reads `/proc/locks` and checks
their `.parentlock` device/inode identities. Exactly one held whole-file POSIX
write lock selects the running profile over stale copies. It never acquires a
lock or trusts leftover lock files or symlinks. Multiple active candidates,
unavailable activity evidence (including other platforms), or inaccessible
candidate lock files leave the name ambiguous. The server needs filesystem
access to this metadata; remote or sandboxed setups may leave names unknown.
Metadata is read-only and refreshed on discovery. Profiles without a resolvable name remain visible with
`name=null` and `name_error`. This requires Firefox metadata on the server's
machine; a separate native helper is not installed.

Protocol ID 4 requires updating both server and extension. The server assigns a
new integer ID on every connection, including extension reconnects. Rediscover
before using previously returned profile/window/tab IDs. Commands
never fall back to another connected profile.

## Reducing the Tool Surface

Every tool's description sits in an MCP client's context for the whole session,
whether or not the tool is ever called. With no predefined scripts listed, the
full set of 46 tools costs roughly 8,096 tokens. `--disable-tools` leaves a group unregistered, so a client never
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
| `profiles` | list | 77 |
| `tabs` | list, create, close, switch, move, capture_screenshot, group, ungroup, groups_update, groups_query | 2,188 |
| `containers` | list, create, update, remove | 624 |
| `bookmarks` | list, search, create, create_folder, update, move, delete | 1,131 |
| `windows` | list, get, get_current, create, close, focus, update | 1,361 |
| `requests` | start_monitoring, stop_monitoring, list_captured, get_content | 837 |
| `navigation` | back, forward, reload, go_to_url | 564 |
| `content` | get_text, get_html, execute_script, execute_predefined, load_file | 826 plus ~35 per listed script |
| `history` | query, get_recent, delete_item | 446 |
| `debug` | websocket_status | 42 |

The `content` figure is with `FOXMCP_EXT_SCRIPTS` unset. `content_execute_predefined`
lists every script in that directory in its description; see
[Telling AI Tools What a Script Does](scripts.md#telling-ai-tools-what-a-script-does).

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

`profiles_list(populate=True)` supplies profile, window and tab IDs even when
the `tabs` group is disabled. Keep discovery enabled, or provide the explicit
profile and native object IDs from another source. Every browser call still
requires `profile_id`; enabling an individual tool does not select a profile.
Without `tab_id`, the screenshot tool captures the visible tab within the
explicitly targeted profile.

### Setting both from the environment

Both lists can be set through the environment, for clients that launch the
server through a wrapper whose arguments you do not control:

```bash
export FOXMCP_DISABLE_TOOLS=bookmarks,history
export FOXMCP_ENABLE_TOOLS=tabs_capture_screenshot
```

`--disable-tools` overrides `FOXMCP_DISABLE_TOOLS`, and `--enable-tools`
overrides `FOXMCP_ENABLE_TOOLS`, when both are given.

## Local file transfers

The first `content_load_file` call starts a small HTTP listener owned by FoxMCP
on `127.0.0.1` and an automatically assigned port. It runs in both HTTP and
stdio modes; it is separate from the MCP HTTP listener. There is no port to
configure and no separate process to start.

Each transfer URL grants a single read and expires after 60 seconds if unused.
It contains a random token, with no filename or local directory. The server
opens only the file explicitly named by the MCP call, streams it in 64 KiB
blocks, disables caching, and closes unused grants and the listener on shutdown.
At most 32 transfers can be pending or active. Never share a transfer URL; it
authorizes that read. URLs and file bytes do not appear in MCP results.

The extension fetches in its background page, where Firefox can store large
response blobs in temporary disk files. The tab receives a File handle that
expires after five minutes or navigation. Private tabs are refused. Disk
spooling reduces retained memory but is not a hard peak-memory limit; queued
I/O and the receiving site's own code can still allocate buffers.

This tool reads through Python's OS permissions, independently of Firefox's
local-file permission toggle. All tools are enabled by default; disabling the
`content` group removes it, and `--enable-tools content_load_file` can keep it
individually. See [Loading local files](scripts.md#loading-local-files).

## Security Features

- **Localhost-only binding**: Both WebSocket and MCP servers bind to `localhost` only for security
- **Host enforcement**: Any attempt to bind to external interfaces (e.g., `0.0.0.0`) is automatically changed to `localhost` with a warning
- **Default secure configuration**: No configuration required for secure localhost-only operation

## Server Ports

- **WebSocket Port**: Default `8765` - Used for Firefox extension communication
- **MCP Port**: Default `3000` - Used for MCP client connections
- **File Transfer Port**: Assigned automatically on `127.0.0.1` at the first local-file load

## Configuring Extension

The persistent background owns configuration in `browser.storage.sync`. Popup
and Options use the same shared controller and background status contract.
The editable fields show saved user settings; connection status shows the
effective endpoint, including any test overrides.

### 1. Access Options

- **Options Page**: Right-click extension → "Manage Extension" → "Preferences"
- **Popup Interface**: Click extension icon for quick configuration
- Or go to `about:addons` → FoxMCP → "Preferences"

### 2. Configure Connection

- **Host**: Server hostname or IP address, without a scheme or port (default: `localhost`)
- **Port**: Integer from 1 to 65535 (default: `8765`)
- **Reconnect Interval (ms)**: Integer from 100 to 30000 (default: `1000`)
- **Test Configuration**: Built-in test override system for development

Both interfaces save valid edits automatically after a 500ms pause. Host and
Port are applied together; an incomplete endpoint does not replace the saved
address. The interval can be saved independently. Closing the popup does not
cancel an edit already queued in the background. Validation and storage errors
are shown beside the settings; the previous active settings remain in use.
Previously saved intervals between 30001 and 60000ms are reduced to 30000ms
when loaded. Other saved intervals in the supported range are preserved.

The extension constructs an unencrypted `ws://` address internally. Entering a
full URL, including `wss://`, in Host is invalid. The built-in server has no TLS
configuration. **Reset to Defaults** immediately saves and applies the defaults,
canceling queued debounce saves while preserving test overrides and unrelated
storage. An already executing write finishes before the reset write; its stale
completion cannot overwrite newer UI edits.
Reset is available in both views and does not open a native confirmation dialog.

Popup and Options share light/dark styling and a segmented **MCP Server URL**
field containing `ws://`, Host and Port. Configuration fields stay visible.
Routine save feedback is hidden; validation and storage errors remain visible.
Both footers show extension/server release diagnostics and the extension's
locally supported protocol ID. Protocol 4 is enforced during registration;
Connected means the server acknowledged this profile, not just that the socket
opened. An incompatible-peer error is shown in both views and stops retries.
Update both components and reload the extension to register again, or correct
the endpoint. Release-version mismatch is advisory when protocol IDs agree.

### 3. Features

- **Persistent settings**: Saved configuration survives browser restarts
- **Connection Status**: Real-time connection status monitoring
- **Status Indicators**: Both pages refresh connection state, the effective endpoint and the next retry every second without replacing unfinished input
- **Automatic Reconnection**: Effective endpoint changes reconnect; interval-only changes preserve a healthy connection
- **Configuration Preservation**: Test settings maintained during normal use

Editable fields show the saved user configuration; a separate server status
shows any active test overrides. Ping Timeout and Max Retry Attempts are no
longer settings. Old stored values are ignored, including a retry limit of zero.

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
2. **Load Firefox extension** in each profile you want to connect (see
   [multiple-profile setup](#connecting-multiple-firefox-profiles-to-one-server))
3. **Connect MCP client** to `http://localhost:3000/mcp/`

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

### Predefined Script Directory

```bash
# Set path to your custom scripts directory
export FOXMCP_EXT_SCRIPTS="/path/to/your/scripts"
```

### Optional Configuration

The server reads three environment variables. `FOXMCP_EXT_SCRIPTS` points at the
directory holding predefined scripts. The installed `foxmcp` console command
defaults to bundled examples when this variable is absent. An explicit value
replaces that default; an empty value disables scripts. Direct source/archive
startup still requires an explicit directory:

```bash
export FOXMCP_EXT_SCRIPTS=/path/to/predefined/
```

`FOXMCP_DISABLE_TOOLS` names tool groups to leave unregistered, and
`FOXMCP_ENABLE_TOOLS` names individual tools to register anyway — see
[Reducing the Tool Surface](#reducing-the-tool-surface).

Ports are set on the command line, not through the environment — see
[Multiple Server Instances](#multiple-server-instances).

## Multiple Server Instances

Use separate server instances when you want separate browser endpoints. To
connect several Firefox profiles to a shared endpoint, follow
[Connecting multiple Firefox profiles to one server](#connecting-multiple-firefox-profiles-to-one-server).

Each independent server needs its own WebSocket port and, when HTTP is enabled,
its own MCP port. Configure each Firefox profile's extension with the WebSocket
port of its chosen server, and each MCP client with that server's MCP endpoint.
For example:

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

WebSocket frame sizes, ping intervals and MCP concurrency are not exposed as
settings; the server uses the `websockets` and FastMCP defaults. See
[programmatic configuration](#programmatic-server-configuration) for supported
constructor arguments.

Two things you can change:

**Request timeout.** `send_request_and_wait` waits 30 seconds by default. Pass
`timeout` to override it for a slow call:

```python
# request contains a top-level profile_id from discovery.
response = await server.send_request_and_wait(request, timeout=60.0)
```

A timeout returns an error dict rather than raising, so callers must check for
`"error"` in the response.

**Extension reconnection.** The first connection is attempted after settings
load. When the socket closes or a connection attempt fails, the extension waits
`retryInterval` (1000 ms by default), then retries. Retries continue indefinitely
at that same interval, including after 50 attempts. Edit **Reconnect Interval
(ms)** in either interface to change the delay; no rebuild or Reconnect button
is needed. Updating the interval preserves a healthy socket and restarts an
already pending delay from the time the setting is applied.

The delay starts when WebSocket reports the closure, rather than when a physical
network problem begins. The server's WebSocket library uses its native Ping/Pong
keepalive; the removed extension Ping Timeout never controlled that mechanism.
This matters most under `--stdio`, where the server comes and goes with your
client: see [The reconnect gap](#the-reconnect-gap).

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

The built-in browser listener serves unencrypted WebSocket connections on
localhost. `FoxMCPServer` has no `ssl_cert`, `ssl_key`, `require_auth`,
`enable_cors` or `enable_debug` constructor settings. The CLI restricts the bind
address to localhost; the browser listener enforces loopback peers, local Host
headers and extension origins. See [protocol access checks](protocol.md#discovery-and-proxy-routes).

## Checking Server Health

There are no health, status, or metrics HTTP endpoints. Three things tell you whether
the pair is connected:

| Check | How | Tells you |
|---|---|---|
| `debug_websocket_status` | Call the MCP tool | Whether the extension is connected right now |
| Extension popup | Click the toolbar icon | Connection state, extension/server versions and advisory mismatch warnings |
| `make status` | From the project root | Whether port 8765 is in use |

The server logs connections, disconnections and version warnings to stderr, so running it in the
foreground is the quickest way to watch the socket come and go.

### Connection version warnings

Popup and Options display the extension release, connected server release and
supported protocol ID. A release-version mismatch warns without blocking tools
when both peers support protocol 4. Missing or invalid release versions are
reported as unavailable; they do not bypass the mandatory profile handshake.

A protocol mismatch is different: registration is refused, both views display
an update message, and the extension stops retrying that incompatible peer.
Update both components and reload the extension, or correct the endpoint.
Restart the server after updating its files. See
[version announcements](protocol.md#connection-version-announcement).
