#!/bin/bash

# FoxMCP Claude Script
# Sets FM_ROOT environment variable and runs Claude with command line arguments

# Get the directory where this script is located (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Export FM_ROOT for Claude Code to reference
export FM_ROOT="$SCRIPT_DIR"

# Run claude with all command line arguments
exec claude "$@"