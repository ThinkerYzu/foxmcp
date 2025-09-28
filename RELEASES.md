# FoxMCP Releases

This document provides release notes and upgrade instructions for FoxMCP.

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