<p align="center">
  <img src="https://raw.githubusercontent.com/ThinkerYzu/foxmcp/master/extension/icons/foxmcp-128.png" alt="FoxMCP fox logo" width="96" height="96">
</p>

# FoxMCP — Firefox Browser Automation via MCP

Connect an MCP-compatible AI assistant to Firefox. Manage tabs and windows,
read pages, upload local files, organize bookmarks, search history, and inspect
network requests.

FoxMCP has two parts: a Firefox extension and a local Python server. Your AI
client talks to the server, which sends commands to the extension.

**Privacy:** Connected AI clients can access your browser data and run page
scripts. Use trusted clients and consider a dedicated Firefox profile.
See [SECURITY.md](SECURITY.md) for the threat model.

## Quick start

PyPI packaging is prepared for the next release; `foxmcp` has not yet been
published to PyPI. Use the GitHub installer below today. The upcoming
[uvx setup](#run-with-uvx-next-release) removes the server installation directory.

You need Firefox, an MCP client, Python **3.10+** with `venv`, and the commands
`bash`, `curl`, `unzip`, and `sha256sum`. The commands below use a Bash shell.
On Debian/Ubuntu, install missing prerequisites with
`sudo apt install python3 python3-venv curl unzip coreutils`.

### 1. Install the server

Run this in a new directory where you want FoxMCP installed:

```bash
mkdir foxmcp && cd foxmcp
curl -fSL https://github.com/ThinkerYzu/foxmcp/releases/download/v1.5.0/install-from-github.sh | bash
```

The installer verifies the release archive checksums, creates `venv/`, installs
Python dependencies, and creates `start-foxmcp.sh`. It also installs example
scripts and a `CLAUDE.md` template, and offers to connect Claude Code.

For unattended setup, save the installer outside the target directory and run
`bash /path/to/install-from-github.sh --non-interactive` from an empty directory.

### 2. Install the Firefox extension

Open [FoxMCP on Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/foxmcp/)
and click **Add to Firefox**.

Use matching server and extension versions. Click the FoxMCP toolbar icon to see
a mismatch warning with both versions inside the popup. No automatic dialog or
notification opens. The server also logs a warning; older peers may show a version
as unavailable. Tools remain available while you update both together. Mozilla review can delay the Add-ons
version after a GitHub release; to try a version awaiting approval, use the
[temporary add-on instructions](docs/development.md#loading-in-firefox).

### 3. Start the server

From your installation directory:

```bash
./start-foxmcp.sh
```

Leave it running. Click the FoxMCP toolbar icon in Firefox and check that it shows
a connected status. The default ports are **8765** for the extension's WebSocket
connection and **3000** for the MCP HTTP endpoint.

### 4. Connect your AI client

For Claude Code, run this in another terminal:

```bash
claude mcp add --transport http foxmcp http://localhost:3000/mcp/
```

If the installer already connected Claude Code, skip that command.

For Codex, run:

```bash
codex mcp add foxmcp --url http://localhost:3000/mcp/
```

For another MCP client, add an HTTP server with URL
`http://localhost:3000/mcp/`.

### 5. Try it

Ask your assistant:

```text
List all open Firefox tabs.
Open https://example.org in a new tab.
Get the text from the current page.
Take a screenshot of the current tab.
```

To target a particular tab, right-click it in Firefox's tab bar and choose
**Tab ID = … (click to copy)**. Paste the copied `tab_id = …` into your request.
Tab IDs change when Firefox restarts.

## What you can do

| Area | Capabilities |
|---|---|
| Tabs and groups | List, open, close, switch, reorder, move between windows, group and ungroup; take screenshots |
| Windows | Create, close, focus, resize, position, minimize and maximize |
| Page content | Read text or HTML, execute JavaScript, run predefined scripts, load local files for uploads |
| Navigation | Go to a URL, go back or forward, reload |
| Bookmarks | List, search, create, update, move and delete bookmarks and folders |
| History | Search, list recent visits and delete entries |
| Network | Monitor requests by URL pattern; inspect headers and captured text response bodies |

Native tab groups require Firefox **139+**. Local file uploads use files readable
by the Python server; see [loading local files](docs/scripts.md#loading-local-files).
See the [API reference](docs/api-reference.md) for tool names and parameters.

## Other setup options

### Run with uvx (next release)

After the first PyPI release, install [uv](https://docs.astral.sh/uv/getting-started/installation/)
and the [Firefox extension](https://addons.mozilla.org/en-US/firefox/addon/foxmcp/).
For one Claude Code client, register a server it launches itself:

```bash
claude mcp add foxmcp -- uvx foxmcp --stdio
```

For several clients, start one shared HTTP server with `uvx foxmcp`, then use
[the HTTP registration commands](#4-connect-your-ai-client). The extension
connects to WebSocket port 8765 in either mode. Separate stdio clients still
conflict on that port, and the first browser call may need a retry while the
extension reconnects; see [stdio tradeoffs](docs/configuration.md#serving-mcp-over-stdio).

The packaged command includes and enables the example scripts. An explicit
`FOXMCP_EXT_SCRIPTS` overrides them; an empty value disables scripts. To match a
particular extension release, use `uvx --from foxmcp==VERSION foxmcp --stdio`,
replacing `VERSION` with that release's version. Python 3.10+ and Bash for the
shell examples are required.

### Install from source

You also need Git, `make`, and `zip` (on Debian/Ubuntu:
`sudo apt install git make zip`).

```bash
git clone https://github.com/ThinkerYzu/foxmcp.git
cd foxmcp
make install
make package
```

[Load the built extension in Firefox](docs/development.md#loading-in-firefox),
then start the server with `make run-server`. Continue with
[Connect your AI client](#4-connect-your-ai-client) above.

### Let your client start the server

Use stdio with `--single-instance` to start the server automatically and share it
across chats. Configure each client to launch
`venv/bin/python server/server.py --stdio --single-instance`, using absolute paths.
Clients discover and share the browser connection on the extension port. They
join an existing server or start a background worker automatically. Closing one
chat leaves the others connected. Automatic workers stop after 60 seconds without
clients; manually started servers keep running. On Windows, use `venv\Scripts\python.exe`.
See [stdio setup](docs/configuration.md#serving-mcp-over-stdio).

## Configuration

Click the FoxMCP toolbar icon to change extension connection settings. If you
change the WebSocket port, change it on both the extension and the server.

For manual startup, run these from the installation directory:

```bash
# Custom WebSocket and MCP HTTP ports
venv/bin/python server/server.py --port 9000 --mcp-port 4000

# Hide tool groups from clients
venv/bin/python server/server.py --disable-tools bookmarks,history

# Hide a group but keep its screenshot tool
venv/bin/python server/server.py --disable-tools tabs --enable-tools tabs_capture_screenshot
```

All **45 tools** are enabled by default. Available groups are `windows`, `tabs`,
`containers`, `bookmarks`, `navigation`, `content`, `requests`, `history`, and `debug`.
See [configuration](docs/configuration.md) for client examples and other options.

## Firefox containers

Use `containers_list` to discover named containers and their opaque
`cookie_store_id` values. Pass one to `tabs_create` to open in that container,
or to `tabs_list` to filter. Use `firefox-default` for normal browsing. Omission
keeps existing behavior; invalid selections fail without opening a fallback tab.

`containers_create`, `containers_update` and `containers_remove` manage persistent
profile containers. Removal clears stored site data and refuses containers with
open tabs. Containers survive client disconnects. See the
[API reference](docs/api-reference.md#firefox-containers) for details.

The extension requires `contextualIdentities` and `cookies` permissions for
container APIs and tab selection. Installation can enable Firefox containers;
subsequent disabling is respected. Update both extension and server together.

## Predefined scripts

External executable scripts can generate JavaScript for FoxMCP to run in a tab.
The release installer configures the examples in `predefined-scripts/`; the
packaged `foxmcp` command uses its bundled examples by default. Both include
DOM summaries, YouTube controls, calendar extraction, and a file-input helper.
Ask your assistant which predefined scripts are available.

For your own scripts, set `FOXMCP_EXT_SCRIPTS` to their directory **before starting
the server**. For example, save this as `get-title.sh` in that directory and run
`chmod +x get-title.sh`:

```bash
#!/bin/bash
# Return the current page title.
echo 'document.title'
```

Then ask your assistant to run `get-title.sh` in a tab. Restart the server after
adding scripts to refresh the list shown to clients. See the
[script guide](docs/scripts.md) for arguments, setup, and file upload examples.

## Troubleshooting

| Problem | Check |
|---|---|
| Extension disconnected | Start the server and check the host/port in the FoxMCP popup. `curl -i http://localhost:8765` should return **426 Upgrade Required**. |
| MCP client cannot connect | Check its URL. `curl -i http://localhost:3000/mcp/` should return a **307** redirect when using HTTP mode. |
| Server logs “address already in use” | Another service owns a port. FoxMCP can keep running even when its MCP listener fails; use [different ports](docs/development.md#port-conflicts) and check both listeners. |
| Server reports missing Python packages | Use `venv/bin/python`, or the provided startup script. |
| Built extension will not install | Follow the [Firefox channel and signing guidance](docs/development.md#loading-in-firefox). |

For other errors, run the server in the foreground and inspect its output.

## Documentation and development

- [Configuration](docs/configuration.md) — ports, MCP clients, tool selection and reconnect behavior
- [API reference](docs/api-reference.md) — all tools and parameters
- [Scripts](docs/scripts.md) — reusable automation and local file uploads
- [Request monitoring](docs/web-request-monitoring.md) — filters, response bodies and monitor lifetime
- [Development](docs/development.md) — extension installation, builds, tests and release workflow
- [Architecture](docs/architecture.md) and [protocol](docs/protocol.md) — how the components communicate
- [Release notes](RELEASES.md) and [changelog](CHANGELOG.md) — updates and upgrade instructions
- [Security](SECURITY.md) — trust boundaries and vulnerability reporting

To contribute, fork the repository, run `make setup` and `make test`, and submit
a pull request with tests for new behavior.

Licensed under the [MIT License](LICENSE).
