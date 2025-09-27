#!/usr/bin/env python3
"""
Verification script for the new test import system using symbolic links.
Run this to verify that all imports are working correctly.
"""

import sys
import os
import subprocess
import re
from pathlib import Path

def test_basic_imports():
    """Test that basic imports work from current directory."""
    print("1. Testing basic imports...")

    try:
        import test_imports
        print("   ✓ test_imports imported")
    except ImportError as e:
        print(f"   ❌ test_imports failed: {e}")
        return False

    try:
        from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
        print("   ✓ test_config imported")
    except ImportError as e:
        print(f"   ❌ test_config failed: {e}")
        return False

    try:
        from firefox_test_utils import FirefoxTestManager
        print("   ✓ firefox_test_utils imported")
    except ImportError as e:
        print(f"   ❌ firefox_test_utils failed: {e}")
        return False

    return True

def test_symbolic_links():
    """Test that symbolic links exist and point to the right place."""
    print("\n2. Testing symbolic links...")

    current_dir = Path(__file__).parent
    links_to_check = [
        ('integration/test_imports.py', '../test_imports.py'),
        ('unit/test_imports.py', '../test_imports.py')
    ]

    all_good = True
    for link_path, expected_target in links_to_check:
        full_path = current_dir / link_path
        if full_path.is_symlink():
            actual_target = os.readlink(full_path)
            if actual_target == expected_target:
                print(f"   ✓ {link_path} -> {actual_target}")
            else:
                print(f"   ❌ {link_path} -> {actual_target} (expected {expected_target})")
                all_good = False
        else:
            print(f"   ❌ {link_path} missing or not a symlink")
            all_good = False

    return all_good

def test_project_root_detection():
    """Test that PROJECT_ROOT is detected correctly."""
    print("\n3. Testing PROJECT_ROOT detection...")

    import test_imports
    project_root = test_imports.PROJECT_ROOT

    if str(project_root).endswith('foxmcp'):
        print(f"   ✓ PROJECT_ROOT: {project_root}")
        return True
    else:
        print(f"   ❌ PROJECT_ROOT incorrect: {project_root}")
        return False

def test_subdirectory_imports():
    """Test imports from subdirectories."""
    print("\n4. Testing subdirectory imports...")

    import subprocess
    current_dir = Path(__file__).parent

    test_script = '''
import test_imports
from test_config import TEST_PORTS
print("OK")
'''

    subdirs = ['integration', 'unit']
    all_good = True

    for subdir in subdirs:
        subdir_path = current_dir / subdir
        if subdir_path.exists():
            try:
                result = subprocess.run(
                    [sys.executable, '-c', test_script],
                    cwd=subdir_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0 and 'OK' in result.stdout:
                    print(f"   ✓ {subdir}/ directory imports work")
                else:
                    print(f"   ❌ {subdir}/ directory failed: {result.stderr.strip()}")
                    all_good = False
            except Exception as e:
                print(f"   ❌ {subdir}/ directory error: {e}")
                all_good = False
        else:
            print(f"   - {subdir}/ directory not found")

    return all_good

def main():
    """Run all verification tests."""
    print("=== Test Import System Verification ===")

    tests = [
        test_basic_imports,
        test_symbolic_links,
        test_project_root_detection,
        test_subdirectory_imports
    ]

    results = []
    for test_func in tests:
        results.append(test_func())

    print("\n=== Summary ===")
    if all(results):
        print("✅ All tests passed! Import system is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())