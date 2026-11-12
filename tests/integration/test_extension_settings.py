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


@pytest.mark.asyncio
async def test_screenshot_upload_fetch_policy_and_failure(server_with_extension, upload_page):
    """Run the production upload function in Firefox with controlled HTTP outcomes."""
    server = server_with_extension['server']
    tab_id = await open_fixture(server, upload_page)
    source = (Path(__file__).resolve().parents[2] / 'extension/background.js').read_text()
    function = source[source.index('function screenshotUploadUrl('):
                      source.index('// The tab group properties')]
    script = '''(async () => {
      const source = FUNCTION;
      const calls = [];
      let status = 204;
      const capture = new Function('fetch', source + ';return transferScreenshot')(async (url, options) => {
        calls.push({url, credentials:options.credentials, redirect:options.redirect,
                    method:options.method, header:options.headers['X-FoxMCP-Request-Id'],
                    bytes:Array.from(new Uint8Array(await options.body.arrayBuffer())),
                    hasSignal:!!options.signal});
        return {status};
      });
      const grant = {url:'http://127.0.0.1:12345/uploads/' + 'a'.repeat(43), requestId:'stable-id'};
      const result = await capture('data:image/png;base64,AAEC/w==', grant, 'png');
      status = 302;
      let rejected = false;
      try { await capture('data:image/png;base64,AAEC/w==', grant, 'png'); }
      catch (error) { rejected = error.message.includes('HTTP 302'); }
      const invalid = [];
      for (const url of ['https://example.org/uploads/' + 'a'.repeat(43),
                        'http://127.0.0.1:12345/other', grant.url + '?redirect=1']) {
        try { await capture('data:image/png;base64,AAEC/w==', {...grant,url}, 'png'); }
        catch (_) { invalid.push(url); }
      }
      let missing = false;
      try { await capture('data:image/png;base64,AAEC/w==', null, 'png'); }
      catch (error) { missing = error.message.includes('required'); }
      return {result, calls, rejected, invalid:invalid.length, missing};
    })()'''.replace('FUNCTION', json.dumps(function))
    try:
        result = await browser_request(server, 'content.execute_script',
                                       {'tabId': tab_id, 'script': script})
        data = result['result']
        assert data['rejected'] and data['invalid'] == 3 and data['missing']
        assert data['result'] == {'upload': {'requestId': 'stable-id', 'size': 4, 'type': 'image/png'}}
        assert len(data['calls']) == 2
        for call in data['calls']:
            assert call['credentials'] == 'omit'
            assert call['redirect'] == 'error'
            assert call['method'] == 'PUT' and call['header'] == 'stable-id'
            assert call['bytes'] == [0, 1, 2, 255] and call['hasSignal']
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})
