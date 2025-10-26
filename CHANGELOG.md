# Changelog

All notable changes to FoxMCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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