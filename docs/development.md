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

`setup` and `install` use the project virtualenv, `venv/` by default. To select
another environment, pass its bin directory consistently to subsequent commands:

```bash
make setup VENV_BIN=.venv/bin
make test-unit VENV_BIN=.venv/bin
```

The environment is created in the parent of `VENV_BIN`; installs, test runners,
server startup and development tools use that selection. `VENV_PIP` can override
the pip executable separately. `PYTHON` chooses the interpreter used to create
the environment. `clean-all` removes the selected environment and `.venv/`.

### Build

```bash
make build      # copy extension/ to dist/extension/
make package    # build, then create the XPI and server ZIP, then clear the profile cache
```

`package` produces `dist/packages/foxmcp@codemud.org.xpi` and
`dist/packages/foxmcp-server.zip`.

### Python distributions

Hatchling maps the existing `server/` modules to the installed `foxmcp` package
and `predefined-ex/` to executable package examples. No source relocation is
needed. Runtime dependencies in `pyproject.toml` must match
`server/requirements.txt`; the artifact check enforces this.

```bash
venv/bin/python -m pip install build twine
venv/bin/python -m build --outdir dist/python/packages
venv/bin/python -m twine check --strict dist/python/packages/*
venv/bin/python scripts/check-python-dist.py dist/python/packages
```

