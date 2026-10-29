# FoxMCP Project Structure

This map identifies the source files responsible for each part of FoxMCP.
See [architecture](architecture.md) for data flow and
[development](development.md) for setup, builds and tests.

## Project Overview

```text
foxmcp/
├── extension/                 # Firefox extension
│   ├── manifest.json          # Permissions, background scripts and UI entry points
│   ├── background.js          # Profile handshake, browser actions and settings persistence
│   ├── config.js              # Shared configuration defaults and validation
│   ├── settings.js            # Shared Popup/Options controller
│   ├── settings.css           # Shared light/dark theme
│   ├── content.js             # Content-script execution and document-local file handles
│   ├── options.html/.js/.css  # Full-page settings layout and DOM adapter
│   ├── popup/                 # Toolbar popup HTML, DOM adapter and CSS
│   └── icons/                 # Packaged extension icons
├── server/                    # Source package, installed as foxmcp
│   ├── server.py              # Browser registry, explicit routing and MCP startup
│   ├── browser_profile.py     # One browser connection, replies and monitor ownership
│   ├── browser_proxy.py       # Shared-port discovery and client forwarding
│   ├── profile_names.py       # Read-only Firefox profile-name lookup
│   ├── mcp_tools.py           # MCP tool definitions and browser request construction
│   ├── file_transfer.py       # Temporary HTTP grants for local files
│   ├── single_instance.py     # Shared-worker discovery, startup and lifetime
│   ├── cli.py                 # Installed foxmcp command
│   ├── version.py             # Runtime release version
│   └── requirements.txt       # Server dependencies
├── predefined-ex/             # Executable example scripts packaged for users
├── tests/                     # Unit/integration tests, helpers and package checks
├── scripts/                   # Installers and release validation helpers
├── docs/                      # Product reference documentation
├── assets/                    # README demo and repository artwork
├── pyproject.toml             # Python packaging and console entry point
├── Makefile                   # Setup, build, test and archive targets
├── CHANGELOG.md               # Changes by release, including Unreleased
├── RELEASES.md                # User-facing release notes
├── CONTRIBUTING.md            # Contribution and compatibility rules
└── CLAUDE.md                  # Source-checkout house rules
```

## Extension Directory

| File | Responsibility |
|---|---|
| [manifest.json](../extension/manifest.json) | Registers `config.js` before the persistent `background.js`, the content script, Popup/Options entry points and permissions. |
| [background.js](../extension/background.js) | Owns the socket, protocol/profile handshake, browser action routing, monitor cleanup and settings read/write queue. Reports Connected only after profile registration. |
| [config.js](../extension/config.js) | Supplies defaults, validates Host/Port and integer intervals, applies test overrides and constructs `ws://` endpoints. |
| [settings.js](../extension/settings.js) | Binds inputs in both views, sends edits/reset requests to the background, polls status and preserves unfinished edits. Formats connection and release/protocol diagnostics. |
| [settings.css](../extension/settings.css) | Shared controls, error feedback and system light/dark theme. |
| [popup/popup.js](../extension/popup/popup.js) | Connects the shared controller to the toolbar popup's status elements. |
| [options.js](../extension/options.js) | Connects the same controller to the full-page settings elements. |
| [content.js](../extension/content.js) | Executes scripts and manages received File handles in the target document's isolated scope. |

Popup and Options send runtime messages to the background; they do not read or
write `storage.sync` themselves. The background validates and debounces valid
edits for 500ms, serializes persistence, then applies the effective configuration.
See [extension configuration](configuration.md#configuring-extension).

Both views offer Host, Port, Reconnect Interval and Reset to defaults. There are
no Save, manual Reconnect, Max Retry Attempts or Ping Timeout controls. Reset
persists immediately through the queue without a confirmation dialog. Endpoint
changes replace the connection; interval-only changes preserve a healthy socket.
See [reconnection](configuration.md#tuning).

## Server Directory

| File | Responsibility |
|---|---|
| [server.py](../server/server.py) | Keeps `profiles`, validates registrations and routes requests using an explicit `profile_id`. Starts HTTP/stdio MCP, browser and local-file services. |
| [browser_profile.py](../server/browser_profile.py) | Owns one profile socket, pending reply futures, connection identity, version diagnostics and monitor ownership. A disconnect affects only that connection. |
| [browser_proxy.py](../server/browser_proxy.py) | Implements `/discovery` and `/proxy`, validates local clients and forwards browser commands while preserving the target profile. |
| [profile_names.py](../server/profile_names.py) | Resolves names from Firefox's local metadata without modifying it. Reports unavailable or ambiguous names. |
| [mcp_tools.py](../server/mcp_tools.py) | Registers 46 tools by default. `profiles_list` discovers targets; browser tools require `profile_id`. Runs predefined scripts locally before sending generated JavaScript. |
| [single_instance.py](../server/single_instance.py) | Joins or starts the shared worker for `--stdio --single-instance`. |
| [file_transfer.py](../server/file_transfer.py) | Streams regular local files through one-use HTTP grants; does not encode file contents into the WebSocket request. |
| [cli.py](../server/cli.py), [version.py](../server/version.py) | Installed command setup and release-version reporting. |

See [profile discovery](api-reference.md#firefox-profiles),
[protocol 4](protocol.md#profile-connections-protocol-id-4) and
[shared stdio](architecture.md#shared-stdio-server) for the contracts.
Dependencies are declared in [server/requirements.txt](../server/requirements.txt)
and [pyproject.toml](../pyproject.toml).

## Tests and Build Outputs

- `tests/unit/` covers routing, validation, profile-name lookup, tool schemas and
  server components. `tests/integration/` uses real sockets and disposable Firefox
  profiles, including multiple profiles and the actual settings scripts/HTML.
  The [multiple-profile matrix](../tests/README.md#multiple-profile-coverage)
  distinguishes direct tool calls with real browsers from actual MCP transports
  with simulated browser responders.
- `tests/extension_settings_checks.js` exercises settings and handshake behavior
  with controlled sockets, storage, timers and UI. The Firefox integration test
  executes it with browser DOM support.
- `tests/package_smoke.py` installs final ZIP/XPI artifacts and exercises every
  tool over HTTP and stdio. `tests/python_package_smoke.py` checks an installed
  wheel/sdist. See [test guide](../tests/README.md).
- `scripts/install-from-github.sh` and `scripts/install-xpi.sh` implement archive
  installation; other scripts check versions, distributions and JUnit reports.
- `dist/extension/`, `dist/server-package/` and `dist/packages/` are generated by
  `make package`; the final directory contains the XPI, server ZIP and checksums.
  Cached test profiles and coverage output are generated, not product sources.

## Documentation

[README](../README.md) gives installation and usage guidance.
[docs/README.md](README.md) indexes the API, protocol, configuration and development
references. Project decisions, pending work and session history live separately
in the workbench at `~/progm/claudebugzilla/proj_docs/foxmcp/`.
