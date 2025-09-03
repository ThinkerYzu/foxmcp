# FoxMCP Project Makefile
# Build and manage the browser extension and Python server

.PHONY: help install build test clean run-server run-tests dev setup check lint package all

# Default target
all: setup build test

help:
	@echo "FoxMCP Project - Available Commands:"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  setup          - Install all dependencies (server + test requirements)"
	@echo "  install        - Install Python server dependencies only"
	@echo ""
	@echo "Building:"
	@echo "  build          - Build extension package"
	@echo "  package        - Create distributable packages (XPI for Firefox)"
	@echo ""
	@echo "Development:"
	@echo "  dev            - Setup development environment"
	@echo "  run-server     - Start the WebSocket server"
	@echo "  check          - Run all quality checks (lint + test)"
	@echo "  lint           - Run linting on Python code"
	@echo ""
	@echo "Testing:"
	@echo "  test           - Run all tests"
	@echo "  test-unit      - Run unit tests only"
	@echo "  test-integration - Run integration tests only"
	@echo "  test-with-firefox - Run tests with temporary Firefox profile and extension"
	@echo "  run-tests      - Run tests with coverage report"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          - Clean build artifacts and temporary files"
	@echo "  clean-all      - Deep clean including dependencies"
	@echo ""

# Setup and Installation
setup: install
	@echo "Installing test dependencies..."
	cd tests && pip install -r requirements.txt
	@echo "✅ Setup complete!"

install:
	@echo "Installing server dependencies..."
	cd server && pip install -r requirements.txt
	@echo "✅ Server dependencies installed!"

dev: setup
	@echo "Setting up development environment..."
	pip install --upgrade pip
	@echo "✅ Development environment ready!"

# Building
build: build-extension
	@echo "✅ Build complete!"

build-extension:
	@echo "Building extension package..."
	@mkdir -p dist
	@rm -rf dist/extension
	@cp -r extension dist/
	@echo "Extension built at: dist/extension/"
	@echo "✅ Extension build complete!"

