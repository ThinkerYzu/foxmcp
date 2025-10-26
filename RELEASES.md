# FoxMCP Releases

This document provides release notes and upgrade instructions for FoxMCP.

## v1.1.0 - Enhanced Automation (2025-10-26)

### 🚀 Feature Release

**FoxMCP v1.1.0** adds powerful new capabilities for web request monitoring, enhanced bookmark management, and ready-to-use automation scripts. This release builds on the solid v1.0.0 foundation with practical features for common automation tasks.

### ✨ New Features

#### **Web Request Monitoring API**
Monitor and capture HTTP requests/responses in real-time:
- **Start Monitoring**: `requests_start_monitoring()` - Begin capturing network activity
- **List Captured Data**: `requests_list_captured()` - Retrieve captured requests/responses
- **Stop Monitoring**: `requests_stop_monitoring()` - End capture session and cleanup
- **Two-Phase Workflow**: Start monitoring → perform actions → retrieve data → stop
- **Use Cases**: Debug API calls, analyze network traffic, validate request patterns

#### **Enhanced Bookmark Management**
New bookmark operations for better organization:
- **Folder Creation**: Create bookmark folders with proper hierarchy support
- **Update Bookmarks**: Modify existing bookmark titles, URLs, and locations
- **Improved Reliability**: Fixed integration test failures and enhanced error handling

#### **Predefined Scripts Collection**
Ready-to-use scripts for common automation tasks:

**YouTube Control** (`youtube-play-pause.sh`)
- Play, pause, or toggle YouTube videos programmatically
- Returns video state, current time, and duration
- Example: `content_execute_predefined(tab_id, "youtube-play-pause.sh", "[]")`

**DOM Simplification** (`dom-summarize.sh`)
- Simplify complex DOM trees for AI agent understanding
- Extract visible interactive elements with persistent IDs
- Supports viewport-only filtering and position data
- Example: `content_execute_predefined(tab_id, "dom-summarize.sh", "[\"onscreen\"]")`

**Google Calendar Integration** (3 scripts)
- `gcal-cal-event-js.sh`: Extract specific event details by title, day, and time
- `gcal-daily-events-js.sh`: Get all events for a specific day
- `gcal-monthly-events-js.sh`: Extract entire month view with statistics
- Perfect for calendar automation and event management

#### **Content API Enhancement**
- **max_length Parameter**: Optional parameter for `content_get_text` tool
- **Context Management**: Truncate large text extractions to fit AI context windows
- **Flexible Extraction**: Choose between full text or length-limited summaries

#### **Installation Improvements**
- **Firefox Add-ons Store**: Official installation option now available
- **Simplified Instructions**: Single-command installation process
- **Script Inclusion**: Installation script now downloads all predefined scripts
- **Better Documentation**: Enhanced setup guides and troubleshooting

### 🐛 Bug Fixes

#### **Critical History Fixes**
- **Query Filtering**: Fixed parameter mismatch preventing history search filtering
  - Extension now correctly reads `query` parameter
  - Non-matching entries properly excluded from results
  - All tests updated to use correct parameter names

- **Timestamp Display**: Fixed "Unknown time" in history MCP tools
  - Tools now correctly read `lastVisitTime` field
  - AI agents see actual timestamps (milliseconds since epoch)
  - Affects `history_query` and `history_get_recent` tools

#### **Other Fixes**
- **Bookmark Tests**: Fixed intermittent bookmark management test failures
- **Calendar Script**: Fixed gcal-daily-events-js.sh month detection
- **Profile Cache**: Clear cache after packaging to prevent stale data

### 🔧 Improvements

#### **Testing & Quality**
- **211 Total Tests**: 59 unit + 152 integration tests, all passing
- **History Validation**: Comprehensive timestamp validation in all tests
- **Query Testing**: New tests verify filtering excludes non-matching entries
- **100% Pass Rate**: All tests enabled and maintaining quality standards

#### **Developer Experience**
- **Debug Logging**: Configurable `ENABLE_DEBUG_LOGGING_TO_SERVER` setting
- **Enhanced Documentation**: Comprehensive CLAUDE.md updates
- **Script Documentation**: Detailed usage examples for all predefined scripts
- **Better Error Messages**: Improved debugging and troubleshooting

### 📦 Installation

#### **Upgrade from v1.0.0**
```bash
# Pull latest changes
git pull origin master

# Rebuild extension and server
make clean
make package

# Clear profile cache
rm -rf dist/profile-cache/*

# Reinstall extension
./scripts/install-xpi.sh /path/to/firefox/profile

# Restart Firefox and server
```

