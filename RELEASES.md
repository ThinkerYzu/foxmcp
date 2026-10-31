# FoxMCP Releases

This document provides release notes and upgrade instructions for FoxMCP.

For the full, entry-by-entry record of every release, see
[CHANGELOG.md](CHANGELOG.md) — that is the file a release's GitHub notes are
generated from.

## v1.6.0 - Multiple profiles and Windows installation (prepared 2026-10-30)

### Publication status

Prepared locally; not tagged or published. The latest published release is
v1.5.0. Release download URLs for v1.6.0 become available after publication.

### Highlights

- Concurrent Firefox profiles, `profiles_list`, and explicit routing for all
  browser tools. Profile names are resolved automatically from local metadata;
  unavailable or ambiguous names stay unknown.
- Shared popup/Options settings with automatic saving, endpoint validation and
  reliable reconnects. Configuration stays visible and errors remain actionable.
- Windows PowerShell installation, Git Bash/Python script execution and hidden
  background workers. Both PowerShell installers ship as GitHub release assets.
- Windows CI covers Python 3.10/3.14 and PowerShell 5.1/7, including clean
  installation, argument handling, HTTP and direct-Python stdio.

### Upgrade from v1.5.0

**Existing tool calls must change.** Version 1.6.0 was selected for this release;
its profile-target requirement is a breaking API change. Update the Python
server and Firefox extension together, restart shared workers, and refresh MCP
clients' cached tool schemas. Python 3.10+ remains required; tab groups require
Firefox 139+. No new extension permissions are added by this release.