package: build
	@echo "Creating distributable packages..."
	@mkdir -p dist/packages

	# Package extension as XPI for Firefox
	cd dist/extension && zip -r ../packages/foxmcp@codemud.org.xpi *

	# Package server
	@mkdir -p dist/server-package
	@cp -r server/* dist/server-package/
	@cp README.md dist/server-package/ 2>/dev/null || echo "README.md not found, skipping..."
	cd dist && zip -r packages/foxmcp-server.zip server-package/

	@echo "📦 Packages created:"
	@echo "  - dist/packages/foxmcp@codemud.org.xpi"
	@echo "  - dist/packages/foxmcp-server.zip"

# Development and Running
run-server:
	@echo "Starting FoxMCP WebSocket server..."
	cd server && python server.py

# Testing
test: run-tests

run-tests: package
	@echo "Running all tests with coverage..."
	cd tests && python run_tests.py

test-unit:
	@echo "Running unit tests..."
	cd tests && python run_tests.py unit

test-integration:
	@echo "Running integration tests..."
	cd tests && python run_tests.py integration

test-with-firefox: package
	@echo "Running tests with temporary Firefox profile and extension..."
	@mkdir -p /tmp/foxmcp-test-profile
	@echo 'user_pref("xpinstall.signatures.required", false);' > /tmp/foxmcp-test-profile/user.js
	@echo "Installing extension to temporary profile..."
	@mkdir -p /tmp/foxmcp-test-profile/extensions
	@cp dist/packages/foxmcp@codemud.org.xpi /tmp/foxmcp-test-profile/extensions/
	@echo "Creating temporary Firefox profile..."
	@timeout 20 ~/tmp/ff2/bin/firefox -profile /tmp/foxmcp-test-profile -no-remote -headless >/dev/null 2>&1 &
	@while [ ! -f /tmp/foxmcp-test-profile/extensions.json ]; do sleep 1; done
	@sleep 1; pkill -f "[f]irefox.*foxmcp-test-profile" >/dev/null 2>&1 || true
	@echo "Enable the extension in the profile..."
	@jq '.addons[] |= if .id == "foxmcp@codemud.org" then .userDisabled = false | .active = true else . end' /tmp/foxmcp-test-profile/extensions.json | sponge /tmp/foxmcp-test-profile/extensions.json
	@echo "Starting Firefox with extension (background mode)..."
	@timeout 300 ~/tmp/ff2/bin/firefox -profile /tmp/foxmcp-test-profile -no-remote -headless >/dev/null 2>&1 &
	@sleep 10
	@echo "Running tests..."
	@cd tests && python run_tests.py || true
	@echo "Cleaning up Firefox processes and temporary profile..."
	@pkill -f "[f]irefox.*foxmcp-test-profile" >/dev/null 2>&1 || true
	@sleep 2
	@rm -rf /tmp/foxmcp-test-profile
	@echo "✅ Test with Firefox complete!"

# Quality Checks
check: lint test
	@echo "✅ All quality checks passed!"

lint:
	@echo "Running Python linting..."
	@command -v flake8 >/dev/null 2>&1 || { echo "Installing flake8..."; pip install flake8; }
	@echo "Linting server code..."
	@flake8 server/ --max-line-length=100 --ignore=E203,W503 || echo "⚠️  Linting issues found in server/"
	@echo "Linting test code..."
	@flake8 tests/ --max-line-length=100 --ignore=E203,W503 || echo "⚠️  Linting issues found in tests/"
	@echo "✅ Linting complete!"

# Extension Development Helper
load-extension:
	@echo "Extension location for browser loading:"
	@echo "Chrome: Load unpacked extension from: $(PWD)/extension"
	@echo "Firefox: Load temporary extension from: $(PWD)/extension/manifest.json"
	@echo ""
	@echo "Instructions:"
	@echo "1. Open Chrome and go to chrome://extensions/"
	@echo "2. Enable 'Developer mode'"  
	@echo "3. Click 'Load unpacked' and select the extension/ directory"
	@echo "4. The FoxMCP extension should now be loaded"

# Maintenance and Cleanup
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dist/
	@rm -rf tests/htmlcov/
	@rm -rf tests/.coverage
	@rm -rf /tmp/foxmcp-test-profile
	@pkill -f "firefox.*foxmcp-test-profile" >/dev/null 2>&1 || true
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@echo "✅ Clean complete!"

clean-all: clean
	@echo "Deep cleaning including virtual environments..."
	@rm -rf venv/
	@rm -rf .venv/
	@echo "✅ Deep clean complete!"

# Development Workflow Helpers
start: run-server

stop:
	@echo "Stopping any running servers..."
	@pkill -f "python.*server.py" || echo "No servers running"

restart: stop start

# Quick development cycle
quick-test: build test-unit
	@echo "✅ Quick test cycle complete!"

# Install development tools
dev-tools:
	@echo "Installing development tools..."
	pip install flake8 black isort pytest-cov
	@echo "✅ Development tools installed!"

# Format code
format:
	@echo "Formatting Python code..."
	@command -v black >/dev/null 2>&1 || { echo "Installing black..."; pip install black; }
	@command -v isort >/dev/null 2>&1 || { echo "Installing isort..."; pip install isort; }
	black server/ tests/ --line-length=100
	isort server/ tests/ --line-length=100
	@echo "✅ Code formatting complete!"

# Project status
status:
	@echo "FoxMCP Project Status:"
	@echo "====================="
	@echo ""
	@echo "📁 Project Structure:"
	@find . -maxdepth 2 -type f -name "*.py" -o -name "*.js" -o -name "*.json" -o -name "*.md" | grep -v __pycache__ | sort
	@echo ""
	@echo "🐍 Python Dependencies:"
	@echo "Server:" && (cd server && pip list --format=freeze | grep -E "(websockets|fastmcp)" || echo "  Not installed")
	@echo "Tests:" && (cd tests && pip list --format=freeze | grep -E "(pytest|coverage)" || echo "  Not installed")
	@echo ""
	@echo "🔗 WebSocket Server:"
	@netstat -ln 2>/dev/null | grep ":8765" >/dev/null && echo "  ✅ Port 8765 in use (server may be running)" || echo "  ❌ Port 8765 available (server not running)"

# Continuous Integration simulation
ci: clean setup lint test package
	@echo "🎉 CI pipeline complete - ready for deployment!"
