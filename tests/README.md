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
│   ├── test_mcp_handler.py # MCP handler tests
│   └── test_protocol.py    # Protocol message tests
├── integration/            # Integration tests
│   └── test_websocket_communication.py
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

### Run Tests with Firefox Extension

```bash
# From project root directory
make test-with-firefox

# With custom Firefox path
FIREFOX_PATH=/path/to/firefox make test-with-firefox
```

This creates a temporary Firefox profile, installs the extension, runs Firefox in background, and executes the test suite with the extension loaded.

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

- **test_mcp_handler.py**: Tests MCP integration
  - Tool registration
  - Request forwarding
  - Action mapping
  - Parameter validation

- **test_protocol.py**: Tests message protocol
  - Message structure validation
  - JSON serialization
  - Error code definitions
  - Data structure validation

### Integration Tests

- **test_websocket_communication.py**: Tests end-to-end WebSocket communication
  - Extension connection testing (now enabled)
  - Message exchange validation
  - Connection state management
  - Message routing verification
  - Connection recovery scenarios
  - Error handling scenarios

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

## Continuous Integration

Tests should be run before:
- Committing code changes
- Creating pull requests
- Deploying to production

All tests must pass before merging changes.