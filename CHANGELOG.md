# Changelog

All notable changes to FoxMCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-14

**This release removes `get_last_focused_window` and seven protocol action names.**
No caller can observe a behavior difference from the tool removal — the tool it
duplicated returns the same window — but a client that names it by hand now gets an
error. See **Removed** below.

### Security
- **Extension WebSocket now accepts only `moz-extension://` origins.** Previously any inbound connection was accepted as the extension. WebSocket handshakes are exempt from the same-origin policy and are never preflighted, so any web page the user visited could connect to the localhost port, displace the real extension — an arriving connection closes the existing one — and answer requests on its behalf with content of its choosing. Non-extension connections are now rejected with a 403 during the handshake, and logged.

  Test clients that stand in for the extension must send an extension origin; use `connect_as_extension()` from `tests/test_config.py`.

### Added
- **`--disable-tools` leaves a tool group unregistered, to keep it out of an MCP client's context.** Every tool description a client is offered stays in its context for the whole session whether or not the tool is ever called, and the full set costs roughly 4,700 tokens — the concern raised in [issue #4](https://github.com/ThinkerYzu/foxmcp/issues/4). The groups are `windows`, `tabs`, `bookmarks`, `navigation`, `content`, `requests`, `history` and `debug`, and all of them remain on by default, so nothing changes for an existing setup. `python server/server.py --disable-tools bookmarks,history` drops nine tools and about 1,000 tokens; `FOXMCP_DISABLE_TOOLS` does the same for clients that launch the server through a wrapper whose arguments you cannot control. An unrecognized group name is an error rather than a warning, because a typo that quietly left the group enabled would defeat the point. See [`docs/configuration.md`](docs/configuration.md#reducing-the-tool-surface) for the per-group cost.
- **`tabs_move` — move tabs to a new position, or into another window.** Takes one tab ID, a list, or a JSON string of IDs, with `index` as the destination (`-1` for the end) and an optional `window_id`. Together with `create_window` this covers gathering the tabs for one site into a window of their own, which was the request in [issue #2](https://github.com/ThinkerYzu/foxmcp/issues/2) — see [`docs/api-reference.md`](docs/api-reference.md#gathering-tabs-into-their-own-window). Firefox refuses some moves without reporting an error, so the result says `Moved {n} of {m}` rather than claiming success.
- **`tabs_list` takes a `window_id`, and reports where each tab sits.** The parameter that was supposed to scope the listing never worked — a `|| true` in the extension made the current-window filter unconditional, so tabs in other windows could not be listed at all, despite the tool documenting itself as listing every tab. An unscoped call now spans every window, as documented, and each line ends with `[window {id}, index {n}]`.
- **A regression test for the MCP port's web-unreachability.** The port has no authentication, and what keeps web pages off it — absent CORS headers, content-type enforcement, and a session id the browser cannot read — is behavior of `fastmcp`/uvicorn rather than of FoxMCP. `tests/integration/test_mcp_port_not_web_reachable.py` asserts all three, so a dependency upgrade that re-opens the port fails the suite instead of passing quietly. No CORS policy was added: the door is already shut, and hand-rolling one risks breaking legitimate MCP clients.
- **Releases are built in public, and say where they came from.** Previously the XPI and server zip were built on the maintainer's machine and uploaded, so installing them meant taking his word that they matched the source — the concern in [issue #1](https://github.com/ThinkerYzu/foxmcp/issues/1). Pushing a `v*` tag now builds them on GitHub Actions from the tagged commit and publishes a signed provenance statement alongside them, which anyone can check without trusting us: `gh attestation verify 'foxmcp@codemud.org.xpi' --repo ThinkerYzu/foxmcp`. `SHA256SUMS` ships as a release asset too. The copy served by addons.mozilla.org is not covered, because Mozilla re-signs the file when it accepts a submission; verify the GitHub asset instead.
- **Audit logging for predefined scripts.** `content_execute_predefined` is the one tool that runs a program on the host, and it previously logged nothing at all — a refused path-traversal attempt and a routine call were equally invisible. Each invocation now logs the script name, arguments and tab at `INFO`, followed by the size of the generated JavaScript and the URL it ran against; every refusal and failure logs at `WARNING`. Arguments are truncated at 120 characters, and the generated JavaScript is never written to the log. See [`docs/scripts.md`](docs/scripts.md#what-gets-logged).

### Removed
- **`release-commands.sh`, the pre-CI release script.** Since 1.2.0 a pushed tag is the entire release, so the script had no job left — but it was worse than idle: it ran `git add -A`, committed the working tree under a "Release v1.1.0" message, and tried to create the `v1.1.0` tag that already exists. It also printed installation instructions that stopped working long ago (`pip install -r requirements.txt`, a repository URL that does not resolve). Everything it did is now in `.github/workflows/release.yml` and `scripts/release-notes.sh`. Nothing referenced it.
- **Seven protocol action names the extension accepted but nothing sent.** Five were old spellings kept as fall-through aliases beside the names that replaced them — `bookmarks.remove`, `content.execute`, `content.html`, `content.text` and `navigation.go`, alongside `bookmarks.delete`, `content.execute_script`, `content.get_html`, `content.get_text` and `navigation.go_to_url`. No tool had sent the old names since before v1.0.0, and their only remaining mention was an unreferenced dispatch table in the test harness, since deleted. The sixth, `tabs.active`, had its own handler returning the active tab of the current window; `tabs_list` reaches the same `browser.tabs.query` and reports the `active` flag, so it added nothing. The seventh, `test.create_test_tabs`, was a test fixture that bulk-created tabs by going around the MCP layer; its only caller was replaced by `tabs_create` in September 2025 — which exercises the layer under test instead of bypassing it — and the handler was left behind. It is the only `test.*` action that never had a method on the server side, and no assertion has ever covered its result. `tabs.update` is deliberately kept: nothing else can change a tab's URL or pinned state in place.
- **`get_last_focused_window`, which could never have returned anything different from `get_current_window`.** Firefox's `ext-windows.js` reads `context.currentWindow || windowTracker.topWindow` for `windows.getCurrent()` and plain `windowTracker.topWindow` for `windows.getLastFocused()`, and `ExtensionParent.sys.mjs` returns `undefined` for `currentWindow` whenever the calling context's `viewType` is `"background"` — the only context this extension has. Both calls therefore evaluated the same expression, and the two tools have returned the same window since v1.0.0. Use `get_current_window`; its description now says it is also the last focused window. Spotted by the reporter of [issue #4](https://github.com/ThinkerYzu/foxmcp/issues/4), who proposed merging the two behind a fallback — the fallback turned out to already be inside `getCurrent`, and to be its only reachable branch here. The `windows.get_last_focused` protocol action is gone with it.

### Fixed
- **`debug_websocket_status` could never report a connection.** It looked for a `connected_clients` collection on the server, which `FoxMCPServer` has never had — it holds a single `extension_connection`, since an arriving extension displaces the previous one — so the tool answered "WebSocket server doesn't track connected clients" whether or not the extension was connected. That is the tool you reach for when the connection is what you doubt, and every other tool answers a missing extension with a 30-second timeout. It now says whether an extension is connected and from which address, and distinguishes "never connected" from "the last connection has closed". Found by installing the extension into a real Firefox profile by hand and asking.
- **`make run-server` ran whatever `python` was on PATH.** Every other Makefile target runs out of `venv/bin`, but this one did not, so on a machine where `python` is another virtual environment — or is not installed, which is normal now that distributions ship only `python3` — starting the server failed on an import of a dependency that was installed all along. `package.json`'s `start` script had the same bug.
- **`debug_websocket_status` was registered by the history group.** Nothing depended on this while every tool was always registered, but it meant the tool you reach for when the connection looks wrong would have disappeared along with an unrelated group. It has its own group now.
- **Response body capture never captured anything.** The extension tried to read bodies by overriding `window.fetch` and `XMLHttpRequest` from a content script, and the override silently did nothing: a content script's `window` is an Xray wrapper, so the assignment landed nowhere and the page kept the native `fetch`. `requests_get_content` therefore returned `included: false` for every request ever made. Bodies now come from `webRequest.filterResponseData`, which taps the response stream in the background script — so the document load is captured too, which the old approach could never have managed, and Firefox has already undone any `Content-Encoding` by the time the bytes arrive. This adds the `webRequestBlocking` permission, which Firefox requires for `filterResponseData`; no listener blocks, cancels or rewrites a request, and the permission carries no new install prompt. At most 200 bodies are held at a time, since a monitor on `*` sees every request the browser makes.
- **`size_bytes` reported 0 for responses whose size was simply unknown.** It was read from `Content-Length`, which compressed HTTP/2 responses routinely omit, with a fallback to `details.responseSize` that returns 0 on Beta and Developer Edition while returning the real figure on Nightly — which is why `test_response_body_capture_verification` passed on the maintainer's machine and failed on CI with no code difference between them. The value is now the bytes actually delivered, counted while the body streams through, and it is correct even when the body itself is withheld for its content type or cut short by `max_body_size`. It is `null`, never 0, when the response could not be tapped at all.
- **A response body, once captured, could not be found again.** When `requests_get_content` had no body stored under the request id it fell back to matching on URL, method and status, comparing against `requestDetail.response_status_code` — a field nothing in the extension ever sets, so the comparison could not succeed. The fallback is gone; bodies are stored under the `webRequest` request id that `requests_list_captured` reports.
- **Tool documentation that MCP clients could not see.** FastMCP builds a tool's description from the docstring summary and body and maps `Args:` onto the input schema, but **discards `Returns:`** — and five tools kept facts a caller needs there. `bookmarks_list` and `bookmarks_search` showed three words each while the ID-and-parent-ID convention that makes `bookmarks_update`/`_delete`/`_create` usable was invisible; `bookmarks_search` never mentioned that it matches bookmarks and never folders. `tabs_capture_screenshot` did not say that its return type changes shape depending on `filename`. `requests_start_monitoring` did not say the response carries the `monitor_id` that its three companion tools require. Those facts are now in the description or on the argument. Twelve other tools have a `Returns:` line that only restates the summary and were left alone.
- **`history_delete_item` raised `NameError` instead of confirming the delete.** Both the success line and the fallback line interpolated `params.url`, but the tool takes `url` directly and has no `params` — a leftover from the Pydantic-model signature the neighbouring navigation tools still use. The delete itself went through, then the tool crashed reporting it, so the caller saw a traceback for work that had already succeeded. Only the error path was under test, which is how it shipped.
- **Release archives kept files that had been deleted from the source tree.** `zip` updates an existing archive rather than replacing it, so once a file entered `foxmcp@codemud.org.xpi` it stayed there through every later build until someone ran `make clean`; the server staging directory was copied into without being cleared and had the same problem. Both are now emptied before each build. `__pycache__` from a local run is also dropped from the server archive, so a build here and a build on CI produce the same contents.

### Documentation
- **The install-from-source instructions did not work.** README told the reader to `pip install -r requirements.txt`, and there is no `requirements.txt` at the repository root — the dependencies live in `server/requirements.txt` and `tests/requirements.txt`. It now says `make install`, which creates `venv/` and installs the server dependencies into it, verified from a fresh clone.
- **Python 3.10 is the floor, and the installer now says so.** `fastmcp` 3 requires it, while `scripts/install-from-github.sh` accepted 3.8 and 3.9 and left pip to fail afterwards with an error that never mentions the Python version. `package.json` claimed `>=3.8` for the same reason. Development and CI run 3.14.
- **Installing an unsigned XPI does not work on release or beta Firefox.** Both enforce extension signing and ignore `xpinstall.signatures.required`; only Nightly, Developer Edition and unbranded builds honour it. README presented the two persistent install methods as if they worked everywhere. They are now marked for what they are, with addons.mozilla.org named as the route for everyone else.
- **`docs/web-request-monitoring.md` documented about twenty tools that were never built** — search, retention policies, storage quotas, session save and load — because the file was an implementation plan presented as reference documentation. It is now a reference for the four tools that exist, covering the pattern syntax, which options do something, where captured data lives and how long it survives.
- **Five parameters are accepted and ignored, and now say so.** `save_request_body_to` and `save_response_body_to` never wrote a file; `include_binary` never changed what came back; `drain_timeout` never delayed a stop; and of the monitoring options, `capture_request_bodies` and `sensitive_headers` are read by nothing. The tool descriptions and the reference docs mark each one rather than leaving a caller to conclude the feature is broken. `requests_get_content` also always returns an empty `request_headers`, which is now documented; no listener collects them.
- **`docs/protocol.md` never documented the `requests.*` messages**, though it presents itself as the complete wire format and the feature shipped in v1.1.0. All four — `start_monitoring`, `list_captured`, `get_content`, `stop_monitoring` — are there now, with their error codes.
- **Neither install path listed its system prerequisites, and both fail without them on a stock Ubuntu.** `make`, `zip` and Python's `venv` module are all absent from a fresh Ubuntu 24.04, so `make install` stopped at "The virtual environment was not created successfully" and `make package` could not build the XPI. README now names them. `scripts/install-from-github.sh` checked for `curl`, `unzip` and `python3` but not for the venv module it uses immediately afterwards: on a machine without `python3-venv` it downloaded and unpacked the whole release, then died on a Python error with no mention of the package to install, leaving five directories and a broken `venv/` behind. It now probes venv creation up front and exits with the apt command to run, before downloading anything.
- **`scripts/install-xpi.sh` told users the extension "should be automatically enabled". It is not.** Firefox installs an extension dropped into a profile from outside the browser in the disabled state and waits for a person to enable it in `about:addons` — verified by installing into a fresh profile and watching the extension sit at `userDisabled: true` while the server logged no connection. The script now says so, as do README's Method 3 and `docs/development.md`; `install-from-github.sh` already did.
- **The repository URL in `package.json` and the extension manifest pointed at a repository that does not exist** (`github.com/foxmcp/foxmcp` rather than `github.com/ThinkerYzu/foxmcp`).

## [1.1.0] - 2025-10-26

### Added
- **Web Request Monitoring API**: Foundation for capturing and inspecting network requests
  - `requests_start_monitoring()`: Start capturing web requests/responses
  - `requests_list_captured()`: Retrieve captured request data
  - `requests_stop_monitoring()`: Stop monitoring and cleanup
  - Two-phase workflow: start monitoring → capture data → stop monitoring
  - Extension integration with comprehensive error handling

- **Bookmark Management Enhancements**
  - Bookmark folder creation support with proper hierarchy
  - Bookmark update functionality for modifying existing bookmarks
  - Enhanced test infrastructure for bookmark operations

- **Predefined Scripts**: Ready-to-use automation scripts
  - `youtube-play-pause.sh`: Control YouTube video playback (play/pause/toggle)
  - `dom-summarize.sh`: Simplify DOM tree for AI agent understanding
  - `gcal-cal-event-js.sh`: Extract specific Google Calendar event details
  - `gcal-daily-events-js.sh`: Get all events for a specific day
  - `gcal-monthly-events-js.sh`: Extract entire month view from calendar
  - All scripts include comprehensive documentation and usage examples

- **Content API Enhancement**
  - Optional `max_length` parameter for `content_get_text` tool
  - Allows truncation of large text extractions for AI context management

- **Installation Options**
  - Firefox Add-ons store installation option documented
  - Simplified installation instructions to single command
  - Updated installation script to include all predefined scripts

- **Test Coverage**: Added comprehensive test for history query filtering
  - Verifies that non-matching entries are excluded from filtered results
  - Tests multiple distinct search terms to ensure proper filtering behavior

- **Timestamp Validation**: Added comprehensive history timestamp validation
  - New `validate_history_item_timestamp()` helper function ensures timestamps are valid
  - Validates timestamp presence, format, range, and reasonableness
  - All history tests now verify timestamps are non-null, positive, and within valid date ranges
  - End-to-end test confirms MCP tools display actual timestamps to AI agents

### Fixed
- **History Query Filtering**: Fixed parameter name mismatch that prevented history search filtering from working correctly
  - Extension now correctly reads `query` parameter (was reading non-existent `text` parameter)
  - History searches now properly filter results based on search query
  - Non-matching entries are correctly excluded from search results
  - All tests updated to use correct `query` parameter per protocol specification

- **History Timestamp Display**: Fixed MCP tools showing "Unknown time" for history items
  - MCP tools now correctly read `lastVisitTime` field (was reading non-existent `visitTime` field)
  - AI agents now see actual timestamps in milliseconds since epoch
  - Affects `history_query` and `history_get_recent` MCP tools
  - Documentation updated to reflect correct field name and format

- **Bookmark Management**: Fixed bookmark management integration test failures
  - Improved test reliability and error handling
  - Enhanced test infrastructure for bookmark operations

- **Google Calendar Scripts**: Fixed gcal-daily-events-js.sh to get current month correctly
  - Script now accurately determines the current month/year
  - Improved date handling for calendar automation

### Changed
- **Infrastructure**: Clear profile cache after packaging extension
  - Ensures clean state for extension testing
  - Prevents stale profile data from affecting tests

- **Documentation**: Enhanced CLAUDE.md with comprehensive instructions
  - Added ENABLE_DEBUG_LOGGING_TO_SERVER debugging documentation
  - Documented all available predefined scripts with usage examples
  - Updated installation instructions with predefined scripts

### Developer Experience
- 211 total tests passing (59 unit + 152 integration)
- All tests enabled and maintaining 100% pass rate
- Enhanced debugging capabilities with configurable logging
- Improved developer documentation and troubleshooting guides

## [1.0.0] - 2024-09-28

### Added
- **Complete Browser Automation**: Full Firefox browser control via MCP protocol
  - Tab management (list, create, close, switch, take screenshots)
  - Window management (list, create, close, focus, resize)
  - Navigation control (back, forward, reload, go to URL)
  - Content access (extract text, HTML, execute JavaScript)
  - History operations (query, search, delete)
  - Bookmark management (list, search, create, delete with folder support)

- **MCP Protocol Integration**: 25+ tools accessible via FastMCP server
  - Dual server architecture (WebSocket + MCP endpoints)
  - Complete request/response correlation with UUID tracking
  - Automatic reconnection and timeout handling
  - Comprehensive error handling and validation

- **Firefox Extension**: Complete WebExtensions-based implementation
  - Background script with persistent WebSocket connection
  - Content scripts for page interaction
  - Popup interface with connection status and configuration
  - Options page for server settings and preferences
  - Storage.sync integration for cross-browser preference sync

- **Development Infrastructure**: Comprehensive build and test system
  - 171 tests (29 unit + 142 integration) with 100% coverage
  - Automated test environment with Firefox integration
  - Dynamic port allocation for test isolation
  - Robust test import system with symbolic links
  - Complete Makefile with development workflow

- **Installation Tools**: Automated setup and deployment
  - Automated extension installation script (`scripts/install-xpi.sh`)
  - Firefox preference configuration (unsigned extension support)
  - Virtual environment setup and dependency management
  - Cross-platform compatibility (Linux, macOS, Windows)

- **Documentation**: Comprehensive guides and references
  - Complete API reference with all 25+ MCP tools
  - Development guide with setup and workflow instructions
  - Architecture documentation with system design
  - Protocol specification with WebSocket message formats
  - Configuration guide for server and extension setup
  - Custom scripts documentation with examples

- **Claude Code Integration**: Ready-to-use MCP client support
  - Example CLAUDE.md templates for script creation assistance
  - Predefined external script system with parameterized execution
  - Browser automation workflow integration
  - Context-aware script development support

- **Security Features**: Robust security model
  - Localhost-only server binding with security enforcement
  - Input validation and sanitization
  - Secure script execution with path validation
  - Minimal required permissions model

### Technical Details
- **WebSocket Protocol**: JSON-based bidirectional communication
- **MCP Server**: FastMCP-powered HTTP server on port 3000
- **WebSocket Server**: Extension communication on port 8765
- **Extension ID**: `foxmcp@codemud.org`
- **Supported Firefox**: All recent versions with WebExtensions support
- **Python Requirements**: Python 3.8+ with asyncio support

### Package Distribution
- **Firefox Extension**: `dist/packages/foxmcp@codemud.org.xpi`
- **Server Package**: `dist/packages/foxmcp-server.zip`
- **Source Code**: Complete repository with build system
- **License**: MIT License with proper attribution

### Performance & Reliability
- **Test Coverage**: 171 automated tests covering all functionality
- **Error Handling**: Comprehensive error recovery and reporting
- **Resource Management**: Proper cleanup and memory management
- **Connection Stability**: Automatic reconnection and health monitoring
- **Cross-Platform**: Tested on Linux, macOS, and Windows

### Initial Release Scope
This v1.0.0 release represents a complete, production-ready browser automation solution that enables AI assistants and automation tools to control Firefox browsers through the standardized Model Context Protocol (MCP).

[1.2.0]: https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.2.0
[1.1.0]: https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.1.0
[1.0.0]: https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.0.0