"""Runs the Node check of loadDiscardedTab and sendMessageWithRetry"""

import shutil
import subprocess
from pathlib import Path


def test_discarded_tabs_are_loaded_once_before_the_retries():
    node = shutil.which("node")
    assert node, "Node.js is required for the extension checks"
    script = Path(__file__).resolve().parents[1] / "extension_discarded_tab_checks.js"

    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok 4"
