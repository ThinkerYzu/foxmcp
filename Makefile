# FoxMCP Project Makefile
# Build and manage the browser extension and Python server

# Variables
FIREFOX_PATH ?= firefox

# Install into the project venv explicitly, and run its tools from there too. A
# bare `pip` targets whatever interpreter happens to be active, which is how the
# venv ended up holding the server dependencies but no pytest; a bare `flake8`
# has the matching problem of resolving against PATH rather than the venv the
# package was just installed into.
VENV_BIN ?= venv/bin
VENV_PIP ?= $(VENV_BIN)/pip

# The interpreter used to build venv/ in the first place, not to run anything
# afterwards. Override it to build the venv against a different Python.
PYTHON ?= python3

.PHONY: help install build test clean run-server run-tests dev setup check lint package all setup-test-imports venv

# Default target
all: setup build test

help:
	@echo "FoxMCP Project - Available Commands:"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  venv           - Create the virtual environment (implied by setup)"
	@echo "  setup          - Install all dependencies (server + test requirements)"
	@echo "  install        - Install Python server dependencies only"
	@echo "  setup-test-imports - Create symbolic links for test import system"
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
	@echo "  run-tests      - Run tests with coverage report"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean          - Clean build artifacts and temporary files"
	@echo "  clean-all      - Deep clean including dependencies"
	@echo ""

# Setup and Installation
setup: install setup-test-imports
	@echo "Installing test dependencies..."
	$(VENV_PIP) install -r tests/requirements.txt
	@echo "✅ Setup complete!"

# Create the virtual environment everything else in this file runs out of.
#
# The real target is venv/bin/python rather than venv/, so make skips the work
# once the interpreter is there. Without this, `make setup` on a fresh clone
# died on a missing venv/bin/pip and said nothing about what to do next.
$(VENV_BIN)/python:
	@echo "Creating the virtual environment..."
	$(PYTHON) -m venv venv
	@echo "✅ Virtual environment created at venv/"

venv: $(VENV_BIN)/python
	@echo "✅ Virtual environment ready at venv/"

install: $(VENV_BIN)/python
	@echo "Installing server dependencies..."
	$(VENV_PIP) install -r server/requirements.txt
	@echo "✅ Server dependencies installed!"

setup-test-imports:
	@echo "Setting up test import symbolic links..."
	@# Create symbolic links for test_imports.py in subdirectories
	@if [ ! -L tests/integration/test_imports.py ]; then \
		echo "  Creating tests/integration/test_imports.py -> ../test_imports.py"; \
		ln -sf ../test_imports.py tests/integration/test_imports.py; \
	else \
		echo "  ✓ tests/integration/test_imports.py already exists"; \
	fi
	@if [ ! -L tests/unit/test_imports.py ]; then \
		echo "  Creating tests/unit/test_imports.py -> ../test_imports.py"; \
		ln -sf ../test_imports.py tests/unit/test_imports.py; \
	else \
		echo "  ✓ tests/unit/test_imports.py already exists"; \
	fi
	@# Verify the links work
	@echo "  Verifying symbolic links..."
	@if [ -L tests/integration/test_imports.py ] && [ -L tests/unit/test_imports.py ]; then \
		echo "  ✅ Test import symbolic links configured successfully!"; \
	else \
		echo "  ❌ Failed to create symbolic links"; \
		exit 1; \
	fi

dev: setup
	@echo "Setting up development environment..."
	$(VENV_PIP) install --upgrade pip
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

