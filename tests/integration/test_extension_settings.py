"""Execute real settings scripts and HTML in Firefox with controlled failures."""

import json
from pathlib import Path

import pytest

from test_file_loading import browser_request, open_fixture, upload_page  # noqa: F401


@pytest.mark.asyncio
async def test_extension_settings_and_reconnect(server_with_extension, upload_page):
    server = server_with_extension['server']
    tab_id = await open_fixture(server, upload_page)
    root = Path(__file__).resolve().parents[2]
    sources = {name: (root / 'extension' / path).read_text(encoding='utf-8')
               for name, path in {
                   'config': 'config.js', 'settings': 'settings.js',
                   'background': 'background.js', 'popup': 'popup/popup.js',
                   'options': 'options.js', 'popupHtml': 'popup/popup.html',
                   'optionsHtml': 'options.html',
               }.items()}
    checks = (root / 'tests/extension_settings_checks.js').read_text(encoding='utf-8')
    script = checks + '(' + json.dumps(sources) + ')'
    try:
        result = await browser_request(server, 'content.execute_script',
                                       {'tabId': tab_id, 'script': script})
        assert len(result['result']) >= 190, result
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})
