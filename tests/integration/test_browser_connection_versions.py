"""Run actual extension JavaScript in Firefox with controlled sockets and UI."""

import asyncio
import json
from pathlib import Path

import pytest

from server.version import VERSION
from test_file_loading import browser_request, open_fixture, upload_page  # noqa: F401


BACKGROUND_CHECK = r'''
const checks = [];
function check(value, label) { if (!value) throw new Error(label); checks.push(label); }
connectToMCPServer();
const first = websocket;
first.onopen();
check(JSON.parse(first.sent[0]).data.version === EXTENSION_VERSION, 'hello is first message');
await first.onmessage({data: JSON.stringify({type:'hello', data:{version:EXTENSION_VERSION}})});
check(serverVersion === EXTENSION_VERSION, 'matching version');
await first.onmessage({data: JSON.stringify({type:'hello', data:{version:'0.0.1'}})});
check(serverVersion === '0.0.1', 'mismatch retained');
let status;
listeners[0]({action:'getConnectionStatus'}, {}, value => status=value);
check(status.serverVersion === '0.0.1' && status.extensionVersion === EXTENSION_VERSION, 'popup diagnostics');
await first.onmessage({data: JSON.stringify({type:'request', action:'ping', id:'tool'})});
check(JSON.parse(first.sent.at(-1)).action === 'ping', 'mismatch does not block tools');
connectToMCPServer();
const second = websocket;
second.onopen();
check(serverVersion === null, 'legacy server is unknown after reconnect');
await first.onmessage({data: JSON.stringify({type:'hello', data:{version:'9.9.9'}})});
first.onopen();
first.onclose();
check(serverVersion === null && isConnected, 'stale callbacks ignored');
for (const data of [null, [], {}, {version:3}, {version:'bad\nversion'}, {version:EXTENSION_VERSION+'\n'}, {version:'1.'+'0'.repeat(70)}]) {
  await second.onmessage({data:JSON.stringify({type:'hello', data})});
  check(serverVersion === null, 'malformed version ignored');
}
await second.onmessage({data:JSON.stringify({type:'request', action:'ping', id:'legacy'})});
check(JSON.parse(second.sent.at(-1)).id === 'legacy', 'legacy tools work');
await second.onmessage({data:JSON.stringify({type:'hello', data:{version:EXTENSION_VERSION}})});
second.onclose();
check(serverVersion === null && !isConnected, 'close clears version');
return checks;
'''

POPUP_CHECK = r'''
await loaded();
check(elements.versionInfo.textContent.includes('server 0.0.1'), 'both versions visible');
check(elements.versionInfo.textContent.includes('Version mismatch'), 'mismatch visible');
elements.serverUrl.value = 'ws://example.org:9999';
connection = {connected:true, extensionVersion:'1.4.0', serverVersion:'1.4.0', retryAttempts:0};
await refresh();
check(!elements.versionInfo.textContent.includes('mismatch'), 'open popup refreshes');
check(elements.serverUrl.value === 'ws://example.org:9999', 'refresh preserves edits');
connection.serverVersion = null;
await refresh();
check(elements.versionInfo.textContent.includes('version unavailable'), 'unknown peer visible');
connection = {connected:false};
await refresh();
check(elements.versionInfo.textContent.includes('disconnected'), 'disconnected clears old version');
return checks;
'''


@pytest.mark.asyncio
async def test_browser_versions_and_popup(server_with_extension, upload_page):
    server = server_with_extension['server']
    for _ in range(100):
        if server.extension_version:
            break
        await asyncio.sleep(0.01)
    assert server.extension_version == VERSION  # Actual extension hello, not a mock.
    tab_id = await open_fixture(server, upload_page)
    root = Path(__file__).resolve().parents[2]
    background = (root / 'extension/background.js').read_text()
    popup = (root / 'extension/popup/popup.js').read_text()
    script = r'''(async () => {
      const listeners = [];
      const event = {addListener() {}};
      const browser = {
        runtime: {getManifest:()=>({version:'1.4.0'}), onMessage:{addListener:f=>listeners.push(f)}},
        menus: {create(){}, onShown:event, onClicked:event},
        storage: {sync:{get:()=>new Promise(()=>{})}}
      };
      class FakeSocket {
        static CLOSED = 3;
        static OPEN = 1;
        constructor() { this.sent=[]; this.readyState=1; }
        send(raw) {this.sent.push(raw);}
        close() {this.readyState=3;}
      }
      const quiet = {log(){}, error(){}, warn(){}, trace(){}};
      const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
      const backgroundResult = await new AsyncFunction(
        'browser','window','WebSocket','setTimeout','console','listeners',
        BACKGROUND_SOURCE + '\n' + BACKGROUND_TEST
      )(browser, {}, FakeSocket, ()=>0, quiet, listeners);
      const elements = {};
      const doc = {
        addEventListener:(_,f)=>loaded=f,
        getElementById:id=>elements[id] ||= {style:{}, value:'', textContent:'', addEventListener(){}},
        createElement:()=>({style:{}})
      };
      let loaded, refresh;
      let connection = {connected:true, extensionVersion:'1.4.0', serverVersion:'0.0.1', retryAttempts:0};
      browser.runtime.sendMessage = (_,callback)=>callback(connection);
      browser.storage.sync.get = async defaults=>defaults;
      const checks=[];
      const check=(value,label)=>{if(!value)throw new Error(label); checks.push(label);};
      const popupResult = await new AsyncFunction(
        'browser','document','window','setInterval','clearInterval','console','setTimeout','getConnection',
        'runChecks', POPUP_SOURCE + '\nreturn runChecks();'
      )(browser, doc, {addEventListener(){}}, f=>{refresh=f;return 0;}, ()=>{}, quiet, ()=>{},
        ()=>connection, async()=>{POPUP_TEST});
      return {background:backgroundResult, popup:popupResult};
    })()'''
    # Inject complete product files rather than reimplementing their functions.
    script = script.replace('BACKGROUND_SOURCE', json.dumps(background))
    script = script.replace('BACKGROUND_TEST', json.dumps(BACKGROUND_CHECK))
    script = script.replace('POPUP_SOURCE', json.dumps(popup))
    script = script.replace('POPUP_TEST', POPUP_CHECK)
    try:
        result = await browser_request(server, 'content.execute_script', {'tabId': tab_id, 'script': script})
        assert len(result['result']['background']) >= 10, result
        assert len(result['result']['popup']) == 6, result
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})
