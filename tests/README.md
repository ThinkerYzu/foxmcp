# FoxMCP Test Suite

Unit and integration tests for FoxMCP. The integration tests launch a real Firefox
with the extension installed; allow about fifteen to twenty minutes for a full run.

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

Every test in the selected suite must pass without skips. Test totals change as
cases are added, removed or parametrized; a fixed count is not a completeness
gate. CI validates the JUnit report with `scripts/check-test-report.py`, which
rejects failed/skipped tests and missing required modules.

To inspect current collection without running test bodies, use the project venv
from the repository root:

```bash
venv/bin/python -m pytest --collect-only -q tests/unit tests/integration
```

To apply the same completeness check locally, run from the repository root:

```bash
PYTEST_ADDOPTS="--junitxml=$PWD/tests/junit.xml" \
  FIREFOX_PATH=/path/to/firefox make test
venv/bin/python scripts/check-test-report.py tests/junit.xml
```

`make test` alone does not run the report guard. For a unit-only report, use
`make test-unit` and pass `--kind unit` to the guard. A fast run or a successful
pytest exit alone does not establish that browser tests ran; inspect skips and
validate the report. See [Finding Firefox](#finding-firefox).

Keep commit-specific counts, durations and validation results in CI reports or
dated validation records. This guide describes how to test the current checkout.

#### Monitor option isolation

`unit/test_monitor_option_validation.py` uses actual MCP calls to verify strict
nested types, unknown-field rejection and no browser calls on invalid options.
`integration/test_monitor_options_end_to_end.py` drives a local page in Firefox
through MCP, checking overlapping monitors with different byte/type policies,
disabled request/response capture, complete page delivery, raw-protocol
validation, monitor membership and reads after stop.

#### Startup composition coverage

`unit/test_server_composition.py` checks the source roles documented in the
[architecture diagram](../docs/architecture.md#system-overview). Browser-only
and automatic-worker startup must not construct MCP tools/frontends; shared
stdio must not construct a browser owner. Direct frontends use BrowserServer
without an adapter, own their local-file service and supply HTTP-session
liveness for monitor cleanup. CLI tool validation rejects internal helper names
without constructing FastMCP, and accepts every registered tool name.

The real-process proxy, shared-stdio, multiple-profile and final-package checks
continue to verify routing, uploads and cleanup across process boundaries.

### Windows broker attachment regression

`unit/test_windows_worker_bootstrap.py` runs the actual bootstrap with controlled
Win32 API results to verify gating, timeout/failure cleanup, argument forwarding
and nonzero script exits. These portable checks do not prove native WMI behavior.
`windows/test_worker.py` retains the hidden-console/environment check and adds
forced broker-attachment delay with successful exit, explicit SystemExit(7),
and an unhandled startup exception (exit 1), plus a real worker heartbeat after
broker termination. Startup-exception checks also require its traceback in the
worker log. Broker exit-code assertions include that log in failure output.
Native Windows CI runs the Windows suite across Python 3.10/3.14 and
PowerShell 5.1/7.

### Discovery shutdown regression

`unit/test_single_instance_election.py` uses a real loopback HTTP server to
reset an accepted discovery connection, then return valid metadata on the next
probe. This covers network resets during shared-worker teardown.
The probe treats network transport failures as temporary unavailability while
continuing to reject completed incompatible responses. Existing shared-instance
and container lifecycle integration tests cover normal worker shutdown/restart.

## Source-installation smoke checks

CI tests source installation separately on Python 3.10 and 3.14, including HTTP
and stdio startup, tool discovery and tool filtering. The stdio check runs without
a browser and passes `profile_id=1`, a valid integer target, to verify that the
bridge promptly reports a disconnected profile. A string placeholder fails schema
validation before reaching routing. Keep these workflow inputs aligned with tool
schemas when changing the API; they are outside the pytest module guard.

### Firefox path

Use Firefox Developer Edition for the unsigned test extension. Release and Beta
enforce signing and cannot load it. Tests find Firefox on `PATH` automatically;
set `FIREFOX_PATH` when Developer Edition is installed elsewhere:

```bash
FIREFOX_PATH=/path/to/firefox-developer-edition/firefox make test-integration
```

## What Gets Run

`run_tests.py` collects `unit/` and `integration/` only. The `test_*.py` files that sit
directly in `tests/` are standalone scripts — helpers and manual end-to-end drivers —
and are **not** part of the normal suite. Run them by hand if you need them.

| Directory | Collection | Needs Firefox |
|---|---|---|
| `unit/` | Normal suite | no |
| `integration/` | Normal suite | Some modules |
| `windows/` | Separate native Windows suite | no |
| `tests/*.py` (root) | Standalone drivers, not collected by the runner | varies |

### Unit tests

Selected test modules, including local-file coverage:

| File | Covers |
|---|---|
| `test_makefile.py` | Isolated developer commands: parallel stage ordering, virtualenv selection, spaced Firefox paths and removal of unmanaged stop/restart helpers |
| `test_github_installer.py` | Real HTTP download failures, checksums, corrupt archives and installed upload example |
| `test_release_report.py` | Missing integration modules, multiple JUnit suites, skipped/failed tests and empty reports |
| `test_file_transfer.py` | Streaming integrity, MIME, regular-file validation, single-use grants, expiry, revocation, capacity, shutdown and content-group registration |
| `test_tab_move.py` | `tabs_move`'s request and result, and the window scoping on `tabs_list` |
| `test_protocol.py` | Message structure, JSON serialization, error codes |
| `test_window_handlers.py` | Window action handlers |
| `test_predefined_script_logging.py` | Predefined script audit/validation and raw/predefined script response timeouts |
| `test_request_monitoring.py` | Web request capture logic |
| `test_ping_pong.py` | Ping-pong protocol |
| `test_connection_versions.py` | Version parsing and advisory diagnostics; per-profile connection tests are in `test_server.py` |
| `test_server.py` | Server-assigned integer IDs, handshake validation, routing isolation, reconnect invalidation and monitor ownership |
| `test_server_composition.py` | Startup role isolation, direct/remote injection, file-service ownership, HTTP monitor liveness and tool-name validation |
| `test_screenshot_filename.py` | Screenshot filename generation |
| `test_profile_names.py` | Registered/group name precedence, real Linux profile locks, stale copies and unavailable/ambiguous metadata |

### Integration tests

Selected test modules:

| File | Covers |
|---|---|
| `test_browser_connection_versions.py` | Real Firefox hello plus actual background/popup scripts: protocol-3 registration/refusal, release mismatch, stale sockets and edit-preserving refresh |
| `test_script_consent.py` | Actual consent-controller source, queue/deadline/target behavior and real-extension policy isolation |
| `test_extension_settings.py` | Actual background, Popup/Options scripts and HTML: validation, autosave, reset, storage failures, constant retries, stale timers, profile registration/errors and live status |
| `test_file_loading.py` | File integrity and metadata, predefined input assignment, events, empty files, tab isolation, expiry and navigation during a transfer |
| `test_window_management.py` | Window creation, focus switching, cross-window tabs |
| `test_history_management.py` | History query, recent, time ranges, concurrency |
| `test_mcp_integration.py` | FastMCP tool init and call handling |
| `test_mcp_protocol_compliance.py` | Tool schemas, parameter formats, HTTP endpoint |
| `test_ping_pong_integration.py` | Bidirectional ping-pong over a live socket |
| `test_bookmark_management.py` | Bookmark CRUD and folders |
| `test_real_websocket_communication.py` | Protocol formats, timeouts, multi-client |
| `test_test_helper_protocol.py` | The `test.*` action namespace |
| `test_live_server_communication.py` | Real server startup, shutdown, recovery |
| `test_websocket_communication.py` | Connection state and message routing |
| `test_firefox_extension_communication.py` | Real Firefox with the extension installed |
| `test_history_with_content.py` | History entries alongside page content |
| `test_mcp_server_integration.py` | Dual-port startup, MCP client connections |
| `test_request_monitoring_integration.py` | Request capture through the MCP layer |
| `test_ui_storage_sync.py` | Legacy storage/effective-config projections retained for protocol compatibility |
| `test_browser_functionality.py` | Tabs, script execution, reload, content, screenshots |
| `test_connection_origin.py` | The origin allowlist on the extension WebSocket |
| `test_mcp_port_not_web_reachable.py` | That no web page can reach the MCP port — see [Dependency-held guarantees](#dependency-held-guarantees) |
| `test_real_firefox_communication.py` | Extension-server message exchange in a real browser |
| `test_request_monitoring_end_to_end.py` | Capture and read response bodies, including ten tiny local JSON responses that expose header/filter ordering races |
| `test_tab_move_end_to_end.py` | Gathering tabs into a new window, and reordering within one |
| `test_history_mcp_integration.py` | History through the MCP tool surface |
| `test_multiple_profiles.py` | Explicit routing, profile isolation, reconnect/restart and concurrent HTTP/stdio clients |

## Multiple-profile coverage

[integration/test_multiple_profiles.py](integration/test_multiple_profiles.py)
covers complementary browser and transport scenarios:

| Test | Browser side | Call path | Checks |
|---|---|---|---|
| `test_two_real_firefox_profiles_reconnect_and_restart_independently` | Two real Firefox processes with disposable profiles | Calls registered tool functions directly; MCP HTTP is disabled for this test | Profile discovery/name resolution, separate tab creation/listing, reconnect and independent restart each replacing identity and rejection of the old target. The other profile stays registered. |
| `test_profiles_are_visible_and_routable_from_http_and_shared_stdio` | Two simulated extension responders on real WebSockets | Actual FastMCP HTTP and shared-stdio clients | Discovery, concurrent routing despite identical native IDs, upload delivery to the correct profile, pending-request failure on disconnect, surviving-profile access and client-owned monitor cleanup. |

Both run in the normal integration suite. Neither combines two real
Firefox profiles with both MCP transports. The final-package smoke check below
uses one disposable Firefox profile per transport to exercise every tool.

## Release package smoke test

`make package` writes both archives and a fresh `SHA256SUMS` manifest on every
build. CI runs `package_smoke.py` after lint, unit, integration and source-install checks
pass. It serves the final archives through a local HTTP fixture, runs the actual
installer in an empty directory with its own dependency venv, and starts the
installed server from outside the checkout. A real Firefox loads the final XPI.
An ordinary page submits a multipart upload over both HTTP and stdio MCP; the
receiver verifies the filename, MIME override, SHA-256 and change event. The
installed `set-file-input.py` helper must assign the file and release its handle
before the form submits, and the page must display success.

To repeat locally, run from the repository root using the project venv and
Developer Edition:

```bash
make package
FIREFOX_PATH=/path/to/firefox venv/bin/python \
  tests/package_smoke.py --packages dist/packages
```

Each transport runs the existing tool scenarios, with read-back checks for:

- Windows: create, list, inspect, focus, resize and close.
- Tabs: create, list, switch, move, group, update/query groups, ungroup and close.
- Navigation/content: navigate, back, forward, reload, HTML, text and JavaScript.
- Screenshots: save and validate a nonempty PNG.
- History: observe visited URLs in searches/recent items, delete and verify removal.
- Bookmarks: create folders/bookmark, update/search, move and delete with read-back.
- Requests: start capture, fetch local JSON, verify captured status/body and stop.
- Debug connection status, plus local-file loading and the installed upload helper.

A new tool without a smoke scenario is listed in the report's `uncovered_tools`.
Ordinary PR/push CI reports this gap while continuing to require all existing
scenarios to pass. Release rehearsals and tags enforce full advertised-tool
coverage and fixed tool totals. Direct local runs enforce these gates by default;
set `FOXMCP_RELEASE_CHECKS=0` to match ordinary CI. The same mode controls fixed
totals in source, Windows, wheel/sdist and shared-stdio container checks. See
[CI policy](../docs/development.md#continuous-integration).

Each mode starts its own test browser after the server is ready, avoiding the
finite reconnect budget in the test profile. Only disposable profile data and
local fixture pages are used. Windows, bookmarks, monitors and tabs are cleaned up.

The printed work directory retains installer/server logs, upload receipts,
`smoke-http.json`, `smoke-stdio.json` and screenshots. Reports record each tool
call and completed feature check, including partial evidence if a check fails.
GitHub retains these files in its `package-smoke` artifact.
No model credentials or running FoxMCP host are needed. It creates a fresh venv
and installs dependencies, so access to the Python package index is required.
The MCP and WebSocket smoke servers reserve test ports 31086/31087; the HTTP
fixture uses an automatically assigned port. Do not run another agent or package
evaluation simultaneously.

`python scripts/check-test-report.py REPORT.xml` requires successful test cases
from every unit and integration module on disk, with no skips; `--kind unit`
checks only unit modules. This detects missing browser collection even when
hundreds of unit tests pass. CI checks unit tests and source installation on
Python 3.10 and 3.14; the full browser suite uses 3.14.

## Manual agent upload evaluation

`agent_file_upload_eval.py` runs a fresh Codex or Claude agent with the actual
MCP schemas, a real Firefox instance and a local CSV importer. The task supplies
only a local file path and destination URL. Built-in filesystem and shell use
is prohibited; Claude's built-in tools are disabled. No upload example or tool
name is supplied in the task prompt.

Use an authenticated CLI for the chosen agent and a packaged extension built
from this checkout. Run from the repository root:

```bash
make package
PYTHONPATH=.:tests FIREFOX_PATH=/path/to/firefox \
  venv/bin/python tests/agent_file_upload_eval.py
# Repeat with Claude:
PYTHONPATH=.:tests FIREFOX_PATH=/path/to/firefox \
  venv/bin/python tests/agent_file_upload_eval.py --agent-cli claude
```

This invokes a model and is deliberately excluded from pytest. The printed
artifact directory contains the prompt, schemas, JSONL transcript, final answer,
upload receipt and result. A pass requires use of `content_load_file`, the original
filename, inferred MIME type, an exact SHA-256 match and a page change event.
Inspect the transcript for input assignment, handle release and the final page
readout. It uses isolated test ports 31086/31087; run one evaluation at a time.

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
async def test_browser_feature(server_with_extension):
    from test_config import profile_connection

    server = server_with_extension['server']
    profile_id = profile_connection(server).profile_id

    response = await server.send_request_and_wait({
        "id": "test-001",
        "type": "request",
        "action": "tabs.list",
        "profile_id": profile_id,
        "data": {}
    })
    assert response["type"] == "response"
```

The fixture is a `FixtureResult` object with keyed access to `server`, `firefox`,
`test_port` and `mcp_port`. It is not a dictionary and cannot be unpacked with
`**`.

### Adding an MCP client

`server_with_extension` gives you the server, not an MCP client. The direct
harness calls registered tool functions without exercising MCP transport. For
HTTP/stdio transport coverage, use real FastMCP clients as shown in
[integration/test_multiple_profiles.py](integration/test_multiple_profiles.py).
For direct tool checks, wrap the fixture explicitly:

```python
import test_imports
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def full_system(server_with_extension):
    from mcp_client_harness import DirectMCPTestClient

    mcp_client = DirectMCPTestClient(server_with_extension['server'].mcp_tools)
    try:
        yield {
            'server': server_with_extension['server'],
            'mcp_client': mcp_client,
        }
    finally:
        await mcp_client.disconnect()

@pytest.mark.asyncio
async def test_mcp_feature(full_system):
    await full_system['mcp_client'].connect()
    from test_config import profile_connection
    profile_id = profile_connection(full_system['server']).profile_id
    result = await full_system['mcp_client'].call_tool(
        "tabs_list", {"profile_id": profile_id})
    assert not result.get('isError', False)
```

### Reaching a tool directly

`FastMCP` exposes `get_tool(name)` for one tool and `list_tools()` for all of them.
Both are async. Neither `get_tools()` nor `_tool_manager` exists in fastmcp 3.x —
tests that used them broke on upgrade.

```python
tabs_list = (await mcp_tools.mcp.get_tool("tabs_list")).fn
result = await tabs_list(profile_id=profile_id)

names = [tool.name for tool in await mcp_tools.mcp.list_tools()]
```

## Port Isolation

Tests must never touch the live server on 8765/3000. `auto_dynamic_ports` rewrites
every `FoxMCPServer` construction to use the test ports from
`port_coordinator.py`, which sit below Linux's ephemeral range (32768-60999)
so a client dialing one can never be given it as its own local port:

| Purpose | Port |
|---|---|
| Test WebSocket server | 30400 |
| Test MCP server | 30600 |
| Reserved (`websocket`) | 30000 |
| Reserved (`mcp`) | 30200 |

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
consults `PATH`. A failed lookup can skip browser tests; use the report guard
to reject incomplete runs.

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

### Connecting as the extension

A test that stands in for the extension has to look like one. The server accepts only
`moz-extension://` origins — the check that keeps web pages off the socket — so use the
helper rather than connecting directly:

```python
from test_config import connect_as_extension

async with connect_as_extension(f"ws://localhost:{port}") as websocket:
    ...
```

The helper sends an extension Origin and completes the protocol-3 profile
registration. `websocket.profile_id` exposes the server-assigned identity,
discovered through the local proxy; callers cannot choose it. Its first `recv()`
returns the buffered server greeting. A plain connection without the Origin is
rejected with `403`; an Origin alone is insufficient without the handshake.

`profile_connection(server)` is a single-profile test helper that asserts exactly
one profile exists. Production calls have no implicit selection. Multiple-profile
tests must select from `server.profiles` explicitly.

The origin the helper sends is arbitrary — the server matches the `moz-extension://`
scheme, not a specific UUID, because Firefox assigns a different one to every install.
The check itself is tested in `integration/test_connection_origin.py`.

## Dependency-Held Guarantees

`integration/test_mcp_port_not_web_reachable.py` is unusual: it asserts behavior FoxMCP
does not implement.

The MCP port has no authentication, so anything that can send it a request can call
every tool. Three things keep web pages out — no CORS headers, content-type enforcement
that closes the no-preflight `text/plain` bypass, and a session id the browser cannot
read cross-origin — and **all three belong to `fastmcp`, the MCP SDK and uvicorn**.

A security property held by a dependency is only safe while someone is checking it. The
`fastmcp` floor in `requirements.txt` has already drifted several major versions without
anyone noticing, so an upgrade that starts sending permissive CORS headers is a real
path. The test turns "we checked once" into "we check every run."

**If it fails after a dependency bump, the port is reachable from any page the user
visits.** The fix is a deliberate CORS policy, not a relaxed assertion.

## Rules

- **Test URLs are `example.org`.** Never `httpbin.org` or any other live service —
  tests must not depend on someone else's uptime.
- **`ENABLE_DEBUG_LOGGING_TO_SERVER` goes back to `false`** in `extension/background.js`
  before committing.
- **Run the suite before committing.** All selected tests must pass without
  skips, and the report guard must confirm every required module ran.
- **Open sockets with `connect_as_extension()`**, from `test_config.py` — never
  `websockets.connect()` directly. The server accepts only `moz-extension://` origins,
  so a plain connect is refused with a 403, and the failure reads like a server problem
  rather than a missing header. See [Connecting as the extension](#connecting-as-the-extension).

## Coverage

Run from the repository root using the normal suite and project interpreter:

```bash
FIREFOX_PATH=/path/to/firefox make test
```

The runner selects `unit/` and `integration/` explicitly and produces terminal
coverage details plus an HTML report in `tests/htmlcov/`. Default bare-pytest
discovery also collects standalone drivers and native Windows tests, so it is
not equivalent to the normal suite.

Coverage above 80% is the project target. Inspect the report for the current
checkout and add meaningful coverage for changed behavior.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named pytest` | Installed into the wrong interpreter | `venv/bin/pip install -r tests/requirements.txt` |
| Browser tests are skipped | Firefox unavailable or unusable | Check Developer Edition and `FIREFOX_PATH`; validate the JUnit report |
| `SKIPPED ... Firefox not found` | Firefox not on `PATH` | `FIREFOX_PATH=/path/to/firefox make test` |
| `AttributeError: ... 'get_tools'` | Removed in fastmcp 3.x | Use `list_tools()` / `get_tool()` |
| `AttributeError: ... '_tool_manager'` | Private attribute, gone in 3.x | Use `get_tool()` |
| Extension change has no effect | Stale cached profile | `make clean && make package && rm -rf dist/profile-cache/*` |
| Import errors | Missing symlinks | `make setup-test-imports` |

## Python package smoke test

`ci.yml` builds a wheel and sdist once with `python -m build`; the wheel is built
from the sdist. `scripts/check-python-dist.py` checks the shared extension and runtime server versions,
Python floor, dependencies against `server/requirements.txt`, module/resource
contents, license, entry point, and executable modes of all bundled examples.
Twine validates the metadata and README.

The `python-install` matrix installs both artifacts in fresh environments on
Python 3.10 and 3.14, copies `python_package_smoke.py` outside the checkout, and
runs it there with the installed Python and expected version as its sole argument.
It checks help, invalid options, occupied-port exit codes, all advertised tools over HTTP
and stdio, version announcements, request/response bridging, executable bundled examples, a custom script
directory, and an explicit empty override. A simulated extension answers requests;
this check covers packaging and startup. The Firefox suite and ZIP/XPI smoke test
separately cover browser behavior. The packaged command receives no test fixtures.

Python distributions and `PYTHON-SHA256SUMS` are retained as the
`python-distributions` Actions artifact and reused by release publication; neither
a manual rehearsal nor ordinary CI publishes to PyPI.

### Firefox container coverage

`unit/test_containers.py` verifies opaque-ID validation, request payloads,
registration overrides, missing/mismatched store responses, no replay to older
extensions and older and future protocol-ID rejection.

`integration/test_containers_end_to_end.py` uses isolated Firefox profiles and a
controlled local origin. It checks cookie/localStorage separation in two named
containers and the default store through HTTP MCP, combined filters, lifecycle
and in-use removal errors. Disposable database snapshots also verify that
removal clears a persistent test cookie. Two real shared-stdio clients verify same-store sharing,
different-store separation and persistence after client disconnects and a worker
restart. Complete background JavaScript is also executed with controlled browser
APIs for absent/disabled containers, private-window refusal and post-creation
store mismatch. Those failure simulations do not modify browser preferences.

Final archive smoke tests exercise all advertised tools over HTTP and stdio, using
container tabs for navigation, groups, screenshots, request capture and actual
file upload. Signed AMO upgrade prompts and enterprise policy effects remain a
manual pre-release check; see [development](../docs/development.md#container-permission-upgrade-check).


### Native Windows acceptance checks

`tests/windows/` is collected explicitly by the Windows CI matrix, separately
from the standard `unit/` and Firefox `integration/` suites. It requires native
Windows and Git for Windows. Missing prerequisites fail instead of skipping.
Each Python 3.10/3.14 and PowerShell 5.1/7 combination exercises the current
packaged installation, HTTP helper and direct Python stdio startup, interpreter arguments,
bundled scripts with explicit profile routing and the WMI worker. Run it with
`python -m pytest tests/windows --junitxml=windows.xml`, then validate with
`python scripts/check-test-report.py windows.xml --kind windows`. Set
`FOXMCP_TEST_POWERSHELL` to `powershell` or `pwsh`. Include the repository and
its tests directory in PYTHONPATH, and build/download dist/packages first.


### Script consent coverage

`integration/test_script_consent.py` executes the actual ScriptConsentGate source
in Firefox with controlled browser APIs and a fake clock. It checks sequential
activation/window focus, coalescing, Allow/Deny reuse, origin invalidation,
closure, full-minute expiry, late approval, popup-unload ordering (including
navigation/expiry while closing), Back/Forward prompt re-presentation, bounded
popup retries, delayed native focus and activation recovery, deferred toggle
transitions and restart reset. A real-extension check verifies content scripts cannot change
the consent policy via runtime messages or a storage.sync key.

`extension_settings_checks.js` verifies the toggle through Popup and Options,
approval-only presentation, Allow/Deny closure and expiry without revealing
settings.
`unit/test_predefined_script_logging.py` checks that both raw and predefined
script tools request a 300-second response timeout. Existing proxy route tests
cover the unchanged transport. Native popup positioning
and older-Firefox presentation remain manual UI checks.
