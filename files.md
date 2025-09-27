# FoxMCP Project Skeleton Structure

This document explains the basic skeleton structure created for the FoxMCP project.

## Project Overview

```
foxmcp/
├── CLAUDE.md           # Project requirements and instructions
├── PLAN.md            # Development plan and phases
├── protocol.md        # WebSocket message protocol specification
├── files.md           # This file - explains project structure
├── README.md          # Main project documentation and quick start
├── claude.sh          # Claude Code integration script with FM_ROOT environment
├── Makefile           # Build system and development commands
├── venv-setup.md      # Virtual environment setup documentation
├── venv/              # Python virtual environment (created)
├── extension/         # Browser extension directory
│   ├── manifest.json  # Extension configuration and permissions
│   ├── background.js  # Service worker with WebSocket client and ping-pong
│   ├── content.js     # Content script for page interaction
│   └── popup/         # Extension popup UI
│       ├── popup.html # Popup interface HTML with test button
│       └── popup.js   # Popup JavaScript logic with ping test
├── server/            # Python MCP server directory
│   ├── __init__.py    # Python package init (for imports)
│   ├── requirements.txt # Python dependencies
│   ├── server.py       # WebSocket server implementation with ping-pong
│   └── mcp_tools.py    # FastMCP tool definitions and handlers
├── tools/             # Utility scripts and tools
│   └── generate-channel-switch.sh # Generate JavaScript for channel switching
└── tests/             # Test suite directory
    ├── conftest.py    # Pytest configuration and fixtures
    ├── pytest.ini     # Pytest settings
    ├── requirements.txt # Test dependencies (with pytest-cov)
    ├── run_tests.py   # Test runner script (with PYTHONPATH fix)
    ├── test_imports.py # Test import system with automatic path setup
    ├── README.md      # Test documentation
    ├── htmlcov/       # Coverage HTML reports (generated)
    ├── firefox_test_utils.py   # Firefox testing utilities with SQLite configuration
    ├── test_config.py          # Test configuration and port allocation
    ├── port_coordinator.py     # Test port coordination system
    ├── unit/          # Unit tests
    │   ├── test_server.py      # Server component tests
    │   ├── test_protocol.py    # Protocol message tests
    │   ├── test_ping_pong.py   # Ping-pong functionality tests
    │   └── test_window_handlers.py # Window management message and MCP tool tests
    ├── integration/   # Integration tests
    │   ├── test_websocket_communication.py # WebSocket communication tests
    │   ├── test_ping_pong_integration.py  # End-to-end ping tests
    │   ├── test_real_firefox_communication.py # Real Firefox extension tests
    │   ├── test_ui_storage_sync.py        # UI storage synchronization tests with Firefox
    │   ├── test_window_management.py      # End-to-end window management tests with Firefox
    │   ├── test_end_to_end_mcp.py         # Complete MCP tool chain tests (includes navigation reload)
    │   ├── test_test_helper_protocol.py   # Test helper protocol unit tests
    │   └── foxmcp_scripts/    # External scripts for predefined script execution tests
    │       ├── simple_test.sh     # Basic test script (no user interaction)
    │       ├── get_page_info.sh   # Page information extraction (title, URL, text, links)
    │       └── multi_arg_test.sh  # Multi-argument demo script with DOM manipulation
    └── fixtures/      # Test data files
```

## Extension Directory (`/extension`)

### `manifest.json`
- **Purpose**: Extension configuration file for Firefox
- **Key Features**:
  - Manifest V2 format for Firefox WebExtensions compatibility
  - Permissions for tabs, windows, history, bookmarks, activeTab, storage, and all URLs
  - Persistent background script registration
  - Content script injection for all URLs
  - Browser action popup UI configuration

