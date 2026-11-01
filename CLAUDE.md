This project is to create an extension to expose data and function to MCP client.

It will create an extension and a MCP server that talk to the extension.
The MCP server will be implemented in Python with FastMCP.
It is Websocket between the extension and the MCP server.

# Agent Entry Point

This file is the shared entry point for coding agents working in this repository.
Before making changes:

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow, coding
   standards, testing requirements and commit-message format.
2. Read [architecture.md](docs/architecture.md), especially the
   [system diagram and source-symbol map](docs/architecture.md#system-overview),
   and the [component responsibilities](docs/files.md). Follow the existing
   design for every change.
3. For maintainer work in this workspace, read the project workbench at
   `~/progm/claudebugzilla/proj_docs/foxmcp/`: start with `AGENT-warm-up.md` and
   `HANDOFF.md`, then check `SPEC.md`, `DESIGN.md` and `IMPLEMENTATION-GUIDE.md`
   for the task's requirements and plan. If the workbench is unavailable, use
   the repository references and agreed issue/PR requirements; disclose any
   missing context that prevents completing the task.

Explicitly describe architecture violations or proposed design changes in the
PR description and/or relevant commit-message body. Changes without a PR must
include that explanation in the commit-message body. Follow the
[architecture-review requirements](CONTRIBUTING.md#architecture-review),
including design discussion and diagram updates before merge.

Before finishing, review the diff, run checks appropriate to the change, and
report what changed, validation performed and any remaining limitations.

# Repository Paths

## FM_ROOT Environment Variable

`claude.sh` sets `FM_ROOT` to the checkout root. Other launch methods may leave
it unset. If it is unset, initialize it from inside the intended FoxMCP checkout:

```bash
export FM_ROOT="$(git rev-parse --show-toplevel)"
```

Ensure each shell or tool command inherits this variable, or initialize it again.
Always use `"$FM_ROOT"` in shell commands referring to repository paths and quote
paths to support checkout directories containing spaces.

```bash
# Read project files
cat "$FM_ROOT/README.md"

# Run the existing unit-test target without Firefox
make -C "$FM_ROOT" test-unit

# Find project files
rg --files "$FM_ROOT/server"
```

See [CONTRIBUTING.md](CONTRIBUTING.md#development-setup) for initial setup and
[the test guide](tests/README.md) for Firefox and full-suite checks.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
NEVER create git commits unless explicitly requested by the User.
When creating future commits, wrap every commit-message line (subject and body)
at 80 characters maximum. Keep subjects at 50 characters or less as
CONTRIBUTING.md specifies. Separate the subject and body with a blank line.
Apply these rules to merge and squash messages too, and check line lengths
before committing.
NEVER add Claude Code attribution or "Generated with Claude Code" footer in git commit messages.

# PR Review Architecture Rules

Every PR review must check the diff against `docs/architecture.md#system-overview`,
its source-symbol map and `docs/files.md`. Follow
[Architecture Review](CONTRIBUTING.md#architecture-review). Explicitly report
architecture alignment. For each violation or proposed architecture change,
name the affected diagram component/connection/boundary, cite the PR code,
and explain what is violated or changed and its impact. Intentional changes
must be discussed and reflected in the design and diagram before merge.

# Protocol Compatibility Rules

Increase the checked protocol ID whenever an existing API between the Firefox
extension and MCP server is modified or removed. This includes changes to
parameters, responses, errors and observable behavior. Increase at most once
per release relative to the previous released tag: retain its ID for compatible
changes, or use its ID plus one for all incompatible changes accumulated since
that release. Do not increment again per PR or intermediate candidate.
Keep protocol docs and compatibility tests aligned. See `docs/protocol.md#protocol-id-compatibility-policy`
for the authoritative policy and current ID location.

Before every release, compare API changes with the previous released tag and
record whether the protocol ID must increase, including the rationale if it
stays unchanged. Do not tag or publish until this review is complete. A release
version bump or version-consistency check does not replace this review.

# Testing Guidelines
ALWAYS use example.org for test URLs instead of httpbin.org or any other service.
- example.org is the official reserved domain for testing and documentation
- Use paths like https://example.org/path1, https://example.org/test, etc.
- NEVER use httpbin.org, httpbin.com, or similar external testing services
- This ensures tests are reliable and don't depend on external services

## Firefox Test Setup
ALWAYS use the consolidated method `setup_and_start_firefox()` for Firefox test setup:
- USE: `firefox.setup_and_start_firefox(headless=True)`
- Extension path is automatically determined internally using `_get_extension_xpi_path()`
- The old individual methods (`create_test_profile()`, `install_extension()`, `start_firefox()`) have been removed
- This ensures consistent setup, error handling, and reduces code duplication across tests
- Internal methods (`_create_test_profile()`, `_get_extension_xpi_path()`, etc.) are implementation details and should not be called directly

# Debugging Configuration

## ENABLE_DEBUG_LOGGING_TO_SERVER Setting

Controls whether the Firefox extension sends debug messages to the server.
Find `ENABLE_DEBUG_LOGGING_TO_SERVER` in `extension/background.js`.

```javascript
const ENABLE_DEBUG_LOGGING_TO_SERVER = false;  // Set to true for debugging
```

**Usage:**
- Enable (`true`) for debugging extension connection issues or test failures
- Disable (`false`) for production and before committing
- After changing, run `make -C "$FM_ROOT" package`; it rebuilds the extension
  and clears the profile cache.

**IMPORTANT: Always set back to `false` before committing.**

# Documentation Files Reference

## Project status and planning
Tracked outside this repo, in the docforge at
`~/progm/claudebugzilla/proj_docs/foxmcp/` — see its `HANDOFF.md` for current
status and next actions, and `DESIGN.md` for the decisions behind the
architecture. `docs/PLAN.md` used to hold this and was retired on 2026-08-11
after drifting out of date.

Reference documentation for how FoxMCP *works* stays here in `docs/`.

## docs/protocol.md
- WebSocket message protocol specification
- JSON format with complete request/response examples
- All browser function definitions and error codes

## docs/files.md
- Source file map and component responsibilities
- Shared settings UI, profile routing, build outputs and test entry points

## README.md
- Main project documentation and quick start guide
- Development commands and troubleshooting
- Links to product reference documentation

## docs/api-reference.md
- Complete MCP tool reference and parameters

## tests/README.md
- Test suite documentation and running instructions
- Unit and integration test organization