Call `profiles_list` and pass the selected integer `profile_id` to every browser
tool, even with a single connected profile. IDs belong to connections: reconnects
get fresh IDs and server restarts reset the sequence. Rediscover targets after
either event. Names are labels, never routing keys. See
[profile selection](docs/configuration.md#selecting-a-firefox-profile).

On Windows, download `install-from-github.ps1` and `install-xpi.ps1` from the same
release and keep them together outside the empty installation directory.
The generated `start-foxmcp.ps1` helper starts HTTP. For MCP stdio, configure the
client to launch `venv\Scripts\python.exe` with the absolute installed
`server\server.py` path and `--stdio`. Set `FOXMCP_EXT_SCRIPTS` to the installed
`predefined-scripts` directory for those examples. Shell scripts require Git Bash
or an absolute `FOXMCP_BASH` override. See [Windows setup](README.md#quick-start).

### Protocol compatibility review

Baseline: released `v1.5.0` at
`a749922d912a91d16790a316b372a2b598dee207`. Reviewed through `f6a1a6e` plus
this release's metadata, documentation and protocol-number correction. Released protocol ID is **2**;
the candidate uses one release-level increase to **3**:

- Extension `hello` is now mandatory, validates protocol compatibility, and
  completes with server `ready`. Legacy, malformed or incompatible handshakes
  close with code 1008 instead of continuing with advisory diagnostics.
- Existing browser requests through MCP and `/proxy` require explicit positive
  integer `profile_id` routing. The server assigns IDs, strips them before
  forwarding to Firefox, and adds connection/routing metadata to results.
  The extension never generates, stores or receives these IDs.
- Connections, pending responses and request monitors are isolated per profile.
  Disconnect errors and cleanup affect only the owning connection; stale replies
  cannot satisfy new requests, and commands never fall back to another profile.
- Connection status and diagnostics describe multiple profiles. `profiles_list`
  and `proxy.profiles` add discovery; profile-scoped native IDs can collide
  without crossing profile boundaries.
- Settings/reconnect behavior changes preserve browser action payloads. Legacy
  test storage projection is retained. No existing browser action is removed.

These changed existing contracts require exactly one increase from released
ID 2 to 3. All incompatible changes accumulated since v1.5.0 share that single
increment. The temporary development ID 4 was never released and is superseded
by 3; restart development workers and update both development peers as well.
Name lookup, Windows process fixes and release metadata introduce no further
extension/server contract change. Both implementations and pairing tests enforce
3. See [protocol policy](docs/protocol.md#protocol-id-compatibility-policy).

### Preparation gates

The pre-correction source baseline's [post-landing CI](https://github.com/ThinkerYzu/foxmcp/actions/runs/41153037451)
passed, including native Windows, the full suite and packaged HTTP/stdio checks.
Local candidate checks pass: all eight version fields, 506 unit tests with no
skips and full unit-module collection, fatal Python lint, 183 local documentation
links/anchors, archive checksums and XPI/server version metadata. Wheel and sdist
builds pass metadata validation and `twine check`. All four package types carry
protocol ID 3. Ten focused integration tests pass without skips, including real
Firefox handshakes, settings/reconnects, multiple profiles and proxy routing.
Forwarder compatibility tests reject released ID 2 and candidate ID 3 in both
directions.

The release candidate still requires its own successful non-publishing workflow
rehearsal before tagging. Publication must verify GitHub assets/checksums and
provenance, both Windows script download URLs, PyPI distributions and AMO status
separately. Signed-extension testing in standard Firefox remains a post-signing
check; Windows CI does not validate a signed extension in real Windows Firefox.

## v1.5.0 - Containers, shared connections and Python packaging (2026-10-25)

### Publication status

- [GitHub release](https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.5.0)
  published. Public XPI, server archive, wheel and source distribution passed
  checksum and provenance verification against the tagged workflow and commit.
- Mozilla accepted version 6620640 for review. The public AMO listing still
  serves v1.4.0; signed v1.5.0 upgrade verification awaits approval.
- [PyPI v1.5.0](https://pypi.org/project/foxmcp/1.5.0/) published after configuring
  the owning account's Trusted Publisher and retrying the PyPI job. Wheel and
  source distribution match the verified GitHub release byte for byte. Fresh
  uvx installation, CLI startup and stdio discovery of all 45 tools passed.

### Highlights

- Discover, create, update and remove Firefox containers; select a cookie store
  when opening a tab and filter tab listings by store. Existing page tools work
  with the selected tab IDs.
- `--stdio --single-instance` lets concurrent clients share one Firefox
  connection. Clients join an existing server or start a worker that exits after
  the last proxy disconnects and the idle interval expires.
- Installable Python wheel/sdist and a `foxmcp` console command, prepared for
  first PyPI publication. GitHub archive and source installs remain supported.
- Extension/server version diagnostics in the toolbar popup and server logs.
- Background-tab screenshots through `tabs_capture_screenshot(tab_id=...)`.
- Original fox icons, README logo and repository social preview artwork.

### Upgrade from v1.4.0

Update both server and extension. Python 3.10+ is required; native tab groups
require Firefox 139+. The extension adds `contextualIdentities` and `cookies`.
Review any Firefox update prompt and enable the updated extension before testing
containers. Containers are profile state and survive client/server restarts.
Removing a container clears its stored site data and requires closing its tabs.

The forwarding protocol ships as ID 2. Restart old shared workers before joining
with updated clients. `--single-instance` remains an opt-in stdio mode; ordinary
HTTP and dedicated stdio remain available. Version warnings are advisory.

Install the server with `uvx --from foxmcp==1.5.0 foxmcp` or the GitHub
installer. The known HTTP bind failure issue remains: if the MCP port is occupied,
use an unused `--mcp-port`.
See [development troubleshooting](docs/development.md#troubleshooting).

### Protocol compatibility review

Baseline: released `v1.4.0` at `ed2ac3819aec89506ce6a5214cef610f2a5901fb`.
That tag predates checked forwarding IDs. Forwarding introduced ID 1 during
unreleased development; the candidate uses **ID 2**, retaining the required
increase for changed existing contracts:

- `tabs.list` includes cookie-store metadata and accepts a store filter. The
  server checks metadata instead of assuming the default store for legacy peers.
- Pending browser requests now fail promptly when their extension disconnects.
- The extension listener checks route, loopback peer and Host alongside its
  existing extension-Origin restriction; different loopback forwarding ports work.

New container, explicit-store creation and background-screenshot actions,
optional version greetings and new local proxy/discovery routes are additive.
No existing action is removed. The full changed contract is covered by ID 2;
no further increase is required for packaging, icons or release metadata.
Extension hello remains advisory and does not enforce the forwarding ID.
See [protocol policy](docs/protocol.md#protocol-id-compatibility-policy).

### Preparation gates

Before tagging, require successful full regression, final-archive HTTP/stdio
smoke checks, clean wheel/sdist installs, a non-publishing workflow rehearsal
and the recorded protocol review.

Publication is staged: GitHub publishes tested, attested artifacts first; AMO
submission and PyPI publication follow in separate jobs. Verify each channel
independently. PyPI requires the owning account's Trusted Publisher; a setup
failure there does not undo GitHub publication and can be retried after setup.

The workflow obtains a signed extension through AMO after GitHub publication.
Rehearse the signed standard-Firefox permission upgrade and enterprise-policy
behavior when that artifact is available, and record the result separately.
The temporary browser test confirms local loading, not signed upgrade prompts.

## v1.4.0 - Local files, tab groups and release verification (2026-10-18)

### Highlights

- `content_load_file` loads a server-local file into a tab for upload/import scripts,
  preserving its basename and allowing a MIME override. The predefined
  `set-file-input.py` example assigns it to an input and dispatches events.
- Native tab groups, `bookmarks_move`, and a tab-menu action to copy the tab ID.
- Predefined scripts appear in the tool schema; failed scripts return stdout as
  well as stderr to help callers correct their arguments.
- Reconnection, window focus, bookmark validation and request-capture fixes,
  including tiny response bodies and overlapping monitors.
- Release gates test the exact ZIP/XPI through clean installation and all 41 tools
  over HTTP and stdio. The installer verifies archive checksums and HTTP errors.

### Upgrade from v1.3.0

Update both the Python server and Firefox extension. Python 3.10+ is required;
native tab groups require Firefox 139+. The extension adds `tabGroups`, `menus`
and `clipboardWrite`; Firefox may ask existing users to approve the clipboard
permission before the updated add-on is enabled.

Local file loading uses the Python server's filesystem permissions and is enabled
with the `content` group by default. Handles last five minutes or until navigation;
loading does not select an input or submit a form. See
[Loading local files](docs/scripts.md#loading-local-files).

Request monitors stop when their owning client disconnects, and losing the
extension/server connection clears monitors and captured data. With Max Retries
set to `-1`, the extension now keeps reconnecting indefinitely, slowing down after
50 attempts; the old four-minute reconnect limit no longer applies.

The full change list and upgrade notes are in
[CHANGELOG.md](CHANGELOG.md#140---2026-10-18).

## v1.3.0 - Launching the Server From Your Client (2026-09-07)

### ✨ Feature Release

Two new ways to control how the server presents itself to an MCP client. Nothing
is removed, and an existing setup keeps working untouched.

**The extension is unchanged from v1.2.0.** This release touches only the Python
server, so the add-on you already have is the right one. If you installed from
addons.mozilla.org, there is nothing to update there.

### `--stdio` lets your MCP client start the server

Most MCP clients, Claude Code and Claude Desktop among them, launch their servers
as child processes and talk to them over pipes. FoxMCP only ever listened on
HTTP, so it had to be started by hand and left running, which is what
[issue #3](https://github.com/ThinkerYzu/foxmcp/issues/3) asked about. This is now
enough:

```bash
claude mcp add --scope project foxmcp -- /path/to/venv/bin/python /path/to/server/server.py --stdio
```

The server then lives and dies with the client. The browser half does not change:
the WebSocket still listens on 8765, and every tool behaves as it does over HTTP.

Two costs come with the mode, both following from the extension being the side
that opens the WebSocket connection.

| Cost | What you see | What to do about it |
|---|---|---|
| One session at a time | A second `claude` session has no browser tools at all, because its own server cannot bind port 8765 | Use HTTP mode when you run more than one session at once |
| The reconnect gap | After roughly four minutes with no server to reach, the extension stops trying | Set Retry Interval to 60000 ms, which buys 50 minutes, or press **Reconnect** in the popup |

Neither is a misconfiguration you can settle by editing a file, so prefer HTTP if
either one would bite. See
[Serving MCP over stdio](docs/configuration.md#serving-mcp-over-stdio),
[One session at a time](docs/configuration.md#one-session-at-a-time) and
[The reconnect gap](docs/configuration.md#the-reconnect-gap).

### `--enable-tools` keeps one tool out of a group you disabled

`--disable-tools`, added in v1.2.0, works a group at a time, and sometimes a
single tool in the group is the one worth its tokens.
[Issue #6](https://github.com/ThinkerYzu/foxmcp/issues/6) asked for a screenshot
of the page without the five tab-management tools that come with it:

```bash
python server/server.py --disable-tools tabs --enable-tools tabs_capture_screenshot
```

`FOXMCP_ENABLE_TOOLS` does the same for clients that launch the server through a
wrapper whose arguments you cannot control. Names are the ones your client sees,
and one that matches no tool is an error rather than a warning, since otherwise
the symptom is the single tool you asked for quietly missing.

`tabs_capture_screenshot` makes the good example because it captures the visible
tab and takes no tab ID, so it stands on its own. Most other tools take a
`tab_id` that in practice comes from `tabs_list`, and enabling one of those alone
leaves you nothing to address it with. See
[Keeping one tool out of a disabled group](docs/configuration.md#keeping-one-tool-out-of-a-disabled-group).

### 📋 Upgrading

Replace the server and restart it. Leave the extension alone.

```bash
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.3.0/install-from-github.sh | bash
```

If you switch to `--stdio`, drop the `--mcp-port` and `--no-mcp` arguments from
your old command line. Passing either alongside `--stdio` is refused rather than
ignored, because in stdio mode no HTTP listener is opened for them to configure.

## v1.2.0 - Security and Context (2026-08-14)

### 🔒 Security Release

**Upgrade if you run any earlier version.** Before v1.2.0 the extension WebSocket
accepted any connection on its localhost port, and WebSocket handshakes are exempt
from the same-origin policy — so any web page you visited could take the connection
and answer browser requests on the extension's behalf. The server now accepts only
`moz-extension://` origins.

### ✨ What else is in it

- **Response bodies are actually captured.** They never were: the old approach
  overrode `window.fetch` from a content script, which Firefox silently refuses.
  Bodies now come from the response stream, and cover the document load as well.
- **`--disable-tools` shrinks the tool surface** your MCP client carries, one group
  at a time — `windows`, `tabs`, `bookmarks`, `navigation`, `content`, `requests`,
  `history`, `debug`. Every group stays on by default.
- **`tabs_move`**, plus a `tabs_list` that can finally see other windows.
- **Releases are built in public** by GitHub Actions and carry a signed provenance
  attestation: `gh attestation verify 'foxmcp@codemud.org.xpi' --repo ThinkerYzu/foxmcp`.
  That needs GitHub CLI **2.49 or newer**. An older `gh` has no `attestation`
  subcommand and answers by printing its list of commands, which reads as a missing
  attestation rather than an out-of-date client — Ubuntu 26.04 still packages 2.46,
  so install from [cli.github.com](https://cli.github.com) if apt is your source.
  The attestation can also be read straight from the API, with no `gh` at all:
  `curl -s https://api.github.com/repos/ThinkerYzu/foxmcp/attestations/sha256:$(sha256sum 'foxmcp@codemud.org.xpi' | cut -d' ' -f1)`.

### ⚠️ Breaking

`get_last_focused_window` is removed. It returned the same window as
`get_current_window` in every case this extension can produce, so no behavior
changes — but a client that names the old tool gets an error. Use
`get_current_window`.

### 📋 Upgrading

Install the new XPI as you installed the old one, and restart the server. The
extension asks for one new permission, `webRequestBlocking`, which is what Firefox
requires before it will hand an extension the response stream; nothing blocks,
cancels or rewrites a request. It has no description string in Gecko, so it raises
no new install prompt.

## v1.1.0 - Enhanced Automation (2025-10-26)

### 🚀 Feature Release

**FoxMCP v1.1.0** adds powerful new capabilities for web request monitoring, enhanced bookmark management, and ready-to-use automation scripts. This release builds on the solid v1.0.0 foundation with practical features for common automation tasks.

### ✨ New Features

#### **Web Request Monitoring API**
Monitor and capture HTTP requests/responses in real-time:
- **Start Monitoring**: `requests_start_monitoring()` - Begin capturing network activity
- **List Captured Data**: `requests_list_captured()` - Retrieve captured requests/responses
- **Stop Monitoring**: `requests_stop_monitoring()` - End capture session and cleanup
- **Two-Phase Workflow**: Start monitoring → perform actions → retrieve data → stop
- **Use Cases**: Debug API calls, analyze network traffic, validate request patterns

#### **Enhanced Bookmark Management**
New bookmark operations for better organization:
- **Folder Creation**: Create bookmark folders with proper hierarchy support
- **Update Bookmarks**: Modify existing bookmark titles, URLs, and locations
- **Improved Reliability**: Fixed integration test failures and enhanced error handling

#### **Predefined Scripts Collection**
Ready-to-use scripts for common automation tasks:

**YouTube Control** (`youtube-play-pause.sh`)
- Play, pause, or toggle YouTube videos programmatically
- Returns video state, current time, and duration
- Example: `content_execute_predefined(tab_id, "youtube-play-pause.sh", "[]")`

**DOM Simplification** (`dom-summarize.sh`)
- Simplify complex DOM trees for AI agent understanding
- Extract visible interactive elements with persistent IDs
- Supports viewport-only filtering and position data
- Example: `content_execute_predefined(tab_id, "dom-summarize.sh", "[\"onscreen\"]")`

**Google Calendar Integration** (3 scripts)
- `gcal-cal-event-js.sh`: Extract specific event details by title, day, and time
- `gcal-daily-events-js.sh`: Get all events for a specific day
- `gcal-monthly-events-js.sh`: Extract entire month view with statistics
- Perfect for calendar automation and event management

#### **Content API Enhancement**
- **max_length Parameter**: Optional parameter for `content_get_text` tool
- **Context Management**: Truncate large text extractions to fit AI context windows
- **Flexible Extraction**: Choose between full text or length-limited summaries

#### **Installation Improvements**
- **Firefox Add-ons Store**: Official installation option now available
- **Simplified Instructions**: Single-command installation process
- **Script Inclusion**: Installation script now downloads all predefined scripts
- **Better Documentation**: Enhanced setup guides and troubleshooting

### 🐛 Bug Fixes

#### **Critical History Fixes**
- **Query Filtering**: Fixed parameter mismatch preventing history search filtering
  - Extension now correctly reads `query` parameter
  - Non-matching entries properly excluded from results
  - All tests updated to use correct parameter names

- **Timestamp Display**: Fixed "Unknown time" in history MCP tools
  - Tools now correctly read `lastVisitTime` field
  - AI agents see actual timestamps (milliseconds since epoch)
  - Affects `history_query` and `history_get_recent` tools

#### **Other Fixes**
- **Bookmark Tests**: Fixed intermittent bookmark management test failures
- **Calendar Script**: Fixed gcal-daily-events-js.sh month detection
- **Profile Cache**: Clear cache after packaging to prevent stale data

### 🔧 Improvements

#### **Testing & Quality**
- **211 Total Tests**: 59 unit + 152 integration tests, all passing
- **History Validation**: Comprehensive timestamp validation in all tests
- **Query Testing**: New tests verify filtering excludes non-matching entries
- **100% Pass Rate**: All tests enabled and maintaining quality standards

#### **Developer Experience**
- **Debug Logging**: Configurable `ENABLE_DEBUG_LOGGING_TO_SERVER` setting
- **Enhanced Documentation**: Comprehensive CLAUDE.md updates
- **Script Documentation**: Detailed usage examples for all predefined scripts
- **Better Error Messages**: Improved debugging and troubleshooting

### 📦 Installation

#### **Upgrade from v1.0.0**
```bash
# Pull latest changes
git pull origin master

# Rebuild extension and server
make clean
make package

# Clear profile cache
rm -rf dist/profile-cache/*

# Reinstall extension
./scripts/install-xpi.sh /path/to/firefox/profile

# Restart Firefox and server
```

#### **Fresh Installation**
```bash
# One-command installation (installs v1.1.0)
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/install-from-github.sh | bash
```

#### **Package Downloads**
- **Firefox Extension**: [foxmcp@codemud.org.xpi](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/foxmcp@codemud.org.xpi)
- **Server Package**: [foxmcp-server.zip](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/foxmcp-server.zip)
- **Source Code**: [v1.1.0.tar.gz](https://github.com/ThinkerYzu/foxmcp/archive/v1.1.0.tar.gz)

### 🎯 Use Cases

#### **Network Analysis**
```python
# Start monitoring network requests
requests_start_monitoring()

# Perform actions that trigger requests
tabs_navigate(tab_id, "https://example.org/api")

# Retrieve captured data
data = requests_list_captured()

# Stop monitoring
requests_stop_monitoring()
```

#### **Calendar Automation**
```python
# Get today's meetings (if today is the 26th)
events = content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"26\"]")

# Get specific event details
event = content_execute_predefined(
    tab_id,
    "gcal-cal-event-js.sh",
    "[\"Team Standup\", \"26\", \"9:00am\"]"
)
```

#### **YouTube Control**
```python
# Toggle play/pause
result = content_execute_predefined(tab_id, "youtube-play-pause.sh", "[]")

# Explicitly pause
result = content_execute_predefined(tab_id, "youtube-play-pause.sh", "[\"pause\"]")
```

### 🔄 Breaking Changes

**None** - This release is fully backward compatible with v1.0.0.

### 📊 Statistics

- **25 Commits** since v1.0.0
- **5 New APIs** (web request monitoring)
- **5 Predefined Scripts** included
- **40+ Test Additions** for new features
- **2 Critical Fixes** (history timestamp and filtering)

### 🌟 Community Highlights

This release includes contributions and feedback addressing:
- Request monitoring for debugging workflows
- Calendar integration for productivity automation
- YouTube control for media management
- History fixes improving search reliability

### 📚 Documentation Updates

- **README.md**: Updated with v1.1.0 features and predefined scripts
- **CLAUDE.md**: Comprehensive predefined scripts documentation
- **Protocol Docs**: Web request monitoring message formats
- **Installation Guide**: Simplified single-command setup

### 🚧 Future Roadmap

Building on v1.1.0, planned enhancements include:
- **Complete Web Request API**: Full request/response inspection and filtering
- **Downloads Management**: Download tracking and control
- **Cookie Management**: Comprehensive cookie operations
- **Enhanced MCP Features**: Batch operations and event streaming

### ⚠️ Notes

- **Extension Rebuild Required**: After upgrade, run `make package` and reinstall
- **Profile Cache**: Clear `dist/profile-cache/*` for clean test environment
- **Predefined Scripts**: Located in `predefined-scripts/` directory
- **Debug Logging**: Disabled by default; enable in `extension/background.js:97`

### 💬 Feedback

We welcome feedback on the new features:
- Report issues via [GitHub Issues](https://github.com/ThinkerYzu/foxmcp/issues)
- Share your automation scripts and use cases
- Suggest new predefined scripts for common tasks
- Contribute improvements via pull requests

---

**Thank you for upgrading to FoxMCP v1.1.0!** This release adds practical automation capabilities while maintaining the stability and reliability of the v1.0.0 foundation.

## v1.0.0 - Initial Release (2024-09-28)

### 🚀 First Stable Release

**FoxMCP v1.0.0** marks the first stable release of Firefox browser automation through the Model Context Protocol (MCP). This release provides a complete, production-ready solution for programmatic browser control.

### ✨ Key Features

#### **Complete Browser Control**
- **Tab Management**: List, create, close, switch between tabs with screenshot capability
- **Window Management**: Create, close, focus, resize windows with cross-window operations
- **Navigation**: Back, forward, reload, and URL navigation with cache control
- **Content Interaction**: Extract text/HTML, execute JavaScript, run custom scripts
- **History Access**: Query browsing history with text search and date filtering
- **Bookmark Operations**: Full bookmark management with folder support and search

#### **MCP Protocol Integration**
- **25+ MCP Tools**: All browser functions exposed via standardized MCP interface
- **Dual Architecture**: WebSocket server (8765) + MCP server (3000)
- **Claude Code Ready**: Direct integration with `claude mcp add` command
- **Real-time Communication**: Automatic reconnection with comprehensive error handling

#### **Developer Experience**
- **Automated Installation**: One-command extension installation with preference setup
- **Comprehensive Testing**: 171 tests covering all functionality with CI/CD ready
- **Complete Documentation**: API reference, guides, and examples
- **Cross-Platform**: Linux, macOS, Windows support

### 📦 Installation

#### **One-Command Installation**
```bash
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/install-from-github.sh | bash
```

This automatically downloads v1.0.0 binaries, sets up Python environment, installs dependencies, configures Firefox extension, downloads Google Calendar automation scripts, and creates Claude Code integration files.

#### **Package Downloads**
- **Firefox Extension**: [foxmcp@codemud.org.xpi](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/foxmcp@codemud.org.xpi)
- **Server Package**: [foxmcp-server.zip](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/foxmcp-server.zip)
- **Source Code**: [v1.0.0.tar.gz](https://github.com/ThinkerYzu/foxmcp/archive/v1.0.0.tar.gz)

### 🔧 System Requirements

- **Firefox**: Any recent version supporting WebExtensions
- **Python**: 3.8 or higher with asyncio support
- **Operating System**: Linux, macOS, or Windows
- **Network**: Localhost access (ports 8765, 3000)

### 🎯 Use Cases

#### **Development & Testing**
- Automated browser testing with AI assistance
- Cross-tab and cross-window testing scenarios
- Dynamic content extraction and validation

#### **AI-Assisted Workflows**
- Intelligent bookmark management and organization
- History-based research and information retrieval
- Automated form filling and data entry

#### **Custom Automation**
- Predefined external scripts for repetitive tasks
- JavaScript execution in browser contexts
- Screenshot capture for documentation

### 🛠️ Architecture

```
MCP Client (Claude Code) → FastMCP Server (3000) → WebSocket (8765) → Firefox Extension → Browser API
```

#### **Core Components**
- **Firefox Extension**: WebExtensions-based browser integration
- **Python Server**: FastMCP + WebSocket dual-server architecture
- **Message Protocol**: JSON-based bidirectional communication
- **MCP Tools**: 25+ standardized browser control functions

### 📚 Documentation

- **[README.md](README.md)**: Quick start and overview
- **[API Reference](docs/api-reference.md)**: Complete function reference
- **[Development Guide](docs/development.md)**: Setup and workflow
- **[Configuration](docs/configuration.md)**: Server and extension setup
- **[Architecture](docs/architecture.md)**: System design and components
- **[Protocol](docs/protocol.md)**: WebSocket message specification

### 🔒 Security

- **Localhost-Only**: Servers bind exclusively to localhost interface
- **Input Validation**: Comprehensive sanitization and validation
- **Minimal Permissions**: Extension uses only required browser permissions
- **Secure Scripting**: Path validation for external script execution

### 🧪 Quality Assurance

- **171 Automated Tests**: Unit and integration test coverage
- **Cross-Platform Testing**: Verified on Linux, macOS, Windows
- **Real Firefox Integration**: Tests run against actual Firefox instances
- **Memory Management**: Proper resource cleanup and leak prevention

### 🌟 Community

- **Open Source**: MIT License with full source availability
- **Issue Tracking**: GitHub Issues for bug reports and feature requests
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines
- **Support**: Community-driven support and documentation

### 🚧 Future Roadmap

The v1.0.0 release establishes a solid foundation for browser automation. Planned future enhancements include:

- **Downloads Management**: Complete downloads API integration
- **Cookie Management**: Comprehensive cookie operations
- **Web Request Interception**: HTTP request/response manipulation
- **Enhanced MCP Features**: Batch operations and event streaming

### ⚠️ Known Limitations

- **Firefox Only**: Currently supports Firefox; Chrome support planned for future releases
- **Localhost Binding**: Servers bind only to localhost for security (not remotely accessible)
- **Extension Signing**: Requires Firefox preference changes for unsigned extension installation

### 💬 Feedback

We welcome feedback and contributions! Please:
- Report bugs via [GitHub Issues](https://github.com/ThinkerYzu/foxmcp/issues)
- Suggest features through issue discussions
- Contribute code via pull requests
- Share your use cases and success stories

---

**Thank you for using FoxMCP!** This v1.0.0 release represents months of development and testing to create a robust, reliable browser automation solution for the AI era.