### `background.js`
- **Purpose**: Extension persistent background script
- **Key Features**:
  - WebSocket client connection to MCP server (ws://localhost:8765)
  - **Configurable connection parameters** with persistent storage via browser.storage.sync
  - **Test configuration override system** - reads testPort/testHostname with priority over regular settings
  - Automatic reconnection with configurable retry intervals and limits
  - Message routing to appropriate handler functions
  - Request/response message handling with async support
  - **Ping-pong functionality** for connection testing
  - **Runtime message handling** for popup and options page communication
  - **Async ping testing** with timeout and correlation
  - **Configuration loading and updating** with test environment support
  - Error handling and logging
  - **Complete WebExtensions API implementations** for all function categories:
    - **History management**: Query history, get recent items via browser.history
    - **Tab management**: List, create, close, update tabs via browser.tabs
    - **Window management**: List, get, create, close, focus, update windows via browser.windows
    - **Content extraction**: Text and HTML extraction from pages via browser.tabs.sendMessage
    - **Navigation control**: URL navigation, back/forward, reload via browser.tabs
    - **Bookmark management**: List, search, create, remove bookmarks via browser.bookmarks
  - **Test Helper Protocol** - WebSocket messages for automated UI testing:
    - **test.get_popup_state**: Get current popup display values and test override status
    - **test.get_options_state**: Get options page display values and configuration state
    - **test.get_storage_values**: Retrieve raw storage.sync values for validation
    - **test.validate_ui_sync**: Validate UI-storage synchronization with expected values
    - **test.refresh_ui_state**: Trigger UI state refresh for testing scenarios

### `content.js`
- **Purpose**: Content script injected into web pages
- **Key Features**:
  - Page content extraction (text, HTML) via browser.runtime.onMessage
  - JavaScript execution capability with eval()
  - Message passing with background script using WebExtensions messaging
  - Error handling for page interactions

### `popup/popup.html`
- **Purpose**: Extension popup user interface
- **Key Features**:
  - Connection status display with retry attempt information
  - **Connection status display** for monitoring server connection
  - **Force Reconnect button** for manual connection restart
  - **Test result display area** with success/failure feedback
  - **Collapsible configuration panel** with:
    - Server URL input field
    - Retry interval configuration (1000ms - 60000ms)
    - Max retry attempts setting (-1 for infinite)
    - Ping timeout configuration (1000ms - 30000ms)
  - **Save Configuration button** with validation
  - Server information display
  - Clean, minimal design with enhanced status indicators

### `popup/popup.js`
- **Purpose**: Popup interface logic
- **Key Features**:
  - **Direct storage.sync access** for accurate configuration reading and writing
  - **Test configuration override support** - displays effective values with priority handling
  - **Real-time connection status checking** with retry information display
  - **Connection monitoring** with visual feedback and status updates
  - **Configuration management** with WebSocket URL parsing/building and form validation
  - **Test override preservation** - saves maintain test configurations during normal use
  - **Test indicator display** - shows when test configuration overrides are active
  - **Force reconnect functionality** for manual connection control
  - **Async communication** with background script using browser.runtime.sendMessage
  - **Comprehensive error handling** with browser.runtime.lastError checks
  - **Dynamic UI updates** based on connection state and configuration
  - **Button state management** during testing and configuration operations

### `options.html` & `options.js`
- **Purpose**: Extension options/preferences page
- **Key Features**:
  - **Comprehensive configuration interface** with server settings and advanced options
  - **Direct storage.sync integration** for reading and writing configuration
  - **Test configuration override support** - displays effective values and warns when test overrides are active
  - **Server configuration**: Hostname, port, and WebSocket URL management
  - **Advanced settings**: Retry intervals, max retries, ping timeout configuration
  - **Connection monitoring** with real-time status updates
  - **Connection status display** with real-time updates
  - **Configuration preservation** - all saves maintain test overrides and existing settings
  - **Form validation** with comprehensive error checking and user feedback
  - **Reset to defaults** functionality with confirmation
  - **Professional UI design** with organized sections and help text

## Server Directory (`/server`)

### `requirements.txt`
- **Purpose**: Python package dependencies
- **Dependencies**:
  - `fastmcp>=1.0.0` - FastMCP framework for MCP protocol
  - `websockets>=12.0` - WebSocket server implementation
  - `asyncio` - Async/await support
  - `json` - JSON message parsing

### `server.py`
- **Purpose**: Main WebSocket server implementation
- **Key Features**:
  - WebSocket server on localhost:8765
  - Extension connection management with proper cleanup
  - **Request/response correlation system** with unique ID tracking
  - **Pending requests map** with Future-based async response handling
  - **Ping-pong message handling** for connection testing
  - **Bidirectional ping functionality** (server can ping extension)
  - **send_request_and_wait method** with configurable timeouts
  - **Async ping testing methods** with correlation
  - **Test helper protocol** with 5 WebSocket test commands for automated UI validation:
    - `test.get_popup_state` - Get popup display state and test override status
    - `test.get_options_state` - Get options page configuration and warnings  
    - `test.get_storage_values` - Get raw storage.sync values
    - `test.validate_ui_sync` - Validate UI synchronization with expected values
    - `test.refresh_ui_state` - Trigger UI state refresh
  - **Response type handling** (success, error, timeout scenarios)
  - Message handling and comprehensive logging
  - Connection state tracking
  - Error handling and recovery
  - Async/await architecture
  - Graceful shutdown handling

### `mcp_tools.py`
- **Purpose**: FastMCP protocol integration and tool definitions
- **Key Features**:
  - **Modern FastMCP framework integration** with decorator-based tool definitions
  - **Complete MCP tool registry** with all browser functions:
    - **History**: query with search terms/time ranges, recent items
    - **Tabs**: list all tabs, create new tabs, close tabs, update tabs
    - **Content**: text extraction, HTML extraction, direct script execution, predefined script execution
    - **Navigation**: URL navigation, back/forward, reload with cache options
    - **Bookmarks**: list bookmarks tree, search bookmarks, create/remove bookmarks
  - **Comprehensive tool parameter definitions** with types and validation
  - **UUID-based request ID generation** for correlation tracking
  - **Complete action mapping** between MCP tools and WebSocket actions
  - **Full response correlation implementation** with timeout handling
  - **Response type processing** (success data extraction, error handling)
  - **15-second timeout** for extension responses with graceful failure handling
  - **Predefined Script Execution System**:
    - `content_execute_predefined()` - Execute external scripts that generate JavaScript
    - **Environment variable configuration**: `FOXMCP_EXT_SCRIPTS` directory path
    - **Security validation**: Path traversal protection, character validation, directory containment
    - **JSON argument support**: JSON array of strings or empty string for no arguments
    - **External script execution**: Subprocess execution with 30-second timeout
    - **JavaScript injection**: Generated script output executed in browser tabs
    - **Comprehensive error handling**: Script validation, execution, and browser injection errors

## Communication Flow

1. **Extension Startup**: Firefox extension connects to WebSocket server with auto-retry
2. **MCP Request**: MCP client calls browser tool via FastMCP framework
3. **Request Generation**: MCP handler creates unique request with UUID-based ID
4. **Tool Mapping**: MCP handler maps tool name to WebSocket action
5. **Extension Forward**: Server sends request to extension via send_request_and_wait
6. **WebExtensions API**: Extension calls Firefox WebExtensions APIs (browser.history, browser.tabs, etc.)
7. **Response Correlation**: Extension sends response with matching request ID
8. **Future Completion**: Server correlates response and completes pending Future
9. **Response Chain**: Actual results flow back through WebSocket to MCP client
10. **Error Handling**: Timeouts, API errors, and connection issues handled gracefully

## Current Implementation Status

- ✅ **Basic Structure**: All directories and files created (26 files)
- ✅ **WebSocket Foundation**: Connection handling implemented with modern API
- ✅ **Message Protocol**: Request/response format defined and implemented
- ✅ **Tool Definitions**: MCP tools registered and mapped to browser actions
- ✅ **Unit Test Infrastructure**: Complete test suite with fixtures and runners
- ✅ **Ping-Pong Communication**: End-to-end connection testing implemented
- ✅ **Build System**: Makefile with complete development workflow
- ✅ **Documentation**: README, protocol spec, and project documentation
- ✅ **Virtual Environment**: Python venv with all dependencies installed
- ✅ **Comprehensive Test Suite**: 91 tests passing (47 unit + 44 integration), 74% code coverage, all tests enabled including automated UI validation
- ✅ **Firefox WebExtensions API Integration**: Complete browser.* API implementations for all handlers
- ✅ **Response Correlation**: Full async response handling with UUID-based correlation
- ✅ **Configuration System**: Configurable retry intervals and connection parameters
- ⏳ **FastMCP Integration**: Actual MCP server framework setup pending
- ⏳ **Error Handling**: Comprehensive error scenarios (partially implemented)
- ⏳ **Integration Testing**: End-to-end testing with real Firefox extension and MCP client

## Tests Directory (`/tests`)

### `conftest.py`
- **Purpose**: Pytest configuration and shared fixtures
- **Key Features**:
  - Sample message fixtures (request, response, error)
  - Mock WebSocket and Chrome API objects
  - Test data fixtures (tabs, history, bookmarks)
  - Async test support configuration

### `pytest.ini`
- **Purpose**: Pytest configuration settings
- **Key Features**:
  - Test discovery patterns
  - Async test mode configuration
  - Coverage and reporting settings

### `requirements.txt`
- **Purpose**: Test-specific Python dependencies
- **Dependencies**: pytest, pytest-asyncio, pytest-mock, coverage, websockets

### `test_imports.py`
- **Purpose**: Test import system with automatic path configuration
- **Key Features**:
  - **Automatic project root detection** by locating 'server' package
  - **Zero-configuration path setup** - eliminates manual sys.path manipulation
  - **Symbolic link support** - available in subdirectories via symlinks
  - **Works everywhere** - pytest, direct execution, any working directory
  - **Debug utilities** - verification, status reporting, and troubleshooting
  - **Type hints and error handling** for robust operation
  - **CLI interface** for debugging import system status

### `run_tests.py`
- **Purpose**: Test runner script with coverage
- **Key Features**:
  - Run all tests with coverage reporting
  - Run unit tests only
  - Run integration tests only
  - HTML coverage reports

### Unit Tests (`/unit`)
- **`test_server.py`**: WebSocket server functionality tests
  
- **`test_protocol.py`**: Message format and data structure validation tests
- **`test_ping_pong.py`**: Ping-pong message handling and protocol tests

### Integration Tests (`/integration`)
- **`test_websocket_communication.py`**: End-to-end WebSocket communication tests
- **`test_ping_pong_integration.py`**: Ping-pong functionality integration tests
- **`test_ui_storage_sync.py`**: UI storage synchronization tests with real Firefox extension using test helper protocol
- **`test_test_helper_protocol.py`**: Unit tests for test helper protocol with mock WebSocket

## Build and Development System

### `Makefile`
- **Purpose**: Complete build system and development workflow
- **Key Features**:
  - **Setup and Installation**: `make setup` - Install all dependencies and setup test imports
  - **Test Import Management**: `make setup-test-imports` - Create symbolic links for test import system
  - **Building**: `make build` - Build extension package
  - **Testing**: `make test` - Run comprehensive test suite with coverage
  - **Unit Testing**: `make test-unit` - Run unit tests only (fast)
  - **Integration Testing**: `make test-integration` - Run integration tests with Firefox automation
  - **Development**: `make run-server` - Start WebSocket server
  - **Quality Assurance**: `make check` - Run linting and tests
  - **Packaging**: `make package` - Create distributable ZIP files
  - **Maintenance**: `make clean` - Clean build artifacts and remove symbolic links
  - **Status Monitoring**: `make status` - Check project status including test import system

### `claude.sh`
- **Purpose**: Claude Code integration script
- **Key Features**:
  - **Automatic FM_ROOT setup** - Sets environment variable to project root directory
  - **Argument pass-through** - Forwards all command line arguments to claude
  - **Project context** - Enables Claude Code to reference project paths in bash commands
  - **Zero configuration** - Automatically detects project root from script location

### `README.md`
- **Purpose**: Main project documentation and quick start guide
- **Key Features**:
  - **Quick Start**: Get running in 5 commands
  - **Complete Function Reference**: All browser APIs documented
  - **Development Workflow**: Step-by-step development process
  - **WebSocket Protocol**: Message format examples
  - **Troubleshooting Guide**: Common issues and solutions
  - **Architecture Diagram**: System overview with data flow

## Virtual Environment and Testing

### `venv/` - Python Virtual Environment
- **Python 3.13.3** with all required dependencies installed
- **Dependencies**: websockets, pytest, pytest-asyncio, pytest-mock, pytest-cov, coverage
- **Usage**: `source venv/bin/activate` to activate environment

### `venv-setup.md` - Setup Documentation
- Complete virtual environment setup instructions
- Package installation commands and verification steps
- Server and test running instructions

### Test Results (Current)
- **91 tests passing** - All unit and integration tests (47 unit + 44 integration) including automated UI validation
- **0 tests skipped** - All integration tests now enabled and working
- **74% code coverage** - Comprehensive coverage across server components
- **HTML coverage reports** - Generated in tests/htmlcov/
- **Real Firefox integration** - Automated testing with temporary profiles and extension installation
- **Dynamic port allocation** - Tests use unique ports (9000-10999) to prevent conflicts
- **Robust fixture management** - Proper async cleanup and resource management
- **Response correlation testing** - All async handler tests passing
- **Multi-client testing** - Concurrent connection handling and server resilience testing
- **Extension configuration testing** - SQLite storage-based configuration injection and testing
- **Test override system** - Test configurations preserve and override regular extension settings

### Firefox Test Infrastructure (`tests/firefox_test_utils.py`)
- **Purpose**: Complete Firefox testing framework with automatic extension configuration
- **Key Features**:
  - **Temporary Firefox profile creation** with test-optimized preferences
  - **Extension installation and enablement** via extensions.json modification using jq
  - **SQLite storage configuration injection** - directly modifies storage-sync-v2.sqlite database
  - **Test configuration override system** - injects testPort/testHostname with priority over regular settings
  - **Firefox process management** - automated startup, initialization, and cleanup
  - **Dynamic port allocation integration** - works with port coordination system
  - **Context manager support** - automatic resource cleanup with proper error handling
  - **Extension XPI detection** - automatic location of built extension packages
  - **Profile isolation** - each test gets clean temporary profile to prevent conflicts

## Next Steps

1. ✅ ~~**Run existing tests** to validate current implementation: `make test`~~
2. ✅ ~~**Implement actual browser API calls** in extension handlers~~
3. ✅ ~~**Add response correlation** and async waiting in MCP handler~~
4. ✅ ~~**Integrate FastMCP server framework** for MCP protocol compliance~~
5. ✅ ~~**Add comprehensive error handling** for edge cases and permissions~~
6. ✅ ~~**Create testing framework and test cases**~~
7. ✅ ~~**Add ping-pong communication for connection validation**~~
8. ✅ ~~**Create build system and documentation**~~
9. ✅ ~~**Set up virtual environment and fix test infrastructure**~~
10. ✅ ~~**Complete window management functionality** with focus switching and cross-window operations~~
11. ✅ ~~**End-to-end integration testing** with real Firefox extension and MCP client~~
12. **Add logging and debugging capabilities** for production deployment
13. **Performance optimization and connection management** for multiple clients

This foundation provides a complete development environment with professional build tooling, comprehensive testing infrastructure, working Python environment, and full documentation for implementing the FoxMCP system with clear separation of concerns and validation.