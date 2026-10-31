"""Windows acceptance tests run explicitly in native Windows CI jobs."""

import os
import shutil
import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def native_windows():
    assert sys.platform == "win32", "Run tests/windows on a native Windows runner"
    shell = os.environ.get("FOXMCP_TEST_POWERSHELL", "powershell")
    assert shutil.which(shell), f"Missing required PowerShell: {shell}"
