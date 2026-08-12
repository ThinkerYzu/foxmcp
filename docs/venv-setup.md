# Virtual Environment Setup

## Created Virtual Environment with Requirements.txt

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install server dependencies
pip install -r server/requirements.txt

# Install test dependencies
pip install -r tests/requirements.txt
```

## Installed Packages

Verified 2026-08-12 against the project venv:

- ✅ **websockets 17.0.1** - WebSocket server/client
- ✅ **fastmcp 3.4.7** - MCP server framework
- ✅ **pytest 9.1.1** - Testing framework
- ✅ **pytest-asyncio 1.4.0** - Async test support
- ✅ **pytest-mock 3.15.1** - Mocking for tests
- ✅ **pytest-cov 7.1.0** - Coverage plugin
- ✅ **coverage 7.15.4** - Code coverage reporting
- ✅ **aiohttp 3.14.3** - HTTP client used by the request-monitoring tests

## Running the Server

```bash
# Activate virtual environment
source venv/bin/activate

# Start the server
cd server && python server.py
```

## Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
cd tests && python run_tests.py

# Or use make command
make test
```

## Server Status
- ✅ Virtual environment created at `./venv/`
- ✅ Python 3.13.3 in virtual environment
- ✅ All dependencies installed from requirements.txt files
- ✅ Server successfully starts and listens on localhost:8765
- ⚠️ Deprecation warning: `WebSocketServerProtocol is deprecated` (non-blocking)

## Requirements Files Updated
- **server/requirements.txt**: Removed `fastmcp`, `asyncio`, `json` (not needed yet/built-in)
- **tests/requirements.txt**: Removed `fastmcp` (not needed yet)

## Next Steps
1. Load browser extension to test connection
2. Check connection status in extension popup
3. Run tests to validate implementation
4. Verify server communication works

## Deactivate Virtual Environment
```bash
deactivate
```