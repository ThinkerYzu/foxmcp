# FoxMCP Test Suite

Unit and integration tests for FoxMCP. The integration tests launch a real Firefox
with the extension installed, so a full run takes about ten minutes.

## Running Tests

```bash
make test              # everything, with coverage (builds the package first)
make test-unit         # unit only — fast, no Firefox
make test-integration  # integration only
make check             # lint + test
```

Dependencies go into the project venv, not whatever interpreter is active:

```bash
make setup             # server + test dependencies, plus the import symlinks
```

`make setup` uses `venv/bin/pip`. Running a bare `pip install -r requirements.txt`
installs into the wrong interpreter and leaves `make test-unit` failing with
`No module named pytest`.

### Expected result

**197 passing, 0 skipped** — 59 unit and 138 integration.

A run that finishes in about seventy seconds instead of ten minutes is a warning,
not good news: it means the Firefox integration tests skipped themselves. Check
that Firefox can be found (see [Finding Firefox](#finding-firefox)).

### Firefox path

Tests find Firefox on `PATH` automatically. Override it when you want a specific build:

```bash
FIREFOX_PATH=/home/you/tools/firefox make test-integration
```

## What Gets Run

`run_tests.py` collects `unit/` and `integration/` only. The `test_*.py` files that sit
directly in `tests/` are standalone scripts — helpers and manual end-to-end drivers —
and are **not** part of the 197. Run them by hand if you need them.

| Directory | Tests | Needs Firefox |
|---|---|---|
| `unit/` | 59 | no |
| `integration/` | 138 | yes |
| `tests/*.py` (root) | not collected | varies |

### Unit tests

| File | Tests | Covers |
|---|---|---|
| `test_protocol.py` | 14 | Message structure, JSON serialization, error codes |
| `test_window_handlers.py` | 14 | Window action handlers |
| `test_request_monitoring.py` | 11 | Web request capture logic |
| `test_ping_pong.py` | 8 | Ping-pong protocol |
| `test_server.py` | 7 | Server init, connection handling, message processing |
| `test_screenshot_filename.py` | 5 | Screenshot filename generation |

### Integration tests

| File | Tests | Covers |
|---|---|---|
| `test_window_management.py` | 11 | Window creation, focus switching, cross-window tabs |
| `test_history_management.py` | 10 | History query, recent, time ranges, concurrency |
| `test_mcp_integration.py` | 10 | FastMCP tool init and call handling |
| `test_mcp_protocol_compliance.py` | 10 | Tool schemas, parameter formats, HTTP endpoint |
| `test_ping_pong_integration.py` | 10 | Bidirectional ping-pong over a live socket |
| `test_bookmark_management.py` | 8 | Bookmark CRUD and folders |
| `test_real_websocket_communication.py` | 8 | Protocol formats, timeouts, multi-client |
| `test_test_helper_protocol.py` | 8 | The `test.*` action namespace |
| `test_live_server_communication.py` | 7 | Real server startup, shutdown, recovery |
| `test_websocket_communication.py` | 7 | Connection state and message routing |
| `test_firefox_extension_communication.py` | 6 | Real Firefox with the extension installed |
| `test_history_with_content.py` | 6 | History entries alongside page content |
| `test_mcp_server_integration.py` | 6 | Dual-port startup, MCP client connections |
| `test_request_monitoring_integration.py` | 6 | Request capture through the MCP layer |
| `test_ui_storage_sync.py` | 6 | Popup settings persistence |
| `test_browser_functionality.py` | 5 | Tabs, script execution, reload, content, screenshots |
| `test_real_firefox_communication.py` | 5 | Extension-server message exchange in a real browser |
| `test_request_monitoring_end_to_end.py` | 5 | Capture a request and read its content back |
| `test_history_mcp_integration.py` | 4 | History through the MCP tool surface |

## Test Import System

Test files never manipulate `sys.path`. Importing `test_imports` first does it:

```python
import test_imports  # always the first import
from server.server import FoxMCPServer
from test_config import TEST_PORTS
from firefox_test_utils import FirefoxTestManager
```

`tests/test_imports.py` is the real file. The copies in `unit/` and `integration/` are
symlinks to it, created by `make setup-test-imports` and removed by `make clean`. They
are not tracked by git. If imports break, run `make setup-test-imports`; `make status`
shows whether the symlinks exist.

## Fixtures

`conftest.py` provides the shared fixtures. Two matter:

- **`server_with_extension`** — a running server with Firefox connected and verified,
  torn down afterwards. Use it for anything touching a real browser.
- **`auto_dynamic_ports`** — session-scoped and autouse. Patches `FoxMCPServer.__init__`
  so tests never bind the production ports.

The rest are mock data: `sample_request`, `sample_response`, `sample_error`,
`mock_websocket`, `mock_chrome_api`, `sample_tab_data`, `sample_history_data`,
`sample_bookmark_data`.

### Using `server_with_extension`

```python
import test_imports  # always the first import
import pytest

@pytest.mark.asyncio
async def test_browser_feature(self, server_with_extension):
    server = server_with_extension['server']

    response = await server.send_request_and_wait({
        "id": "test-001",
        "type": "request",
        "action": "tabs.list",
        "data": {}
    })
    assert response["type"] == "response"
```

The dict also carries `firefox`, `test_port`, and `mcp_port`.

### Adding an MCP client

`server_with_extension` gives you the server, not an MCP client. Wrap it:

```python
@pytest_asyncio.fixture
async def full_system(self, server_with_extension):
    from mcp_client_harness import DirectMCPTestClient

    mcp_client = DirectMCPTestClient(server_with_extension['server'].mcp_tools)
    yield {**server_with_extension, 'mcp_client': mcp_client}
    await mcp_client.disconnect()

@pytest.mark.asyncio
async def test_mcp_feature(self, full_system):
    await full_system['mcp_client'].connect()
    result = await full_system['mcp_client'].call_tool("tabs_list")
    assert not result.get('isError', False)
```

### Reaching a tool directly

`FastMCP` exposes `get_tool(name)` for one tool and `list_tools()` for all of them.
Both are async. Neither `get_tools()` nor `_tool_manager` exists in fastmcp 3.x —
tests that used them broke on upgrade.

```python
tabs_list = (await mcp_tools.mcp.get_tool("tabs_list")).fn
result = await tabs_list()

names = [tool.name for tool in await mcp_tools.mcp.list_tools()]
```

## Port Isolation

Tests must never touch the live server on 8765/3000. `auto_dynamic_ports` rewrites
every `FoxMCPServer` construction to use the high test ports from
`port_coordinator.py`:

| Purpose | Port |
|---|---|
| Test WebSocket server | 40400 |
| Test MCP server | 40600 |
| Reserved (`websocket`) | 40000 |
| Reserved (`mcp`) | 40200 |

The extension's build-time fallback port also changes from 8765 to 48765, so an
extension in a test profile cannot reach a development server even if its stored
settings are missing.

Each port is fixed rather than drawn from a range. Tests run one at a time, so
only one server holds a port at a time, and a fixed port is what lets the
Firefox profile cache hit — a cached profile records the port it was built for.
The cost is that **two suite runs at once collide**: the second fails to bind
with `[errno 98] address already in use`. Run one suite at a time.

Firefox learns its port through a coordination file written by
`coordinated_test_ports()` and read by `FirefoxTestManager` during profile setup.

## Firefox Integration

### Setup

Always use the consolidated method. The older `create_test_profile()` /
`install_extension()` / `start_firefox()` trio was removed, and the `_`-prefixed
internals are not for direct use.

```python
success = firefox.setup_and_start_firefox(headless=True)
```

Each run gets a temporary profile with `storage.sync` disabled, so test settings
cannot leak into a real browser profile. Profiles and processes are cleaned up
afterwards.

### Finding Firefox

`resolve_firefox_path()` in `firefox_test_utils.py` takes an explicit path, then
`$FIREFOX_PATH`, then falls back to `shutil.which()`. That last step matters:
`os.path.exists("firefox")` is false for a bare command name because it never
consults `PATH`. Checking only `os.path.exists()` silently skipped 59 integration
tests on a machine where Firefox was installed — and a skip reads as a pass on the
summary line.

### Waiting for the connection

Wait for the connection event, not a fixed sleep:

```python
connected = await server.wait_for_extension_connection(timeout=10.0)

connected = await firefox.async_wait_for_extension_connection(
    timeout=15.0, server=server
)
```

### After changing the extension

Test profiles are cached. Editing `extension/` has no effect until the cache is cleared:

```bash
make clean && make package && rm -rf dist/profile-cache/*
```

## Rules

- **Test URLs are `example.org`.** Never `httpbin.org` or any other live service —
  tests must not depend on someone else's uptime.
- **`ENABLE_DEBUG_LOGGING_TO_SERVER` goes back to `false`** in `extension/background.js`
  before committing.
- **Run the suite before committing.** All 197 must pass.

## Coverage

```bash
cd tests && pytest --cov=../server --cov-report=html --cov-report=term-missing
```

Reports land in `tests/htmlcov/`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named pytest` | Installed into the wrong interpreter | `venv/bin/pip install -r tests/requirements.txt` |
| Whole suite finishes in ~70 s | Integration tests skipped themselves | Check Firefox resolution; a full run is ~10 minutes |
| `SKIPPED ... Firefox not found` | Firefox not on `PATH` | `FIREFOX_PATH=/path/to/firefox make test` |
| `AttributeError: ... 'get_tools'` | Removed in fastmcp 3.x | Use `list_tools()` / `get_tool()` |
| `AttributeError: ... '_tool_manager'` | Private attribute, gone in 3.x | Use `get_tool()` |
| Extension change has no effect | Stale cached profile | `make clean && make package && rm -rf dist/profile-cache/*` |
| Import errors | Missing symlinks | `make setup-test-imports` |
