"""
The tab context menu item that shows and copies a tab's ID

The item lives entirely in the extension and talks to no server, so the
manifest is the only part of it a unit test can reach.
"""

import json
from pathlib import Path

import pytest

EXTENSION_DIR = Path(__file__).resolve().parents[2] / "extension"


@pytest.mark.parametrize("permission, api_call", [
    ("menus", "browser.menus.create("),
    ("clipboardWrite", "navigator.clipboard.writeText("),
])
def test_manifest_declares_the_permission_each_menu_call_needs(permission, api_call):
    """Without clipboardWrite the copy fails only in the background page's
    console, since a menu click does not count as a user action there, so a
    manifest that loses it still passes every other test"""
    background_source = (EXTENSION_DIR / "background.js").read_text()
    manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text())

    assert api_call in background_source
    assert permission in manifest["permissions"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
