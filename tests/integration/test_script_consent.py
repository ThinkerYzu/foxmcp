"""Exercise actual consent-controller JavaScript in Firefox with controlled APIs."""

import json
from pathlib import Path

import pytest

from test_file_loading import browser_request, open_fixture, upload_page  # noqa: F401


@pytest.mark.asyncio
async def test_script_consent_state_machine(server_with_extension, upload_page):
    server = server_with_extension['server']
    tab_id = await open_fixture(server, upload_page)
    root = Path(__file__).resolve().parents[2]
    background = (root / 'extension/background.js').read_text()
    start = background.index('class ScriptConsentGate {')
    end = background.index('async function loadConfig()', start)
    source = background[start:end]
    checks = (root / 'tests/extension_script_consent_checks.js').read_text()
    try:
        result = await browser_request(server, 'content.execute_script',
                                       {'tabId': tab_id, 'script': checks + '(' + json.dumps(source) + ')'})
        assert len(result['result']) >= 29, result
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})


@pytest.mark.asyncio
async def test_injected_script_cannot_change_consent_policy(server_with_extension, upload_page):
    server = server_with_extension['server']
    tab_id = await open_fixture(server, upload_page)
    script = r'''(async () => {
      const results = [];
      for (const request of [
        {action:'queueConfigUpdate', group:'scriptConsent', config:{scriptConsent:true}},
        {action:'resetConfig'},
        {action:'decideScriptConsent', token:'1', allowed:true}
      ]) {
        try { await browser.runtime.sendMessage(request); results.push('BYPASS'); }
        catch(error) { results.push(error.message); }
      }
      // Content scripts have storage permission. This key must not be authoritative.
      await browser.storage.sync.set({scriptConsent:true});
      await new Promise(resolve => setTimeout(resolve, 100));
      const status = await browser.runtime.sendMessage({action:'getConnectionStatus'});
      await browser.storage.sync.remove('scriptConsent');
      return {results, enabled:status.scriptConsent.enabled};
    })()'''
    try:
        result = (await browser_request(server, 'content.execute_script',
                                        {'tabId': tab_id, 'script': script}))['result']
        assert not result['enabled']
        assert len(result['results']) == 3
        assert all('only available in the FoxMCP extension UI' in value for value in result['results'])
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})
