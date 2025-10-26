#!/bin/bash

# FoxMCP v1.1.0 Release Commands
# Run these commands to create the official release

echo "🚀 FoxMCP v1.1.0 Release Process"
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
git commit -m "Release v1.1.0

- Web request monitoring API
- Bookmark folder creation and update
- Content API max_length parameter
- Predefined scripts (YouTube, DOM summarize, Google Calendar)
- History timestamp and query filtering fixes
- Firefox Add-ons store installation option

This release adds monitoring capabilities, enhanced bookmark management,
and useful predefined scripts for common automation tasks."

echo ""
echo "Step 5: Create and push git tag..."
git tag -a v1.1.0 -m "FoxMCP v1.1.0 - Enhanced browser automation

Adds web request monitoring, bookmark enhancements, predefined scripts,
and important bug fixes for history management."

echo ""
echo "Step 6: Push to GitHub..."
echo "git push origin master"
echo "git push origin v1.1.0"

echo ""
echo "🎯 Next Steps (Manual):"
echo "1. Run: git push origin master"
echo "2. Run: git push origin v1.1.0"
echo "3. Go to GitHub and create release from v1.1.0 tag"
echo "4. Upload these files as release assets:"
echo "   - dist/packages/foxmcp@codemud.org.xpi"
echo "   - dist/packages/foxmcp-server.zip"
echo ""
echo "📋 GitHub Release Notes Template:"
echo "================================="
echo ""
echo "## FoxMCP v1.1.0 - Enhanced Automation"
echo ""
echo "🚀 **Feature release** with web request monitoring, bookmark enhancements, and predefined scripts"
echo ""
echo "### ✨ New Features"
echo "- **Web Request Monitoring**: Capture and inspect network requests/responses"
echo "- **Bookmark Management**: Create folders and update existing bookmarks"
echo "- **Predefined Scripts**: YouTube control, DOM summarize, Google Calendar integration"
echo "- **Content API Enhancement**: Optional max_length parameter for text extraction"
echo "- **Firefox Add-ons Store**: Direct installation option available"
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
echo "Execute the commands above to publish FoxMCP v1.1.0"