Use a fresh output directory after changing versions. `build` creates the sdist,
then builds the wheel from it. CI installs each artifact on Python 3.10 and 3.14
and runs [Python package smoke checks](../tests/README.md#python-package-smoke-test)
outside the checkout. Python archives are separate from `make package`'s ZIP/XPI.

### Test

```bash
make test              # everything, with coverage
make test-unit         # unit only — fast, no Firefox
make test-integration  # integration only
make check             # lint + test
```

Allow about fifteen to twenty minutes for a full run. The maintained
[test guide](../tests/README.md#expected-result) records the current collection,
completeness checks, fixtures and troubleshooting.

### Other

```bash
make run-server   # start the WebSocket server
make lint         # flake8 over server/ and tests/
make format       # black + isort
make status       # ports, dependencies, symlink state
make clean        # build artifacts and symlinks
make clean-all    # also removes the selected virtualenv and .venv/
```

`run-server` (also available as `make start`) runs in the foreground. Stop it
with Ctrl+C in that terminal. The Makefile has no `stop` or `restart` target;
manage separately launched services through the launcher that owns them.

`make all`, `make ci`, `make check` and `make quick-test` sequence their stages,
including under parallel make. `make ci` runs clean, setup, lint and test in
order; the test target builds the packages. Local lint reports style issues
without failing, while GitHub CI separately rejects syntax and undefined-name
errors. These local targets do not replace all platform/package CI checks.

## Project Structure

```
foxmcp/
├── docs/            # Documentation
├── extension/       # Firefox extension source
├── server/          # Python server
│   ├── server.py          # Startup composition and compatibility facade
│   ├── browser_server.py  # BrowserServer: listener, registry and routing
│   ├── mcp_frontend.py    # MCPFrontend: MCP transport, tools and local files
│   ├── browser_profile.py # Per-profile sockets, replies and monitor ownership
│   ├── browser_proxy.py   # Shared-port discovery and forwarding
│   ├── profile_names.py   # Read-only Firefox metadata lookup
│   └── mcp_tools.py       # The 46 MCP tool definitions
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

### Icon artwork

`assets/foxmcp-icon-source.png` is the original generated fox artwork. Its
built-in image generation prompt is recorded in `assets/foxmcp-icon-prompt.txt`.
The extension bundles transparent PNGs in `extension/icons/` at 16, 32, 48, 64, 96,
128 and 256 pixels. Manifest `icons` selects extension-manager artwork;
`browser_action.default_icon` selects toolbar artwork. Both use the same mark.
The normal build copies these assets into the XPI automatically.

To regenerate an individual size with ImageMagick:

```bash
magick assets/foxmcp-icon-source.png -resize 32x32 -strip extension/icons/foxmcp-32.png
```

### GitHub repository artwork

The README begins with `assets/demo.gif`, a recorded example of Claude Code
preparing Firefox for a FoxMCP meeting. It shows tab reordering, duplicate
removal, a bookmark folder containing the saved pages, and unrelated tabs
closing. Its absolute GitHub raw URL also works in Python package metadata.
The GIF is 1100 by 760 pixels, runs for 62.4 seconds, and is about 1.1 MB.

Keep the GIF readable at README width and below 5 MB. Hold each full user prompt
for at least 10 seconds and zoom in on browser changes. Name the actor in every
bottom caption: “The user says:” for requests, “The agent ...” for agent actions,
and “The user ...” for the user inspecting the results. Prompts should describe
the task naturally, without naming an MCP server or tool alias. Link the preview
to the full YouTube demo when its published URL is available; retain the
high-quality video outside the repo.

The README displays the existing 128-pixel fox icon. Its absolute GitHub raw URL
also works when the README is displayed outside a source checkout, such as in
Python package metadata.

`assets/foxmcp-social-preview.png` is the repository sharing card, sized
1280 by 640 pixels and kept below GitHub's 1 MB limit. Its image-generation
prompt is in `assets/foxmcp-social-preview-prompt.txt`. Upload this image through
repository **Settings > General > Social preview > Edit > Upload an image**.
Committing the PNG alone does not change GitHub's configured social preview.

### Loading in Firefox

Build the extension with `make package` first. If you used the release installer,
the downloaded XPI is already at `dist/packages/foxmcp@codemud.org.xpi`.

**Firefox Release and Beta enforce signing.** They ignore
`xpinstall.signatures.required=false`. Use the signed extension from
[Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/foxmcp/) for
permanent installation, or load the unsigned build temporarily. Persistent
unsigned installation requires Developer Edition, Nightly, or an unbranded build.

| Method for an unsigned XPI | Survives restart | Firefox channels |
|---|---|---|
| Temporary add-on | No | All |
| Install from file with signing disabled | Yes | Developer Edition, Nightly, unbranded |
| `scripts/install-xpi.sh` | Yes, after manual enablement | Developer Edition, Nightly, unbranded |

**Temporary add-on:** Open `about:debugging` → **This Firefox** →
**Load Temporary Add-on**, and select `dist/packages/foxmcp@codemud.org.xpi`.
Repeat after Firefox restarts. If the signed release is already installed,
the temporary build with the same add-on ID takes its place for the session;
restarting Firefox restores the installed release. Reload existing page tabs
before testing content-script changes. Temporary loading does not verify the
permission prompts shown during a signed extension upgrade.

Keep licensing declarations in `LICENSE` and package metadata. `license` is not
a supported WebExtension manifest key and produces a Firefox loading warning.

**Install from file:** On a channel that permits unsigned extensions, open
`about:config` and set `xpinstall.signatures.required` to `false`. Then open
`about:addons` → gear icon → **Install Add-on From File** and select the XPI.

**Script:** On a channel that permits unsigned extensions, find the profile
directory in `about:profiles`, close Firefox completely, then run:

```bash
./scripts/install-xpi.sh /path/to/firefox/profile
```

The script installs the XPI, changes the signing preference in `user.js`, and
fixes permissions. Start Firefox, open `about:addons`, and **enable FoxMCP by
hand**. Firefox initially disables extensions installed directly into a profile.
Installing through the browser with either method above does not need that step.

### Layout

```
extension/
├── manifest.json   # Extension configuration (Manifest V2)
├── background.js   # Profile handshake, browser actions and settings persistence
├── config.js       # Shared defaults, validation and effective endpoints
├── settings.js     # Shared controller for Popup/Options
├── settings.css    # Shared light/dark styling
├── options.html/.js/.css # Full-page settings and DOM adapter
├── content.js      # Page text/HTML readers and file handles
└── popup/          # Toolbar popup layout and DOM adapter
```

The persistent background owns settings validation and writes. Both views use
`settings.js` and send runtime messages, so pending saves survive popup closure.
Keep profile registration, socket identity guards and protocol errors intact when
editing reconnection behavior. See the [file map](files.md#extension-directory).

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
@self._tool()
async def tabs_list(profile_id: int) -> str:
    """List all open browser tabs"""
    request = {
        "id": str(uuid.uuid4()),
        "type": "request",
        "action": "tabs.list",
        "data": {},
        "timestamp": datetime.now().isoformat()
    }

    response = await self._send(profile_id, request)

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

The server takes `--host`, `--port`, `--mcp-port`, `--no-mcp`, `--stdio`,
`--disable-tools` and `--enable-tools`:

```bash
cd server && python server.py --port 8767
```

Under `--stdio` the server's stdout carries the MCP protocol, so its logging —
and anything else with something to say — goes to stderr, where the client
collects it; most keep a log per MCP server. Nothing in `server/` may call
`print()`, and `tests/unit/test_stdio_mode.py` fails if something does.

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

## Continuous Integration

`.github/workflows/ci.yml` runs on every push to master and every pull request:
lint, unit tests, the full suite against a real Firefox, an install from source,
and a smoke test of the final release archives. Unit and installation jobs run
on Python 3.10 and 3.14. The release workflow calls this same CI workflow, so
these checks also gate tag releases and manual rehearsals.

The install job is the one that follows README rather than the test harness. It
runs `make install` on a clean checkout — which nothing else does, since the other
jobs create the venv themselves — then starts the server and asks it for its tools
over HTTP as a real MCP client would. It checks discovery with every group enabled
and with two groups disabled, stdio startup, and that an individually enabled tool
survives its disabled group. These behavior checks run on every PR and push.

Fixed tool totals and complete advertised-tool coverage in the archive smoke test
are release gates. Reusable CI accepts boolean `release-checks` (default false);
`release.yml` sets it to true for both manual rehearsals and tagged releases.
Every CI job receives `FOXMCP_RELEASE_CHECKS=0` for ordinary runs or `1` for
release runs. Local checks remain strict unless explicitly run with
`FOXMCP_RELEASE_CHECKS=0`. Only the catalog gates are relaxed: functional tests,
nonempty discovery, filtering and the no-skipped-tests guard remain required.
Archive reports list uncovered tools during ordinary CI; release runs fail until
all advertised tools have smoke scenarios and all expected counts are updated.

Before release, update affected totals in the install workflow, Windows installer,
Python-package, shared-stdio container and archive smoke checks. For example,
with 47 tools and 10 in the tabs group, enabling only its screenshot exposes 38.
To check the default HTTP tool count by hand:

```bash
venv/bin/python server/server.py --port 18765 --mcp-port 13000 &
venv/bin/python -c "
import asyncio
from fastmcp import Client
async def main():
    async with Client('http://localhost:13000/mcp/') as c:
        print(len(await c.list_tools()))
asyncio.run(main())"
```

The suite job installs Firefox Developer Edition rather than release. The tests
drop an unsigned XPI into the profile, which needs
`xpinstall.signatures.required=false` to be honoured, and only Nightly,
Developer Edition and unbranded builds honour it — release and beta enforce
signing regardless, so the extension never loads and every browser test fails.
Pass `channel: nightly` to `.github/actions/setup-firefox` to test against
tomorrow's Firefox.

The settings regression harness executes 234 assertions against the actual
scripts, with controlled storage, sockets, timers and UI. Its Firefox test also
uses browser DOM. Multiple-profile coverage is split between two real Firefox profiles called
through registered tool functions, and simulated profiles reached by actual
HTTP/shared-stdio clients. The latter checks native-ID collisions and transport
isolation. No single test combines two real Firefox profiles with both MCP
transports. See the [coverage matrix](../tests/README.md#multiple-profile-coverage).
The 2026-10-31 server-composition refactor passed all 727 tests without skips
(517 unit, 210 integration), plus the module/no-skip guard. Final packaged HTTP
and stdio each passed all 46 tools, including exact upload bytes and events.
Wheel/sdist installation checks passed on Python 3.10 and 3.14. Native Windows
validation for the refactor remains pending in CI. The prior released tree's
successful Windows results do not validate these new source changes.

Source-installation smoke checks run separately from pytest on Python 3.10 and
3.14. Keep their embedded tool arguments in `.github/workflows/ci.yml` aligned
with the current schema. In particular, a missing-profile routing check must
supply a positive integer `profile_id`; a legacy string placeholder only tests
schema rejection. See [source-installation checks](../tests/README.md#source-installation-smoke-checks).

The shared `scripts/check-test-report.py` guard requires successful test cases
from every unit and integration module on disk. It detects missing integration
collection even if all unit tests pass, and handles multiple JUnit suites.
The job also fails if any test was *skipped*. Everything that touches the
browser skips rather than fails when Firefox is unusable, so without that guard
a broken runner would produce a green build of a suite that never opened a
browser.

### Test against the Firefox CI uses, not the one you have

`test_response_body_capture_verification` passed on the maintainer's Nightly for
months while failing on CI, because the two builds disagreed about
`details.responseSize` on `onCompleted`: Nightly reported the transferred bytes,
Developer Edition reported `0`. The test read that value, so it passed on one
machine and failed on the other with no code difference at all.

Set `FIREFOX_PATH` to a Developer Edition build before concluding that a browser
test is fine.

## Release Process

Complete the [protocol ID compatibility review](protocol.md#protocol-id-compatibility-policy)
before every release. Compare the extension/server API with the previous released
tag, identify every modified or removed existing API, and confirm that the
protocol ID has increased when required. Record the baseline tag, affected APIs,
previous/current IDs and rationale in the release preparation record. Explicitly
record an unchanged-ID decision too. This is a required manual check before
tagging or publishing; `scripts/check-version.sh` checks release-version
consistency, not API compatibility.

1. Complete and record the protocol ID compatibility review described above.
2. Reconcile the tool catalog as part of release preparation. Discover the
   candidate's actual tools and update every fixed expected total, including
   disabled-group and individually enabled-tool variants. Update the source
   install workflow, Windows installer tests, wheel/sdist smoke check,
   shared-stdio container test and final-archive smoke check as needed. Add or
   update meaningful tests for new or changed tools and an archive smoke
   scenario for every advertised tool over both HTTP and stdio. Do this work
   before the release rehearsal; do not bypass the catalog gates to release.
3. Bump the version in `extension/manifest.json`, `package.json`, `pyproject.toml`, `server/version.py`,
   `scripts/install-from-github.sh`, `scripts/install-from-github.ps1`, both
   the top-level and package versions in `server.json`, and the install URLs
   in `README.md`
4. Rename `## [Unreleased]` in `CHANGELOG.md` to `## [1.7.0] - <date>` and add
   the link reference at the bottom
5. `scripts/check-version.sh 1.7.0` fails unless all nine files agree
   and the README `mcp-name` marker matches the registry server name.
6. Commit the prepared candidate and run a non-publishing release rehearsal
   on that exact commit. Its `release-checks: true` enables fixed tool totals
   and complete advertised-tool coverage. Resolve failures and rehearse the
   updated commit again before proceeding. Record the validated catalog totals
   and test results in the release preparation record.
7. After every rehearsal gate passes, tag that exact validated commit:
   `git tag -a v1.7.0 -m "..."`, then push the tag.

Pushing the tag is the whole release. `.github/workflows/release.yml` re-checks
the version and runs all CI checks. The package job builds the archives once,
records SHA-256 checksums, and tests the real installer in an empty directory.
The installed server and final XPI must exercise every advertised tool through
both HTTP and stdio MCP: windows, tabs/groups, navigation/content, screenshots,
history, bookmarks, request capture, connection diagnostics and file uploads.
Checks read back state and verify captured bodies and uploaded bytes. Each
transport saves a tool-call report, completed feature checks and a screenshot;
logs and upload receipts are also retained as Actions artifacts. See [Package smoke test](../tests/README.md#release-package-smoke-test).

Only those tested archives are attested and published to the GitHub release.
CI also builds and tests a Python wheel and sdist once. The release reuses those
exact files, verifies `PYTHON-SHA256SUMS`, and includes them in GitHub provenance
and release assets. A separate tag-only job publishes them to PyPI with OIDC
Trusted Publishing and PyPI attestations. Manual rehearsals publish neither
to PyPI nor GitHub. The tag-only `mcp-registry` job runs after PyPI succeeds
and publishes the matching `server.json` through GitHub OIDC. Registry metadata
is validated in `verify` on both tags and manual rehearsals.
The AMO job unpacks the tested XPI for submission rather than rebuilding it.
Release notes come from the changelog section. No publication happens if lint,
installation, minimum-Python checks, the full suite or package smoke testing fails.

The package check covers every advertised tool with representative workflows;
the full suite covers additional cases and invalid inputs. Credentialed agent
trials remain manual. Testing the signed extension on standard Firefox remains
a separate post-signing check; the release gate uses Developer Edition to load
the unsigned XPI.

The AMO step runs in the `amo` deployment environment, which holds the API
credentials and requires a human to approve the deployment. Nothing else in
either workflow can reach those secrets.

To rehearse without releasing anything, run the workflow by hand from the
Actions tab and give it a version. It verifies and builds; it publishes nothing
and never touches AMO or authenticates to the MCP Registry.

There is no release script to run. `release-commands.sh` used to sit in the
repository root and was deleted in 1.2.0; if you find a copy, it is not the
release path and running it would commit your working tree under a v1.1.0
message.

### First PyPI publication

Before the first PyPI publication, create the GitHub `pypi` environment and
configure its release-tag deployment policy. In the owning PyPI account, create
[a pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
with these exact values:

| Field | Value |
|---|---|
| Project name | `foxmcp` |
| GitHub owner | `ThinkerYzu` |
| Repository | `foxmcp` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

No PyPI token belongs in GitHub secrets. Publication uses
[`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)
in the release workflow, after all reusable CI checks and GitHub publication.
The PyPI name returned 404 on 2026-10-21; PyPI can still reject a reserved name.

The GitHub release and AMO submission are separate from the PyPI job. If first
publication fails on publisher configuration, keep the verified GitHub release,
complete the owning account setup and rerun the failed publishing job. Confirm
PyPI actually serves the version before recommending `uvx foxmcp`.

Bump `pyproject.toml` with the extension and other version-bearing files before
the next release. Rehearse first, then publish through a new version tag. After
publication, verify `uvx --from foxmcp==VERSION foxmcp --help` from an empty
directory and promote the README's uvx setup into Quick start. Do not describe
the package as published until PyPI serves that tested version.

### MCP Registry publication

[`server.json`](../server.json) describes the PyPI package and the command
`uvx foxmcp==VERSION --stdio`. Firefox still needs the extension installed
separately, as described in [Quick Start](../README.md#quick-start).
The README ownership marker must exactly match `server.json`'s `name`:
`io.github.ThinkerYzu/foxmcp`. The registry checks the README served by PyPI,
so the first publication requires a new PyPI release containing that marker.
Already-published 1.6.0 cannot be replaced or registered with this preparation.

Before the first registry publication, create the GitHub `mcp-registry`
deployment environment with a required maintainer reviewer and a `v*` tag-only
deployment policy. Allow the maintainer to approve their own releases, as for
`amo`. The workflow uses `id-token: write` and `mcp-publisher login github-oidc`;
GitHub OIDC grants the repository owner's `io.github.ThinkerYzu/*` namespace.
No registry secret or interactive device login is required. See the official
[GitHub Actions publishing guide](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/github-actions.mdx).

Both validation and publication install the Linux x86-64 publisher pinned in
[`scripts/install-mcp-publisher.sh`](../scripts/install-mcp-publisher.sh).
When upgrading it, deliberately update both its release tag and SHA-256 from
the upstream release. Rehearse the release workflow from the intended branch
with its current version before tagging: registry validation must pass while
all publishing jobs remain skipped. This does not test OIDC authentication or
remote PyPI ownership checks, which occur only during an approved publication.

After PyPI succeeds, approve the `mcp-registry` deployment. If registry
publication fails, retain the successful package releases, correct the registry
configuration and rerun the failed job. Verify the exact name/version on the
[official registry](https://registry.modelcontextprotocol.io/) before reporting
it as listed. Updating the awesome-mcp-servers list is a separate one-time PR.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Import errors in tests | `make setup-test-imports` |
| `No module named pytest` | `venv/bin/pip install -r tests/requirements.txt` |
| Firefox not found | Set `FIREFOX_PATH`; tests otherwise search `PATH` |
| Extension edit has no effect | `make clean && make package && rm -rf dist/profile-cache/*` |
| Extension not loading | Check `about:debugging` for errors |
| Port conflict | Pass `--port` / `--mcp-port` |

### Port conflicts

If the MCP HTTP port is occupied, v1.4.0 logs an `address already in use` error
but leaves its WebSocket server running. A connected Firefox extension or a
426 response from the WebSocket port does not prove that the MCP endpoint is
working. Check the startup log and both ports; an HTTP response on the occupied
port may come from the other service.

Stop the FoxMCP process you just started, choose unused ports, and start it
manually. For a release installation, preserve the example-script directory:

```bash
# From the installation directory, instead of ./start-foxmcp.sh
export FOXMCP_EXT_SCRIPTS="$PWD/predefined-scripts"
venv/bin/python server/server.py --port 9000 --mcp-port 4000
```

Set the extension's WebSocket port to **9000** and the MCP client's URL to
`http://localhost:4000/mcp/`. Check the new WebSocket port for a 426 response and
the new MCP URL for a 307 redirect; then connect an MCP client and list tools.
The generated `start-foxmcp.sh` uses the default ports, so use the manual command
for this setup.

### README installation verification

On 2026-10-18, the documented unattended installation was run in an empty
directory using the published v1.4.0 installer and release assets from GitHub.
Dependency installation succeeded. Manual startup with the documented custom
ports accepted an MCP client, advertised all 41 tools, included
`set-file-input.py` in the predefined-script description, and returned the
expected WebSocket HTTP 426 response.

The default startup script was also tried, exposing the occupied-MCP-port
behavior described above. This check did not repeat the interactive installer
prompts, manual Firefox Add-ons installation, Claude Code registration, or the
natural-language examples through an AI assistant. The release package smoke
tests separately exercise all 46 tools over HTTP and stdio with an unsigned XPI
in Firefox Developer Edition; they do not verify the signed Add-ons installation.

## Security Notes

The server binds to localhost only and is never exposed to a network. Predefined
scripts pass through a path validation chain before execution — see
[`scripts.md`](scripts.md). Error messages should not leak internal paths or state.

### Container permission upgrade check

When AMO provides the signed container-support artifact, rehearse upgrading
from signed v1.4.0 in a separate standard-Firefox profile. Record the actual
permission prompt and enterprise-policy effects of adding required
`contextualIdentities` and `cookies`. The release workflow submits to AMO after
GitHub publication, so this is a post-signing check, as described in the general
release procedure. Do not mark it complete from temporary-loading tests.
Automated tests install an unsigned XPI in Developer Edition; they do not verify
the signed AMO update flow. Container APIs may enable the feature during
installation. Respect later user disabling.

The v1.5.0 [release compatibility review](../RELEASES.md#protocol-compatibility-review)
uses released v1.4.0 as its baseline. That tag predates checked forwarding IDs;
unreleased forwarding introduced ID 1 and the candidate retains the required
increase to ID 2. The review covers tab-list metadata/filtering, disconnect
handling and listener validation. New container lifecycle actions alone do not
require another bump. Recheck if the release diff changes before tagging.


### Windows acceptance CI

CI installs the same archives built by the Linux unit job on Windows, using
Python 3.10/3.14 and Windows PowerShell 5.1/PowerShell 7. Each job runs
`tests/windows` and requires all its modules without failures or skips via
`scripts/check-test-report.py windows.xml --kind windows`. The standard Linux
unit and browser suites retain their existing no-skip guards. Package validation
waits for the Windows matrix too.

The Windows suite serves the current archives and examples from loopback,
installs into an empty path containing spaces, launches the generated wrapper
from a different directory and verifies HTTP discovery. Stdio discovery uses
the installed Python interpreter directly; the PowerShell HTTP helper rejects
`--stdio` promptly with the supported command. It also
checks Python/Git Bash argument preservation, bundled-script routing and WMI
worker startup. Firefox helper installation uses a disposable directory; these
checks do not establish signed installation behavior in a real Firefox browser.
Reports and installation/startup logs are retained as workflow artifacts.

Both PowerShell installers ship as release assets. Keep their helper acquisition
instructions aligned with the release download URLs when publishing a version.

## Native script consent check

Use matching protocol-3 server and extension test builds in a disposable Firefox
profile. Enable **Ask before agents run scripts in a tab**. Send raw/predefined
script attempts to several background tabs, including one in another window.
Confirm that each prompt activates its target and focuses that window, with no
later request interrupting the current prompt. Check Allow and Deny, then leave
a prompt unanswered for 60 seconds and confirm rejection without execution.
A fresh attempt after timeout should ask again. After Allow, confirm that the
popup disappears and focus returns to the page before the script runs. Also
confirm that the approval popup hides connection/configuration controls, and
Deny closes it without running the script. Check Deny followed by a queued
target: the old popup must close before the next prompt opens. Popup-opening
failures are logged in the extension console. While a request
is pending, use Back and Forward between pages on the same origin and confirm
that the popup reappears after navigation without renewing the deadline. An
origin change must reject the old pending request instead. Also check delayed
focus in another Firefox window: pending approval must resume when that window
actually gains focus, without another navigation or a renewed deadline. Read-only
`test.get_popup_state` with `includeConsentDiagnostics: true` reports the loaded
implementation and pending visibility/error state; see
[protocol diagnostics](protocol.md#get-popup-display-state).

Inspect the native toolbar popup on Firefox Desktop 149+ and test the **!**
badge/manual toolbar-click path on older Firefox. Closing/reopening must retain
the original deadline. Switching away must disable approval until the target is
visible again. Check the tab title, origin, countdown, keyboard focus and both
buttons. Automated controlled-API checks do not replace this visual check.

Also check same-origin reload versus origin change, independent tabs on the same
origin, and a toggle change while several approvals are pending. New arrivals
must wait for that transition. Restart Firefox to verify that the toggle persists
but tab decisions are forgotten. See [configuration](configuration.md#script-injection-consent)
and [test coverage](../tests/README.md#script-consent-coverage).
