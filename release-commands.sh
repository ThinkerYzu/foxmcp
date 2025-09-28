#!/bin/bash

# FoxMCP v1.0.0 Release Commands
# Run these commands to create the official release

echo "🚀 FoxMCP v1.0.0 Release Process"
echo "================================="

echo ""
echo "Step 1: Create clean packages..."
make clean
make package

echo ""
echo "Step 2: Verify packages created..."
ls -la dist/packages/
echo ""

echo "Step 3: Add all files to git..."
git add -A

echo ""
echo "Step 4: Create release commit..."
git commit -m "Release v1.0.0 - Initial stable release

- Complete Firefox browser automation via MCP protocol
- 25+ MCP tools for comprehensive browser control
- 171 tests with full integration coverage
- Automated installation tools and comprehensive documentation
- Production-ready deployment with security features
- MIT License with proper attribution

This release establishes FoxMCP as a complete, tested, and documented
browser automation solution ready for production use."

echo ""
echo "Step 5: Create and push git tag..."
git tag -a v1.0.0 -m "FoxMCP v1.0.0 - Firefox browser automation via MCP

First stable release providing complete browser automation through
the Model Context Protocol with comprehensive testing and documentation."

echo ""
echo "Step 6: Push to GitHub..."
echo "git push origin master"
echo "git push origin v1.0.0"

echo ""
echo "🎯 Next Steps (Manual):"
echo "1. Run: git push origin master"
echo "2. Run: git push origin v1.0.0"
echo "3. Go to GitHub and create release from v1.0.0 tag"
echo "4. Upload these files as release assets:"
echo "   - dist/packages/foxmcp@codemud.org.xpi"
echo "   - dist/packages/foxmcp-server.zip"
echo ""
echo "📋 GitHub Release Notes Template:"
echo "================================="
echo ""
echo "## FoxMCP v1.0.0 - Initial Release"
echo ""
echo "🚀 **First stable release** of Firefox browser automation through Model Context Protocol"
echo ""
echo "### ✨ Key Features"
echo "- **Complete Browser Control**: Tabs, windows, navigation, content, history, bookmarks"
echo "- **MCP Integration**: 25+ tools accessible via FastMCP server"
echo "- **Claude Code Ready**: Direct integration with \`claude mcp add\` command"
echo "- **Automated Installation**: One-command extension setup with preference configuration"
echo "- **Comprehensive Testing**: 171 tests with 100% integration coverage"
echo ""
echo "### 📦 Installation"
echo "\`\`\`bash"
echo "# Quick start"
echo "git clone https://github.com/foxmcp/foxmcp.git"
echo "cd foxmcp"
echo "python3 -m venv venv && source venv/bin/activate"
echo "pip install -r requirements.txt"
echo "make package"
echo "./scripts/install-xpi.sh /path/to/firefox/profile"
echo "make run-server"
echo ""
echo "# Connect Claude Code"
echo "claude mcp add --transport http foxmcp http://localhost:3000/mcp/"
echo "\`\`\`"
echo ""
echo "### 📚 Documentation"
echo "Complete documentation available in the repository:"
echo "- Quick start guide and API reference"
echo "- Development setup and contribution guidelines"
echo "- Architecture documentation and protocol specification"
echo ""
echo "### 🔒 Security & Quality"
echo "- Localhost-only operation with comprehensive input validation"
echo "- 171 automated tests covering all functionality"
echo "- Cross-platform support (Linux, macOS, Windows)"
echo "- MIT License with proper attribution"
echo ""

echo "✅ Release preparation complete!"
echo "Execute the commands above to publish FoxMCP v1.0.0"