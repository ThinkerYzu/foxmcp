# FoxMCP Test Suite

This directory contains unit and integration tests for the FoxMCP project.

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── pytest.ini              # Pytest settings
├── requirements.txt         # Test dependencies
├── run_tests.py            # Test runner script
├── README.md               # This file
├── unit/                   # Unit tests
│   ├── test_server.py      # Server component tests
│   └── test_protocol.py    # Protocol message tests
├── integration/            # Integration tests
│   ├── test_websocket_communication.py      # Basic WebSocket communication tests
│   ├── test_live_server_communication.py    # Real server startup and communication tests
│   ├── test_real_websocket_communication.py # Advanced WebSocket protocol tests
│   ├── test_firefox_extension_communication.py # Firefox extension integration tests
│   └── test_ping_pong_integration.py        # Ping-pong protocol tests
└── fixtures/               # Test data files
```

## Running Tests

### Install Test Dependencies

```bash
cd tests
pip install -r requirements.txt
```

### Run All Tests

```bash
python run_tests.py
```

### Run Unit Tests Only

```bash
python run_tests.py unit
```

### Run Integration Tests Only

```bash
python run_tests.py integration
```

### Run Integration Tests (includes Firefox Extension)

```bash
# From project root directory
make test-integration

# With custom Firefox path (if needed)
FIREFOX_PATH=/path/to/firefox make test-integration
```

The integration tests automatically create temporary Firefox profiles, install the extension, and run comprehensive testing with proper resource cleanup.

### Run Tests with Coverage

```bash
pytest --cov=../server --cov-report=html --cov-report=term-missing
```

## Test Categories

### Unit Tests

- **test_server.py**: Tests WebSocket server functionality
  - Server initialization
  - Connection handling
  - Message processing
  - Error handling


- **test_protocol.py**: Tests message protocol
  - Message structure validation
  - JSON serialization
  - Error code definitions
  - Data structure validation

### Integration Tests

- **test_websocket_communication.py**: Tests basic WebSocket communication patterns
  - Extension connection mocking and validation
  - Message exchange simulation
  - Connection state management
  - Message routing verification
  - Connection recovery scenarios
  - Error handling scenarios

- **test_live_server_communication.py**: Tests real WebSocket server functionality
  - Live server startup and shutdown
  - Real client connections to server
  - Bidirectional message flow simulation
  - Multiple client connection handling
  - Server resilience and error recovery
  - Protocol compatibility verification

- **test_real_websocket_communication.py**: Tests advanced WebSocket protocol features
  - Real server-client communication with dynamic ports
  - Protocol message format validation
  - Browser action category support (tabs, history, bookmarks, etc.)
  - Error handling robustness
  - Connection timeout and recovery
  - Multi-client concurrent connections

- **test_firefox_extension_communication.py**: Tests Firefox extension integration
  - Real Firefox browser startup with extension
  - Temporary profile creation and management
  - Extension installation and configuration
  - Server-extension WebSocket communication
  - Browser API accessibility through extension
  - Connection resilience with real browser

- **test_ping_pong_integration.py**: Tests ping-pong protocol implementation
  - Bidirectional ping-pong messaging
  - Connection state validation during ping
  - Message ID uniqueness and correlation
  - Timeout handling and recovery
  - Concurrent ping operations
  - Protocol compliance verification

- **test_mcp_integration.py**: Tests FastMCP server integration
  - MCP tools initialization and configuration
  - Server startup with dual port architecture (WebSocket + MCP)
  - MCP tool call simulation with mock WebSocket responses
  - Error handling in MCP protocol layer
  - Tool structure and category validation
  - MCP application creation and management

- **test_real_firefox_communication.py**: Tests actual Firefox browser integration
  - Real Firefox process startup with extension installed
  - Extension-server communication with coordinated ports
  - Message exchange verification between extension and server
  - Connection tracking and response validation
  - Firefox test profile management and cleanup
  - Extension configuration persistence testing

- **test_history_management.py**: Comprehensive end-to-end history management tests
  - Complete browser history functionality testing through WebSocket protocol
  - History query with text search, time ranges, and parameter validation
  - Recent history retrieval with sorting verification
  - Concurrent history operations and response correlation
  - Error handling for unimplemented features (delete_item)
  - Real Firefox history API integration testing

- **test_history_mcp_integration.py**: MCP protocol integration tests for history
  - Dual server architecture verification (MCP + WebSocket)
  - MCP-WebSocket layer integration for history operations
  - End-to-end MCP tool workflow validation

- **test_end_to_end_mcp.py**: Comprehensive MCP protocol compliance tests
  - **Schema validation**: All history and tab tools have correct parameter schemas
  - **Parameter format validation**: Direct parameters (no `params` wrapper)
  - **Agent error reproduction**: Tests for common external agent issues
  - **HTTP endpoint validation**: FastMCP server accessibility testing
  - **Tool naming validation**: Prevents naming mismatches between test and production
  - **End-to-end tab testing**: Creates actual browser tabs and verifies tab listing functionality
  - **Navigation reload testing**: Complete end-to-end page reload functionality with cache bypass options

- **test_window_management.py**: Comprehensive window management end-to-end tests
  - **Window creation and properties**: Creates windows with specific dimensions and properties
  - **Cross-window tab creation**: Creates tabs in specific windows using window_id parameter
  - **Window focus switching**: Tests focus operations with current window verification
  - **Tab isolation verification**: Ensures tabs remain in their designated windows
  - **Window cleanup**: Proper cleanup of created windows after tests
  - **Multiple test scenarios**: Basic operations and comprehensive focus switching tests

## Test Fixtures

The `conftest.py` file provides shared test fixtures:

- `sample_request`: Sample WebSocket request message
- `sample_response`: Sample WebSocket response message
- `sample_error`: Sample error message
- `mock_websocket`: Mock WebSocket connection
- `mock_chrome_api`: Mock Chrome extension API
- `sample_tab_data`: Sample tab data for testing
- `sample_history_data`: Sample history data
- `sample_bookmark_data`: Sample bookmark data

## Writing New Tests

### Unit Test Example

```python
def test_new_functionality(self, fixture_name):
    """Test description"""
    # Arrange
    input_data = {"key": "value"}

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result["status"] == "success"
```

### Async Test Example

```python
@pytest.mark.asyncio
async def test_async_functionality(self, mock_websocket):
    """Test async functionality"""
    result = await async_function(mock_websocket)
    assert result is True