#### **Fresh Installation**
```bash
# One-command installation (installs v1.1.0)
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/install-from-github.sh | bash
```

#### **Package Downloads**
- **Firefox Extension**: [foxmcp@codemud.org.xpi](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/foxmcp@codemud.org.xpi)
- **Server Package**: [foxmcp-server.zip](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.1.0/foxmcp-server.zip)
- **Source Code**: [v1.1.0.tar.gz](https://github.com/ThinkerYzu/foxmcp/archive/v1.1.0.tar.gz)

### 🎯 Use Cases

#### **Network Analysis**
```python
# Start monitoring network requests
requests_start_monitoring()

# Perform actions that trigger requests
tabs_navigate(tab_id, "https://example.org/api")

# Retrieve captured data
data = requests_list_captured()

# Stop monitoring
requests_stop_monitoring()
```

#### **Calendar Automation**
```python
# Get today's meetings (if today is the 26th)
events = content_execute_predefined(tab_id, "gcal-daily-events-js.sh", "[\"26\"]")

# Get specific event details
event = content_execute_predefined(
    tab_id,
    "gcal-cal-event-js.sh",
    "[\"Team Standup\", \"26\", \"9:00am\"]"
)
```

#### **YouTube Control**
```python
# Toggle play/pause
result = content_execute_predefined(tab_id, "youtube-play-pause.sh", "[]")

# Explicitly pause
result = content_execute_predefined(tab_id, "youtube-play-pause.sh", "[\"pause\"]")
```

### 🔄 Breaking Changes

**None** - This release is fully backward compatible with v1.0.0.

### 📊 Statistics

- **25 Commits** since v1.0.0
- **5 New APIs** (web request monitoring)
- **5 Predefined Scripts** included
- **40+ Test Additions** for new features
- **2 Critical Fixes** (history timestamp and filtering)

### 🌟 Community Highlights

This release includes contributions and feedback addressing:
- Request monitoring for debugging workflows
- Calendar integration for productivity automation
- YouTube control for media management
- History fixes improving search reliability

### 📚 Documentation Updates

- **README.md**: Updated with v1.1.0 features and predefined scripts
- **CLAUDE.md**: Comprehensive predefined scripts documentation
- **Protocol Docs**: Web request monitoring message formats
- **Installation Guide**: Simplified single-command setup

### 🚧 Future Roadmap

Building on v1.1.0, planned enhancements include:
- **Complete Web Request API**: Full request/response inspection and filtering
- **Downloads Management**: Download tracking and control
- **Cookie Management**: Comprehensive cookie operations
- **Enhanced MCP Features**: Batch operations and event streaming

### ⚠️ Notes

- **Extension Rebuild Required**: After upgrade, run `make package` and reinstall
- **Profile Cache**: Clear `dist/profile-cache/*` for clean test environment
- **Predefined Scripts**: Located in `predefined-scripts/` directory
- **Debug Logging**: Disabled by default; enable in `extension/background.js:97`

### 💬 Feedback

We welcome feedback on the new features:
- Report issues via [GitHub Issues](https://github.com/ThinkerYzu/foxmcp/issues)
- Share your automation scripts and use cases
- Suggest new predefined scripts for common tasks
- Contribute improvements via pull requests

---

**Thank you for upgrading to FoxMCP v1.1.0!** This release adds practical automation capabilities while maintaining the stability and reliability of the v1.0.0 foundation.

## v1.0.0 - Initial Release (2024-09-28)

### 🚀 First Stable Release

**FoxMCP v1.0.0** marks the first stable release of Firefox browser automation through the Model Context Protocol (MCP). This release provides a complete, production-ready solution for programmatic browser control.

### ✨ Key Features

#### **Complete Browser Control**
- **Tab Management**: List, create, close, switch between tabs with screenshot capability
- **Window Management**: Create, close, focus, resize windows with cross-window operations
- **Navigation**: Back, forward, reload, and URL navigation with cache control
- **Content Interaction**: Extract text/HTML, execute JavaScript, run custom scripts
- **History Access**: Query browsing history with text search and date filtering
- **Bookmark Operations**: Full bookmark management with folder support and search

#### **MCP Protocol Integration**
- **25+ MCP Tools**: All browser functions exposed via standardized MCP interface
- **Dual Architecture**: WebSocket server (8765) + MCP server (3000)
- **Claude Code Ready**: Direct integration with `claude mcp add` command
- **Real-time Communication**: Automatic reconnection with comprehensive error handling

#### **Developer Experience**
- **Automated Installation**: One-command extension installation with preference setup
- **Comprehensive Testing**: 171 tests covering all functionality with CI/CD ready
- **Complete Documentation**: API reference, guides, and examples
- **Cross-Platform**: Linux, macOS, Windows support

### 📦 Installation

#### **One-Command Installation**
```bash
curl -L https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/install-from-github.sh | bash
```

This automatically downloads v1.0.0 binaries, sets up Python environment, installs dependencies, configures Firefox extension, downloads Google Calendar automation scripts, and creates Claude Code integration files.

#### **Package Downloads**
- **Firefox Extension**: [foxmcp@codemud.org.xpi](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/foxmcp@codemud.org.xpi)
- **Server Package**: [foxmcp-server.zip](https://github.com/ThinkerYzu/foxmcp/releases/download/v1.0.0/foxmcp-server.zip)
- **Source Code**: [v1.0.0.tar.gz](https://github.com/ThinkerYzu/foxmcp/archive/v1.0.0.tar.gz)

### 🔧 System Requirements

- **Firefox**: Any recent version supporting WebExtensions
- **Python**: 3.8 or higher with asyncio support
- **Operating System**: Linux, macOS, or Windows
- **Network**: Localhost access (ports 8765, 3000)

### 🎯 Use Cases

#### **Development & Testing**
- Automated browser testing with AI assistance
- Cross-tab and cross-window testing scenarios
- Dynamic content extraction and validation

#### **AI-Assisted Workflows**
- Intelligent bookmark management and organization
- History-based research and information retrieval
- Automated form filling and data entry

#### **Custom Automation**
- Predefined external scripts for repetitive tasks
- JavaScript execution in browser contexts
- Screenshot capture for documentation

### 🛠️ Architecture

```
MCP Client (Claude Code) → FastMCP Server (3000) → WebSocket (8765) → Firefox Extension → Browser API
```

#### **Core Components**
- **Firefox Extension**: WebExtensions-based browser integration
- **Python Server**: FastMCP + WebSocket dual-server architecture
- **Message Protocol**: JSON-based bidirectional communication
- **MCP Tools**: 25+ standardized browser control functions

### 📚 Documentation

- **[README.md](README.md)**: Quick start and overview
- **[API Reference](docs/api-reference.md)**: Complete function reference
- **[Development Guide](docs/development.md)**: Setup and workflow
- **[Configuration](docs/configuration.md)**: Server and extension setup
- **[Architecture](docs/architecture.md)**: System design and components
- **[Protocol](docs/protocol.md)**: WebSocket message specification

### 🔒 Security

- **Localhost-Only**: Servers bind exclusively to localhost interface
- **Input Validation**: Comprehensive sanitization and validation
- **Minimal Permissions**: Extension uses only required browser permissions
- **Secure Scripting**: Path validation for external script execution

### 🧪 Quality Assurance

- **171 Automated Tests**: Unit and integration test coverage
- **Cross-Platform Testing**: Verified on Linux, macOS, Windows
- **Real Firefox Integration**: Tests run against actual Firefox instances
- **Memory Management**: Proper resource cleanup and leak prevention

### 🌟 Community

- **Open Source**: MIT License with full source availability
- **Issue Tracking**: GitHub Issues for bug reports and feature requests
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines
- **Support**: Community-driven support and documentation

### 🚧 Future Roadmap

The v1.0.0 release establishes a solid foundation for browser automation. Planned future enhancements include:

- **Downloads Management**: Complete downloads API integration
- **Cookie Management**: Comprehensive cookie operations
- **Web Request Interception**: HTTP request/response manipulation
- **Enhanced MCP Features**: Batch operations and event streaming

### ⚠️ Known Limitations

- **Firefox Only**: Currently supports Firefox; Chrome support planned for future releases
- **Localhost Binding**: Servers bind only to localhost for security (not remotely accessible)
- **Extension Signing**: Requires Firefox preference changes for unsigned extension installation

### 💬 Feedback

We welcome feedback and contributions! Please:
- Report bugs via [GitHub Issues](https://github.com/foxmcp/foxmcp/issues)
- Suggest features through issue discussions
- Contribute code via pull requests
- Share your use cases and success stories

---

**Thank you for using FoxMCP!** This v1.0.0 release represents months of development and testing to create a robust, reliable browser automation solution for the AI era.