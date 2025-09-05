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
- **128 total tests** across unit and integration suites (includes history content testing)
- **Enhanced coverage** of server components including FastMCP integration
- **91 integration tests** covering WebSocket communication and MCP functionality
- **29 unit tests** covering individual component functionality
- **8 additional tests** in root test directory for end-to-end coordination

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

**Tabs Management:** `tabs.list`, `tabs.get_active`, `tabs.create`, `tabs.close`, `tabs.switch`, `tabs.duplicate`

**History Operations:** `history.query`, `history.get_recent`, `history.delete_item`, `history.clear_range`

**Bookmark Management:** `bookmarks.list`, `bookmarks.search`, `bookmarks.create`, `bookmarks.delete`, `bookmarks.update`, `bookmarks.create_folder`

**Navigation Control:** `navigation.back`, `navigation.forward`, `navigation.reload`, `navigation.go_to_url`

**Content Access:** `content.get_text`, `content.get_html`, `content.get_title`, `content.get_url`, `content.execute_script`

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