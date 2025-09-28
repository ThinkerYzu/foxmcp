# Development Guide

Complete guide for FoxMCP development, including setup, workflow, testing, and maintenance.

## Development Workflow

**Quick development cycle:**
1. `make dev` - Setup environment
2. `make build` - Build extension
3. Load extension in Firefox (see installation guide)
4. `make run-server` - Start server
5. `make test` - Run tests

## Development Commands

### Setup and Installation
```bash
make setup              # Install all dependencies + setup test import system
make install           # Install server dependencies only
make setup-test-imports # Create symbolic links for test import system
make dev               # Setup development environment
```

### Building and Packaging
```bash
make build             # Build extension only
make package           # Build and create distributable packages (XPI + server ZIP)
```

### Testing
```bash
make test              # Run all tests (auto-creates test imports)
make test-unit         # Run unit tests only (auto-creates test imports)
make test-integration  # Run integration tests only (auto-creates test imports)
make check             # Run linting + tests
```

### Development
```bash
make run-server        # Start WebSocket server
make lint              # Run Python linting
make format            # Format Python code
```

### Maintenance
```bash
make clean             # Clean build artifacts + remove test import symlinks
make clean-all         # Deep clean including dependencies
make status            # Show project status + test import system status
```

## Test Import System

The project uses an automated test import system to ensure consistent module imports across all test files, regardless of how they're executed (pytest, direct execution, different working directories).

### Key Features

- **Automatic path setup** - No manual `sys.path` manipulation needed
- **Symbolic links** - Managed automatically by Makefile
- **Git-friendly** - Only source files tracked, symlinks ignored
- **Zero configuration** - Works seamlessly across all test environments

### How it Works

1. `tests/test_imports.py` - Main import utility (tracked by git)
2. Symbolic links in subdirectories (ignored by git, created by Makefile):
   - `tests/integration/test_imports.py` → `../test_imports.py`
   - `tests/unit/test_imports.py` → `../test_imports.py`

### Usage in Test Files

```python
import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from test_config import TEST_PORTS
```

### Developer Workflow

- `make setup` automatically creates symbolic links
- `make test*` commands ensure symbolic links exist
- `make clean` removes symbolic links for cleanup
- `make status` shows symbolic link status

## Project Structure

```
foxmcp/
├── docs/               # Documentation
├── extension/          # Firefox extension source
├── server/            # Python server implementation
├── tests/             # Test suite
│   ├── unit/          # Unit tests
│   ├── integration/   # Integration tests
│   └── fixtures/      # Test data
├── venv/              # Python virtual environment
├── Makefile           # Build system
└── requirements.txt   # Python dependencies
```

## Extension Development

### Building the Extension

```bash
# Build and package extension
make package

# Extension will be created at: dist/packages/foxmcp@codemud.org.xpi
# Server package will be created at: dist/packages/foxmcp-server.zip
```

### Loading in Firefox

**Method 1: Temporary Add-on (Development)**
1. Open Firefox
2. Navigate to `about:debugging`
3. Click "This Firefox"
4. Click "Load Temporary Add-on"
5. Select `dist/packages/foxmcp@codemud.org.xpi`

**Method 2: Persistent Installation with Preferences**
1. Open Firefox
2. Go to `about:config` (accept the warning if shown)
3. Search for and modify these preferences:
   - Set `xpinstall.signatures.required` to `false`
   - Set `extensions.experiments.enabled` to `true` (if needed for advanced features)
4. Go to `about:addons`
5. Click gear icon → "Install Add-on From File"
6. Select `dist/packages/foxmcp@codemud.org.xpi`

**Method 3: Profile Directory Installation (Script)**
```bash
# Find your profile directory in about:profiles, then:
./scripts/install-xpi.sh /path/to/firefox/profile
```

This script automatically:
- Installs the extension to the profile's extensions directory
- Configures `user.js` to allow unsigned extensions (`xpinstall.signatures.required = false`)
- Sets proper file permissions

**Installation Notes:**
- **Method 1**: Extension is removed when Firefox restarts (best for quick testing)
- **Method 2**: Persistent installation that survives restarts, requires manual preference changes
- **Method 3**: Automated installation with preference configuration, most reliable for development
- Unsigned extensions cannot be installed through `about:addons` without preference changes
- All methods work with unsigned extensions in development mode

### Extension Architecture

```
extension/
├── manifest.json      # Extension configuration
├── background.js      # Service worker (WebSocket client)
├── content.js         # Content script injection
└── popup/            # Extension popup UI
    ├── popup.html
    ├── popup.js
    └── popup.css
```

## Server Development

### Architecture

```python
# Server components
server/
├── server.py          # Main WebSocket server
├── fastmcp_tools.py   # MCP tool definitions
└── utils.py           # Utility functions
```

### Adding New Browser Functions

1. **Add to Extension** (`extension/background.js`):
```javascript
// Add new action handler
actions.new_function = async (data) => {
    // Implementation using browser APIs
    return result;
};
```

