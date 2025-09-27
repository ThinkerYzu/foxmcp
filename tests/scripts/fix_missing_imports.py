#!/usr/bin/env python3
"""
Script to find and fix missing standard library imports in test files.
This fixes issues where imports were accidentally removed during the migration.
"""

import os
import re
import sys
from pathlib import Path

def check_and_fix_imports(file_path):
    """Check a test file for missing imports and fix them."""

    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content
    changes_made = []

    # Check for usage of common modules that might be missing imports
    modules_to_check = {
        'os': [r'os\.', r'os\s'],
        'sys': [r'sys\.', r'sys\s'],
        'time': [r'time\.', r'time\s'],
        'tempfile': [r'tempfile\.', r'tempfile\s'],
        'shutil': [r'shutil\.', r'shutil\s'],
        'subprocess': [r'subprocess\.', r'subprocess\s'],
        'sqlite3': [r'sqlite3\.', r'sqlite3\s'],
        'atexit': [r'atexit\.', r'atexit\s'],
        'tarfile': [r'tarfile\.', r'tarfile\s'],
        're': [r're\.', r're\s']
    }

    # Find existing imports
    existing_imports = set()
    import_pattern = r'^import\s+(\w+)'
    for match in re.finditer(import_pattern, content, re.MULTILINE):
        existing_imports.add(match.group(1))

    # Check for missing imports
    missing_imports = []
    for module, patterns in modules_to_check.items():
        if module not in existing_imports:
            # Check if module is used in the file
            for pattern in patterns:
                if re.search(pattern, content):
                    missing_imports.append(module)
                    break

    # Add missing imports
    if missing_imports:
        # Find the position to insert imports (after existing imports)
        import_section_pattern = r'^(import\s+\w+\n)+'
        match = re.search(import_section_pattern, content, re.MULTILINE)

        if match:
            insert_pos = match.end()
            new_imports = '\n'.join(f'import {module}' for module in missing_imports)
            content = content[:insert_pos] + new_imports + '\n' + content[insert_pos:]
            changes_made.extend(missing_imports)

    # Only write if content changed
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return changes_made

    return []

def main():
    """Check and fix all test files."""
    script_dir = Path(__file__).parent
    tests_dir = script_dir.parent

    print("Checking for missing imports in test files...")

    total_fixed = 0
    files_fixed = []

    # Check all Python test files
    for py_file in tests_dir.rglob('*.py'):
        if py_file.name in ['__init__.py', 'test_imports.py'] or 'scripts' in str(py_file):
            continue

        rel_path = py_file.relative_to(tests_dir)
        changes = check_and_fix_imports(py_file)

        if changes:
            print(f"✓ {rel_path}: Added imports for {', '.join(changes)}")
            files_fixed.append(rel_path)
            total_fixed += len(changes)
        else:
            print(f"  {rel_path}: No missing imports")

    print(f"\nSummary:")
    print(f"Files checked: {len(list(tests_dir.rglob('*.py'))) - 2}")  # -2 for scripts and __init__
    print(f"Files fixed: {len(files_fixed)}")
    print(f"Total imports added: {total_fixed}")

    if files_fixed:
        print(f"\nFixed files:")
        for file in files_fixed:
            print(f"  - {file}")

    return 0

if __name__ == '__main__':
    sys.exit(main())