# Build the two release archives, containing exactly what the source tree holds.
#
# Both archives and the server staging directory are cleared before being
# written. zip updates an existing archive instead of replacing it, so a file
# deleted from the source tree used to survive in the package until someone ran
# `make clean` — and the staging copy had the same problem. Bytecode is dropped
# because `cp -r server/*` otherwise sweeps up whatever __pycache__ the last
# local run left behind, which made a build here and a build in CI differ.
package: build
	@echo "Creating distributable packages..."
	@mkdir -p dist/packages
	@rm -f dist/packages/foxmcp@codemud.org.xpi dist/packages/foxmcp-server.zip
	@rm -rf dist/server-package

	# Package extension as XPI for Firefox
	cd dist/extension && zip -r ../packages/foxmcp@codemud.org.xpi *

	# Package server
	@mkdir -p dist/server-package
	@cp -r server/* dist/server-package/
	@find dist/server-package -type d -name __pycache__ -prune -exec rm -rf {} +
	@cp README.md dist/server-package/ 2>/dev/null || echo "README.md not found, skipping..."
	cd dist && zip -r packages/foxmcp-server.zip server-package/

	# Clear profile cache since extension has changed
	@echo "Clearing profile cache..."
	@rm -rf dist/profile-cache/*
	@echo "✓ Profile cache cleared"

	@echo "📦 Packages created:"
	@echo "  - dist/packages/foxmcp@codemud.org.xpi"
	@echo "  - dist/packages/foxmcp-server.zip"

# Development and Running
# Run the server out of the project venv, like every other target here.
#
# This used to be `cd server && python server.py`, which takes whatever `python`
# is on PATH — the same mistake the pip calls above used to make. On a machine
# where `python` is some other venv, or does not exist at all, the recipe failed
# on an import that has been installed all along.
run-server:
	@echo "Starting FoxMCP WebSocket server..."
	$(VENV_BIN)/python server/server.py

# Testing
test: run-tests

run-tests: setup-test-imports package
	@echo "Running all tests with coverage..."
	cd tests && FIREFOX_PATH=$(FIREFOX_PATH) ../venv/bin/python run_tests.py

test-unit: setup-test-imports
	@echo "Running unit tests..."
	cd tests && PYTHONPATH=.. FIREFOX_PATH=$(FIREFOX_PATH) ../venv/bin/python run_tests.py unit

test-integration: setup-test-imports package
	@echo "Running integration tests..."
	cd tests && PYTHONPATH=.. FIREFOX_PATH=$(FIREFOX_PATH) ../venv/bin/python run_tests.py integration


# Quality Checks
check: lint test
	@echo "✅ All quality checks passed!"

lint:
	@echo "Running Python linting..."
	@test -x $(VENV_BIN)/flake8 || { echo "Installing flake8..."; $(VENV_PIP) install flake8; }
	@echo "Linting server code..."
	@$(VENV_BIN)/flake8 server/ --max-line-length=100 --ignore=E203,W503 || echo "⚠️  Linting issues found in server/"
	@echo "Linting test code..."
	@$(VENV_BIN)/flake8 tests/ --max-line-length=100 --ignore=E203,W503 || echo "⚠️  Linting issues found in tests/"
	@echo "✅ Linting complete!"


# Maintenance and Cleanup
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dist/
	@rm -rf tests/htmlcov/
	@rm -rf tests/.coverage
	@rm -rf /tmp/foxmcp-test-profile
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@# Remove test import symbolic links
	@rm -f tests/integration/test_imports.py tests/unit/test_imports.py
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
	$(VENV_PIP) install flake8 black isort pytest-cov
	@echo "✅ Development tools installed!"

# Format code
format:
	@echo "Formatting Python code..."
	@test -x $(VENV_BIN)/black || { echo "Installing black..."; $(VENV_PIP) install black; }
	@test -x $(VENV_BIN)/isort || { echo "Installing isort..."; $(VENV_PIP) install isort; }
	$(VENV_BIN)/black server/ tests/ --line-length=100
	$(VENV_BIN)/isort server/ tests/ --line-length=100
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
	@echo "Server:" && ($(VENV_PIP) list --format=freeze | grep -E "(websockets|fastmcp)" || echo "  Not installed")
	@echo "Tests:" && ($(VENV_PIP) list --format=freeze | grep -E "(pytest|coverage)" || echo "  Not installed")
	@echo ""
	@echo "🔗 WebSocket Server:"
	@netstat -ln 2>/dev/null | grep ":8765" >/dev/null && echo "  ✅ Port 8765 in use (server may be running)" || echo "  ❌ Port 8765 available (server not running)"
	@echo ""
	@echo "🔧 Test Import System:"
	@if [ -L tests/integration/test_imports.py ]; then echo "  ✅ tests/integration/test_imports.py symlink exists"; else echo "  ❌ tests/integration/test_imports.py symlink missing"; fi
	@if [ -L tests/unit/test_imports.py ]; then echo "  ✅ tests/unit/test_imports.py symlink exists"; else echo "  ❌ tests/unit/test_imports.py symlink missing"; fi

# Continuous Integration simulation
ci: clean setup lint test package
	@echo "🎉 CI pipeline complete - ready for deployment!"