```

## Test Coverage

Run with coverage to ensure comprehensive testing:

```bash
pytest --cov=../server --cov-report=html
```

Coverage reports are generated in `htmlcov/` directory.

**Current Test Statistics:**
- **130+ total tests** across unit and integration suites (includes window management testing)
- **Enhanced coverage** of server components including FastMCP integration
- **97+ integration tests** covering WebSocket communication, MCP functionality, and window management
- **29 unit tests** covering individual component functionality
- **8 additional tests** in root test directory for end-to-end coordination
- **Comprehensive MCP schema validation** prevents parameter format issues
- **Window management test coverage** includes focus switching and cross-window operations

## Test Infrastructure Features

### Fixed Port Allocation for Test Coordination
Tests use **fixed, coordinated ports** to enable reliable extension-server communication:

#### Test Suite Port Assignments
- `unit_tests`: WebSocket 8700, MCP 3100
- `integration_basic`: WebSocket 8701, MCP 3101
- `integration_live`: WebSocket 8702, MCP 3102
- `integration_websocket`: WebSocket 8703, MCP 3103
- `integration_firefox`: WebSocket **8704**, MCP 3104 ← **Extension connects here**
- `integration_mcp`: WebSocket 8705, MCP 3105
- `integration_ping_pong`: WebSocket 8706, MCP 3106

#### Extension-Server Coordination
- **Firefox Extension Test Port**: `8704` (fixed)
- **Real Firefox Tests**: Use `FirefoxTestManager` to pre-configure extension with correct port
- **Extension Configuration**: Automatically set during test profile creation
- **Port Conflicts**: Avoided by test suite separation and cleanup

### Robust Fixture Management
- Proper async fixture cleanup with error handling
- Server task cancellation and resource cleanup
- Temporary Firefox profile management
- Extension installation and cleanup

### Firefox Integration Testing
The test suite includes comprehensive Firefox browser integration:
- Temporary profile creation with extension settings
- XPI extension installation and activation
- Background Firefox execution with custom paths
- Real WebSocket communication between server and extension
- Browser API function verification

## Browser API Test Coverage

All major browser functions are tested:

**Tabs Management:** `tabs_list`, `tabs_create`, `tabs_close`, `tabs_switch` (with end-to-end tab creation and listing tests) - ✅ All implemented in extension
  - ✅ **Cross-window tab creation**: `tabs_create` with `window_id` parameter support
  - ✅ **Tab isolation**: Tabs properly isolated per window

**Window Management:** `windows.list`, `windows.get`, `windows.create`, `windows.close`, `windows.focus`, `windows.update`, `windows.get_current` - ✅ All implemented and tested
  - ✅ **Window creation**: Creates windows with specific dimensions and properties
  - ✅ **Focus switching**: Window focus operations with current window verification
  - ✅ **Window properties**: State management (normal, maximized, minimized, fullscreen)
  - ✅ **Cross-window operations**: Verified tab creation and management across multiple windows

**History Operations:** `history.query`, `history.get_recent`, `history.delete_item`, `history.clear_range`

**Bookmark Management:** `bookmarks.list`, `bookmarks.search`, `bookmarks.create`, `bookmarks.delete`, `bookmarks.update`, `bookmarks.create_folder`

**Navigation Control:** `navigation.back`, `navigation.forward`, `navigation.reload`, `navigation.go_to_url`

**Content Access:** `content.get_text`, `content.get_html`, `content.get_title`, `content.get_url`, `content.execute_script` (with comprehensive end-to-end JavaScript execution tests) - ✅ All implemented and tested

## Test Environment Isolation

### Development Environment Protection

The test suite implements comprehensive port isolation to prevent interference with development environments:

**Automatic Port Allocation:**
- Tests use dynamic ports (40000+ range) instead of default ports (8765, 3000)
- `conftest.py` automatically patches `FoxMCPServer` to override default ports
- Extension build process changes default fallback port from 8765 to 48765

**Firefox Profile Isolation:**
- Test Firefox profiles disable storage.sync to prevent cross-contamination
- Profile-specific configurations ensure test settings don't affect development browsers
- Automatic cleanup of test profiles and processes

**Key Benefits:**
- ✅ Integration tests never connect to development servers
- ✅ Development workflow uninterrupted by test execution
- ✅ Complete isolation between test and production environments
- ✅ Safe parallel execution of tests and development servers

## Continuous Integration

Tests should be run before:
- Committing code changes
- Creating pull requests
- Deploying to production

All tests must pass before merging changes.

### Running the Complete Test Suite

For comprehensive testing including Firefox integration:

```bash
# Run all tests with coverage
make test

# Run just integration tests
python -m pytest integration/ -v

# Run specific test categories
python -m pytest integration/test_live_server_communication.py -v
```