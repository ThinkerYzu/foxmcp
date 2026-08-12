# Development Guide

Setup, workflow, and maintenance for FoxMCP development.

## Quick Cycle

1. `make setup` — install dependencies and create the test import symlinks
2. `make package` — build the extension XPI
3. Load the extension in Firefox (see [Loading in Firefox](#loading-in-firefox))
4. `make run-server` — start the server
5. `make test` — run the suite

## Commands

### Setup

```bash
make setup              # server + test dependencies, plus test import symlinks
make install            # server dependencies only
make setup-test-imports # recreate the test import symlinks
make dev                # setup, then upgrade pip
```

`setup` and `install` install into `venv/` explicitly, through `$(VENV_PIP)`. A bare
`pip` targets whatever interpreter happens to be active, which is how the venv once
ended up with the server dependencies but no pytest.

### Build

```bash
make build      # copy extension/ to dist/extension/
make package    # build, then create the XPI and server ZIP, then clear the profile cache
```

`package` produces `dist/packages/foxmcp@codemud.org.xpi` and
`dist/packages/foxmcp-server.zip`.

### Test

```bash
make test              # everything, with coverage
make test-unit         # unit only — fast, no Firefox
make test-integration  # integration only
make check             # lint + test
```

Expect **202 passing** in about ten minutes. See [`../tests/README.md`](../tests/README.md)
for the suite layout, fixtures, and troubleshooting.

### Other

```bash
make run-server   # start the WebSocket server
make lint         # flake8 over server/ and tests/
make format       # black + isort
make status       # ports, dependencies, symlink state
make clean        # build artifacts and symlinks
make clean-all    # also removes venv/
```

## Project Structure

```
foxmcp/
├── docs/            # Documentation
├── extension/       # Firefox extension source
├── server/          # Python server
│   ├── server.py    # WebSocket server, request correlation, CLI
│   └── mcp_tools.py # The 35 MCP tool definitions
├── tests/           # Test suite (unit/, integration/, fixtures/)
├── scripts/         # install-xpi.sh, install-from-github.sh
├── venv/            # Python virtual environment
└── Makefile         # Build system
```

## Test Import System

Test files never manipulate `sys.path`. Importing `test_imports` first sets it up:

```python
import test_imports  # always the first import
from server.server import FoxMCPServer
from test_config import TEST_PORTS
```

`tests/test_imports.py` is the tracked file. The copies in `tests/unit/` and
`tests/integration/` are symlinks to it, created by `make setup-test-imports` (which
every `make test*` target runs first) and removed by `make clean`. They are not
tracked by git.

## Extension Development

### Loading in Firefox

| Method | Survives restart | Best for |
|---|---|---|
| Temporary add-on | no | quick testing |
| `about:addons` install | yes | manual setup |
| `scripts/install-xpi.sh` | yes | development |

**Temporary add-on** — go to `about:debugging` → "This Firefox" → "Load Temporary
Add-on" → pick `dist/packages/foxmcp@codemud.org.xpi`.

**`about:addons`** — set `xpinstall.signatures.required` to `false` in `about:config`
first, then use the gear icon → "Install Add-on From File". Unsigned extensions cannot
be installed without that preference change.

**Script** — close Firefox completely, find your profile directory in `about:profiles`,
then:

```bash
./scripts/install-xpi.sh /path/to/firefox/profile
```

The script installs the XPI, sets `xpinstall.signatures.required = false` in `user.js`,
and fixes permissions.

### Layout

```
extension/
├── manifest.json   # Extension configuration (Manifest V2)
├── background.js   # WebSocket client and action dispatch
├── content.js      # Content script injection
└── popup/          # Popup UI (html, js, css)
```

## Adding a Browser Function

Actions are namespaced with a dot — `tabs.list`, `windows.create`. The extension
dispatches on the part before the dot, then on the whole string.

**1. Handle it in the extension** (`extension/background.js`). Add a `case` to the
handler for its namespace:

```javascript
async function handleTabsAction(id, action, data) {
  try {
    switch (action) {
      case 'tabs.list':
        const tabs = await browser.tabs.query({ currentWindow: true });
        sendResponse(id, action, { tabs: tabs.map(/* ... */) });
        break;
```

A new namespace also needs a `case` in the top-level `switch (action.split('.')[0])`
and its own `handle<Name>Action` function.

**2. Expose it as an MCP tool** (`server/mcp_tools.py`). Tools are registered inside
the `_setup_*_tools` methods. The tool builds the request, waits for the reply, and
formats it for the caller:

```python
@self.mcp.tool()
async def tabs_list() -> str:
    """List all open browser tabs"""
    request = {
        "id": str(uuid.uuid4()),
        "type": "request",
        "action": "tabs.list",
        "data": {},
        "timestamp": datetime.now().isoformat()
    }

    response = await self.websocket_server.send_request_and_wait(request)

    if "error" in response:
        return f"Error getting tabs: {response['error']}"
    ...
```

The docstring becomes the tool description that MCP clients see, so write it for them.

**3. Add a test** in `tests/integration/`, using the `server_with_extension` fixture.

**4. Rebuild before testing.** Test profiles are cached, so an extension edit has no
effect until you clear the cache:

```bash
make clean && make package && rm -rf dist/profile-cache/*
```

## Debugging

### Server

The server takes `--host`, `--port`, `--mcp-port`, and `--no-mcp`:

```bash
cd server && python server.py --port 8767
```

### Extension

Extension logs are prefixed `[FoxMCP]`. Read them in the background script console at
`about:debugging` → "This Firefox" → "Inspect".

To forward extension logs to the server, set `ENABLE_DEBUG_LOGGING_TO_SERVER = true`
near the top of `extension/background.js`, then rebuild and clear the profile cache.
**Set it back to `false` before committing.**

### Tests

```bash
cd tests && pytest -v -s                                    # verbose, unbuffered
cd tests && pytest integration/test_window_management.py -v  # one file
cd tests && pytest unit/test_server.py::test_name -v --pdb   # drop into the debugger
```

## Code Style

```bash
make format   # black + isort over server/ and tests/
make lint     # flake8, max line length 100
```

There is no JavaScript linting or formatting configured.

## Release Process

1. Update the version in `extension/manifest.json` and `package.json`
2. Update the version in `scripts/install-from-github.sh` and `release-commands.sh`
3. Update the installation URL in `README.md`
4. Add release notes to `CHANGELOG.md` and `RELEASES.md`
5. `make package`
6. Tag: `git tag -a v1.2.0 -m "..."` and push the tag

`release-commands.sh` scripts steps 5 and 6. There is no CI — the suite runs locally.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Import errors in tests | `make setup-test-imports` |
| `No module named pytest` | `venv/bin/pip install -r tests/requirements.txt` |
| Firefox not found | Set `FIREFOX_PATH`; tests otherwise search `PATH` |
| Extension edit has no effect | `make clean && make package && rm -rf dist/profile-cache/*` |
| Extension not loading | Check `about:debugging` for errors |
| Port conflict | Pass `--port` / `--mcp-port` |

## Security Notes

The server binds to localhost only and is never exposed to a network. Predefined
scripts pass through a path validation chain before execution — see
[`scripts.md`](scripts.md). Error messages should not leak internal paths or state.
