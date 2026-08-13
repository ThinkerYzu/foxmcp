# Changelog

All notable changes to FoxMCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Extension WebSocket now accepts only `moz-extension://` origins.** Previously any inbound connection was accepted as the extension. WebSocket handshakes are exempt from the same-origin policy and are never preflighted, so any web page the user visited could connect to the localhost port, displace the real extension — an arriving connection closes the existing one — and answer requests on its behalf with content of its choosing. Non-extension connections are now rejected with a 403 during the handshake, and logged.

  Test clients that stand in for the extension must send an extension origin; use `connect_as_extension()` from `tests/test_config.py`.

### Fixed
- **Tool documentation that MCP clients could not see.** FastMCP builds a tool's description from the docstring summary and body and maps `Args:` onto the input schema, but **discards `Returns:`** — and five tools kept facts a caller needs there. `bookmarks_list` and `bookmarks_search` showed three words each while the ID-and-parent-ID convention that makes `bookmarks_update`/`_delete`/`_create` usable was invisible; `bookmarks_search` never mentioned that it matches bookmarks and never folders. `tabs_capture_screenshot` did not say that its return type changes shape depending on `filename`. `requests_start_monitoring` did not say the response carries the `monitor_id` that its three companion tools require. Those facts are now in the description or on the argument. Twelve other tools have a `Returns:` line that only restates the summary and were left alone.
- **`history_delete_item` raised `NameError` instead of confirming the delete.** Both the success line and the fallback line interpolated `params.url`, but the tool takes `url` directly and has no `params` — a leftover from the Pydantic-model signature the neighbouring navigation tools still use. The delete itself went through, then the tool crashed reporting it, so the caller saw a traceback for work that had already succeeded. Only the error path was under test, which is how it shipped.
- **Release archives kept files that had been deleted from the source tree.** `zip` updates an existing archive rather than replacing it, so once a file entered `foxmcp@codemud.org.xpi` it stayed there through every later build until someone ran `make clean`; the server staging directory was copied into without being cleared and had the same problem. Both are now emptied before each build. `__pycache__` from a local run is also dropped from the server archive, so a build here and a build on CI produce the same contents.

### Added
- **`tabs_move` — move tabs to a new position, or into another window.** Takes one tab ID, a list, or a JSON string of IDs, with `index` as the destination (`-1` for the end) and an optional `window_id`. Together with `create_window` this covers gathering the tabs for one site into a window of their own, which was the request in [issue #2](https://github.com/ThinkerYzu/foxmcp/issues/2) — see [`docs/api-reference.md`](docs/api-reference.md#gathering-tabs-into-their-own-window). Firefox refuses some moves without reporting an error, so the result says `Moved {n} of {m}` rather than claiming success.
- **`tabs_list` takes a `window_id`, and reports where each tab sits.** The parameter that was supposed to scope the listing never worked — a `|| true` in the extension made the current-window filter unconditional, so tabs in other windows could not be listed at all, despite the tool documenting itself as listing every tab. An unscoped call now spans every window, as documented, and each line ends with `[window {id}, index {n}]`.
- **A regression test for the MCP port's web-unreachability.** The port has no authentication, and what keeps web pages off it — absent CORS headers, content-type enforcement, and a session id the browser cannot read — is behavior of `fastmcp`/uvicorn rather than of FoxMCP. `tests/integration/test_mcp_port_not_web_reachable.py` asserts all three, so a dependency upgrade that re-opens the port fails the suite instead of passing quietly. No CORS policy was added: the door is already shut, and hand-rolling one risks breaking legitimate MCP clients.
- **Audit logging for predefined scripts.** `content_execute_predefined` is the one tool that runs a program on the host, and it previously logged nothing at all — a refused path-traversal attempt and a routine call were equally invisible. Each invocation now logs the script name, arguments and tab at `INFO`, followed by the size of the generated JavaScript and the URL it ran against; every refusal and failure logs at `WARNING`. Arguments are truncated at 120 characters, and the generated JavaScript is never written to the log. See [`docs/scripts.md`](docs/scripts.md#what-gets-logged).

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

[1.1.0]: https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.1.0
[1.0.0]: https://github.com/ThinkerYzu/foxmcp/releases/tag/v1.0.0