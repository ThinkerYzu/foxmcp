#!/usr/bin/env python3
"""
Script to update test files to use the new symbolic link import pattern.
Removes try/except import blocks and bootstrap code, replacing with simple imports.
"""

import os
import re
import sys
from pathlib import Path

def update_test_file(file_path):
    """Update a single test file to use the simple import pattern."""
    with open(file_path, 'r') as f:
        content = f.read()

    original_content = content

    # Pattern 1: Remove manual sys.path manipulations
    content = re.sub(r'^sys\.path\.insert\(0,\s*[^)]+\).*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^# Add.*parent.*path.*\n', '', content, flags=re.MULTILINE)

    # Pattern 2: Remove bootstrap code blocks
    bootstrap_pattern = r'# Bootstrap path setup.*?\n(.*?)\n# Now we can import test utilities\n'
    content = re.sub(bootstrap_pattern, '# Set up consistent imports\n', content, flags=re.MULTILINE | re.DOTALL)

    # Pattern 3: Replace try/except import blocks
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

    # Pattern 4: Ensure test_imports is imported
    if 'import test_imports' not in content:
        # Find where to insert the import setup
        import_pattern = r'^(import (?:pytest|asyncio|json|os|time|tempfile|shutil|subprocess|sqlite3|atexit|tarfile|re)\n|from (?:datetime|dataclasses|pathlib|unittest) import.*\n)+'

        match = re.search(import_pattern, content, flags=re.MULTILINE)
        if match:
            insert_pos = match.end()
            setup_code = "\n# Set up consistent imports\nimport test_imports\n\n"
            content = content[:insert_pos] + setup_code + content[insert_pos:]

    # Only write if content changed
    if content != original_content:
        with open(file_path, 'w') as f:
            f.write(content)
        return True
    return False

def main():
    """Update all test files."""
    script_dir = Path(__file__).parent
    tests_dir = script_dir.parent

    if not tests_dir.exists():
        print("Tests directory not found!")
        return 1

    updated_files = []

    # Find all Python test files
    for py_file in tests_dir.rglob('*.py'):
        if py_file.name in ['__init__.py', 'test_imports.py'] or 'scripts' in str(py_file):
            continue

        rel_path = py_file.relative_to(tests_dir)
        print(f"Processing {rel_path}...")

        if update_test_file(py_file):
            updated_files.append(rel_path)
            print(f"  ✓ Updated")
        else:
            print(f"  - No changes needed")

    if updated_files:
        print(f"\nUpdated {len(updated_files)} files:")
        for file in updated_files:
            print(f"  - {file}")
    else:
        print("\nNo files needed updating.")

    print("\nIMPORTANT: Test files now use symbolic links for test_imports.py")
    print("Make sure symbolic links exist in subdirectories:")
    print("  ln -sf ../test_imports.py integration/test_imports.py")
    print("  ln -sf ../test_imports.py unit/test_imports.py")
    return 0

if __name__ == '__main__':
    sys.exit(main())