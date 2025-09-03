#!/usr/bin/env python3
"""
Test runner script for FoxMCP tests
"""

import sys
import subprocess
import os
from pathlib import Path

def run_tests():
    """Run all tests with coverage"""
    
    # Change to tests directory
    test_dir = Path(__file__).parent
    os.chdir(test_dir)
    
    # Add project root to Python path so we can import server module
    project_root = test_dir.parent
    sys.path.insert(0, str(project_root))
    
    # Run pytest with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=../server",
        "--cov-report=html",
        "--cov-report=term-missing",
        "unit/",
        "integration/"
    ]
    
    # Set PYTHONPATH environment variable
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    try:
        result = subprocess.run(cmd, check=True, env=env)
        print("\n✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Tests failed with exit code: {e.returncode}")
        return e.returncode

def run_unit_tests_only():
    """Run only unit tests"""
    cmd = [sys.executable, "-m", "pytest", "unit/", "-v"]
    return subprocess.run(cmd).returncode

def run_integration_tests_only():
    """Run only integration tests"""
    cmd = [sys.executable, "-m", "pytest", "integration/", "-v"]  
    return subprocess.run(cmd).returncode

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        if test_type == "unit":
            sys.exit(run_unit_tests_only())
        elif test_type == "integration":
            sys.exit(run_integration_tests_only())
        else:
            print("Usage: python run_tests.py [unit|integration]")
            sys.exit(1)
    else:
        sys.exit(run_tests())