2. **Add MCP Tool** (`server/fastmcp_tools.py`):
```python
@app.tool()
def new_function(param1: str, param2: int = 10) -> str:
    """Description of the new function"""
    return send_browser_request({
        "action": "new_function",
        "data": {"param1": param1, "param2": param2}
    })
```

3. **Add Tests**:
```python
# tests/integration/test_new_function.py
@pytest.mark.asyncio
async def test_new_function(self, server_with_extension):
    # Test implementation
    pass
```

## Testing

### Test Structure

```
tests/
├── conftest.py        # Shared fixtures and configuration
├── test_imports.py    # Automatic path setup utility
├── unit/              # Unit tests for individual components
│   ├── test_server.py
│   └── test_protocol.py
└── integration/       # End-to-end tests with real browser
    ├── test_tabs.py
    ├── test_history.py
    └── test_bookmarks.py
```

### Writing Tests

#### Unit Tests

```python
import test_imports  # Always first import
import pytest
from server.server import FoxMCPServer

def test_server_initialization():
    server = FoxMCPServer()
    assert server.host == "localhost"
    assert server.port == 8765
```

#### Integration Tests

```python
import test_imports  # Always first import
import pytest

@pytest.mark.asyncio
async def test_browser_function(self, server_with_extension):
    """Test with real Firefox browser"""
    server = server_with_extension['server']

    # Test browser functionality
    response = await server.send_request({
        "action": "tabs_list",
        "data": {}
    })

    assert response["type"] == "response"
```

### Running Specific Tests

```bash
# Run specific test file
pytest tests/unit/test_server.py -v

# Run specific test method
pytest tests/integration/test_tabs.py::TestTabs::test_tab_creation -v

# Run with coverage
pytest --cov=server --cov-report=html

# Run integration tests with Firefox
FIREFOX_PATH=/path/to/firefox make test-integration
```

## Debugging

### Server Debugging

```bash
# Run server with debug logging
python server/server.py --debug

# Or set environment variable
export FOXMCP_DEBUG=1
python server/server.py
```

### Extension Debugging

1. Open Firefox Developer Tools (F12)
2. Go to "Console" tab
3. Extension logs will appear with `[FoxMCP]` prefix
4. Check "Background Script" console in `about:debugging`

### Test Debugging

```bash
# Run tests with verbose output
pytest -v -s

# Debug specific test
pytest tests/integration/test_tabs.py::test_tab_creation -v -s --pdb

# Keep Firefox open after test failure
pytest -v -s --keep-firefox
```

## Code Style

### Python Code Style

```bash
# Format code
make format

# Check linting
make lint

# Fix common issues
black server/ tests/
isort server/ tests/
flake8 server/ tests/
```

### JavaScript Code Style

```bash
# Format extension code
cd extension/
npx prettier --write *.js popup/*.js

# Check for issues
npx eslint *.js popup/*.js
```

## Performance

### Profiling Server

```python
import cProfile
import pstats

# Profile server performance
profiler = cProfile.Profile()
profiler.enable()

# Run server operations
server = FoxMCPServer()
# ... server operations ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative').print_stats(20)
```

### Memory Usage

```bash
# Monitor memory usage
python -m memory_profiler server/server.py

# Profile specific function
@profile
def function_to_profile():
    # Function implementation
    pass
```

## Security Considerations

### Secure Development Practices

1. **Input Validation**: Always validate user inputs
2. **Localhost Only**: Server binds only to localhost
3. **No Remote Access**: Never expose server to external networks
4. **Script Validation**: Predefined scripts use secure path validation
5. **Error Handling**: Don't expose internal details in error messages

### Security Testing

```bash
# Run security-focused tests
pytest tests/security/ -v

# Check for common vulnerabilities
bandit -r server/

# Audit dependencies
pip-audit
```

## Continuous Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: make setup
      - run: make test
      - run: make lint
```

## Release Process

### Version Management

1. Update version in `extension/manifest.json`
2. Update version in `server/server.py`
3. Update `docs/PLAN.md` with release notes
4. Create git tag: `git tag v1.0.0`

### Building Release

```bash
# Build release packages
make package

# Creates:
# - extension/foxmcp.xpi (Firefox extension)
# - dist/foxmcp-server.zip (Server package)
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Run `make setup-test-imports`
2. **Firefox Not Found**: Set `FIREFOX_PATH` environment variable
3. **Port Conflicts**: Use custom ports with `--port` flag
4. **Extension Not Loading**: Check `about:debugging` for errors
5. **Tests Failing**: Ensure Firefox is installed and accessible

### Getting Help

1. Check existing documentation in `docs/`
2. Review test files for usage examples
3. Enable debug logging for detailed information
4. Check browser console for extension errors
5. Review server logs for connection issues

### Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Make changes and add tests
4. Run test suite: `make test`
5. Submit pull request

See project README for contribution guidelines.