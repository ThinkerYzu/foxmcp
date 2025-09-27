#!/usr/bin/env python3
"""
Script to update test files to use the new test_imports utility
instead of try/except import patterns.
"""

import os
import re
import sys
from pathlib import Path

def update_test_file(file_path):
    """Update a single test file to use the new import pattern."""
    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content

    # Pattern 1: Remove manual sys.path manipulations
    # Remove lines like: sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    content = re.sub(r'^sys\.path\.insert\(0,\s*os\.path\.join\([^)]+\)\).*\n', '', content, flags=re.MULTILINE)

    # Pattern 2: Replace try/except import blocks
    # Look for try/except import patterns
    try_except_pattern = r'try:\s*\n((?:\s*from\s+\.\..*import.*\n)+)except ImportError:\s*\n((?:\s*from\s+.*import.*\n)+)'

    def replace_imports(match):
        relative_imports = match.group(1).strip()
        fallback_imports = match.group(2).strip()

        # Extract the actual imports from the fallback (non-relative) imports
        import_lines = []
        for line in fallback_imports.split('\n'):
            line = line.strip()
            if line.startswith('from ') and ' import ' in line:
                import_lines.append(line)

        return '\n'.join(import_lines)

    content = re.sub(try_except_pattern, replace_imports, content, flags=re.MULTILINE | re.DOTALL)

    # Pattern 3: Add the new import setup if not already present
    if 'from test_imports import setup_project_paths' not in content:
        # Find where to insert the import setup
        # Look for the first import statement that's not a standard library import
        import_pattern = r'^(import (?:pytest|asyncio|json|os|sys|time|tempfile|shutil|subprocess|sqlite3|atexit|tarfile|re)\n|from (?:datetime|dataclasses|pathlib|unittest) import.*\n)+'

        match = re.search(import_pattern, content, flags=re.MULTILINE)
        if match:
            insert_pos = match.end()
            setup_code = """
# Set up consistent imports
from test_imports import setup_project_paths
setup_project_paths()

"""
            content = content[:insert_pos] + setup_code + content[insert_pos:]

    # Only write if content changed
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    """Update all test files."""
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / 'tests'

    if not tests_dir.exists():
        print("Tests directory not found!")
        return 1

    updated_files = []

    # Find all Python test files
    for py_file in tests_dir.rglob('*.py'):
        if py_file.name in ['__init__.py', 'test_imports.py']:
            continue

        print(f"Processing {py_file.relative_to(project_root)}...")

        if update_test_file(py_file):
            updated_files.append(py_file.relative_to(project_root))
            print(f"  ✓ Updated")
        else:
            print(f"  - No changes needed")

    if updated_files:
        print(f"\nUpdated {len(updated_files)} files:")
        for file in updated_files:
            print(f"  - {file}")
    else:
        print("\nNo files needed updating.")

    print("\nIMPORTANT: Please review the changes and test that imports still work correctly.")
    return 0

if __name__ == '__main__':
    sys.exit(main())