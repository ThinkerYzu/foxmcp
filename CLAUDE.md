This project is to create an extension to expose data and function to MCP client.

It will create an extension and a MCP server that talk to the extension.
The MCP server will be implemented in Python with FastMCP.
It is Websocket between the extension and the MCP server.

# Claude Code Integration

## FM_ROOT Environment Variable
The `FM_ROOT` environment variable is set to the project root directory. This enables Claude Code to reference project paths consistently when running bash commands.

**IMPORTANT: Always use `$FM_ROOT` in bash commands to refer to project files and paths - this is much less error-prone than relative paths.**

Examples of proper usage:
```bash
# Read project files
cat $FM_ROOT/README.md
ls $FM_ROOT/tests/

# Run tests with proper paths
PYTHONPATH=$FM_ROOT/tests $FM_ROOT/venv/bin/python -m pytest $FM_ROOT/tests/test_example.py

# Edit files with absolute paths
vim $FM_ROOT/server/server.py

# Find files in project
find $FM_ROOT -name "*.py" -type f
```

Benefits of using `$FM_ROOT`:
- ✅ **Error-free paths** - No ambiguity about working directory
- ✅ **Consistent execution** - Commands work from any directory
- ✅ **Clear intent** - Obviously references project files
- ✅ **Reliable automation** - No path resolution issues

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
NEVER create git commits unless explicitly requested by the User.
NEVER add Claude Code attribution or "Generated with Claude Code" footer in git commit messages.

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

# Documentation Files Reference

## PLAN.md
- Development plan with 4 phases (3 complete, 1 partial)
- Current implementation status and next priority tasks
- 14 total tasks: 12 completed, 5 pending
- Comprehensive test suite with 77 tests passing (39 unit + 38 integration), 74% coverage, all tests enabled

## protocol.md  
- WebSocket message protocol specification
- JSON format with complete request/response examples
- All browser function definitions and error codes

## files.md
- Complete project structure (26 files + venv)
- Implementation details for each component
- Current status: foundation complete, tests working, browser APIs pending

## README.md
- Main project documentation and quick start guide
- Development commands and troubleshooting
- Complete browser function reference

## tests/README.md
- Test suite documentation and running instructions
- Unit and integration test organization

