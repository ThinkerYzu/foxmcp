"""
Test import utilities for consistent path setup across all test modules.

This module automatically configures Python paths when imported, ensuring test
modules can import project modules regardless of execution context (pytest,
direct execution, different working directories, etc.).

## Quick Start

Simply import this module at the top of any test file:

```python
import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from test_config import TEST_PORTS
```

## How It Works

1. **Automatic Discovery**: Finds project root by locating 'server' package
2. **Path Configuration**: Adds project root and tests directory to sys.path
3. **Symbolic Links**: Available in subdirectories via symlinks for direct import
4. **Zero Configuration**: No manual path manipulation needed

## Directory Structure

```
foxmcp/
├── server/           # Project modules (automatically detected)
├── tests/
│   ├── test_imports.py     # This file (main)
│   ├── integration/
│   │   └── test_imports.py # Symlink -> ../test_imports.py
│   └── unit/
│       └── test_imports.py # Symlink -> ../test_imports.py
```

## Symbolic Links Setup

Symbolic links enable direct imports from subdirectories:

```bash
cd tests
ln -sf ../test_imports.py integration/test_imports.py
ln -sf ../test_imports.py unit/test_imports.py
```

## Troubleshooting

- **Import Errors**: Ensure symbolic links exist in subdirectories
- **Wrong PROJECT_ROOT**: Check that 'server' directory exists at project root
- **Missing Standard Imports**: Add explicit imports (os, time, etc.) to test files

"""

import sys
import os
from pathlib import Path
from typing import Optional


class TestImportError(Exception):
    """Raised when test import setup fails."""
    pass


def _find_project_root(start_path: Optional[Path] = None) -> Path:
    """
    Find the project root directory by looking for the 'server' package.

    Args:
        start_path: Starting path for search (defaults to this file's location)

    Returns:
        Path: The project root directory

    Raises:
        TestImportError: If project root cannot be found
    """
    if start_path is None:
        start_path = Path(__file__).resolve().parent

    # Walk up the directory tree looking for 'server' directory
    for parent in [start_path] + list(start_path.parents):
        server_dir = parent / 'server'
        if server_dir.is_dir() and (server_dir / '__init__.py').exists():
            return parent

    # Fallback heuristic: tests directory is typically one level down from root
    fallback = start_path.parent if start_path.name == 'tests' else start_path.parent.parent
    if fallback.exists():
        return fallback

    raise TestImportError(
        f"Could not find project root (looking for 'server' package). "
        f"Started search from: {start_path}"
    )


def _setup_python_paths(project_root: Path) -> None:
    """
    Configure sys.path with project root and tests directory.

    Args:
        project_root: The project root directory
    """
    paths_to_add = [
        str(project_root),              # For server modules
        str(project_root / 'tests'),    # For test utilities
    ]

    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)


def _setup_project_paths() -> Path:
    """
    Main setup function that configures all paths for test imports.

    Returns:
        Path: The detected project root directory

    Raises:
        TestImportError: If setup fails
    """
    try:
        project_root = _find_project_root()
        _setup_python_paths(project_root)
        return project_root
    except Exception as e:
        raise TestImportError(f"Failed to setup test import paths: {e}") from e


def get_project_root() -> Path:
    """
    Get the project root directory.

    Returns:
        Path: The project root directory
    """
    return PROJECT_ROOT


def get_tests_dir() -> Path:
    """
    Get the tests directory.

    Returns:
        Path: The tests directory
    """
    return PROJECT_ROOT / 'tests'


def verify_imports() -> bool:
    """
    Verify that the import system is working correctly.

    Returns:
        bool: True if all imports are working, False otherwise
    """
    try:
        # Test basic path setup
        assert PROJECT_ROOT.exists(), f"Project root does not exist: {PROJECT_ROOT}"
        assert (PROJECT_ROOT / 'server').exists(), f"Server directory not found: {PROJECT_ROOT / 'server'}"
        assert get_tests_dir().exists(), f"Tests directory not found: {get_tests_dir()}"

        # Test that paths are in sys.path
        project_str = str(PROJECT_ROOT)
        tests_str = str(get_tests_dir())
        assert project_str in sys.path, f"Project root not in sys.path: {project_str}"
        assert tests_str in sys.path, f"Tests directory not in sys.path: {tests_str}"

        return True
    except (AssertionError, Exception):
        return False


def debug_info() -> dict:
    """
    Get debug information about the import system.

    Returns:
        dict: Debug information including paths, symbolic links, etc.
    """
    info = {
        'project_root': str(PROJECT_ROOT),
        'tests_dir': str(get_tests_dir()),
        'current_file': str(Path(__file__).resolve()),
        'sys_path_entries': [p for p in sys.path if 'foxmcp' in p],
        'symbolic_links': {},
        'verification_passed': verify_imports(),
    }

    # Check symbolic links
    tests_dir = get_tests_dir()
    for subdir in ['integration', 'unit']:
        link_path = tests_dir / subdir / 'test_imports.py'
        if link_path.exists():
            if link_path.is_symlink():
                info['symbolic_links'][subdir] = str(os.readlink(link_path))
            else:
                info['symbolic_links'][subdir] = 'exists_but_not_symlink'
        else:
            info['symbolic_links'][subdir] = 'missing'

    return info


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# Automatically set up paths when this module is imported
try:
    PROJECT_ROOT = _setup_project_paths()
except TestImportError as e:
    # Print error but don't crash - let tests handle the failure gracefully
    print(f"Warning: Test import setup failed: {e}", file=sys.stderr)
    PROJECT_ROOT = Path.cwd()


# =============================================================================
# DEPRECATED CODE (kept for backwards compatibility)
# =============================================================================

def setup_test_imports():
    """
    Legacy function for manual path setup.

    Note: This is deprecated. Path setup now happens automatically on import.

    Returns:
        Path: The project root directory
    """
    return PROJECT_ROOT


# Legacy bootstrap code (no longer needed with symbolic links)
BOOTSTRAP_CODE = '''
# DEPRECATED: This bootstrap code is no longer needed with symbolic links.
# Simply use: import test_imports
import sys
from pathlib import Path
_test_dir = Path(__file__).resolve().parent
while _test_dir.name != 'tests' and _test_dir.parent != _test_dir:
    _test_dir = _test_dir.parent
sys.path.insert(0, str(_test_dir.parent))
sys.path.insert(0, str(_test_dir))
'''


if __name__ == '__main__':
    # CLI interface for debugging
    import json
    print("Test Import System Debug Information")
    print("=" * 40)
    print(json.dumps(debug_info(), indent=2))

    if verify_imports():
        print("\n✅ Import system is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ Import system verification failed!")
        sys.exit(1)