// Runs the complete product scripts in Firefox; also runnable with Node for fast feedback.
(async function runSettingsChecks(sources) {
  const checks = [];
  const check = (ok, label) => { if (!ok) throw new Error(label); checks.push(label); };
  const settle = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
  const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
  const quiet = {log() {}, error() {}, warn() {}, trace() {}};

  async function background(initial = {}, options = {}) {
    const stored = {...initial};
    const local = new Map();
    const timers = new Map();
    const sockets = [];
    const writes = [];
    const listeners = [];
    const storageListeners = [];
    let now = 100000, nextTimer = 0;
    let failWrite = false, holdWrite = null;
    let failConnection = false;
    const event = {addListener() {}, removeListener() {}};
    const browser = {
      runtime: {getManifest: () => ({version: '1.5.0'}), getURL: path => 'moz-extension://test/' + path, onMessage: {addListener: f => listeners.push(f)}},
      menus: {create() {}, onShown: event, onClicked: event},
      storage: {
        onChanged: {addListener: f => storageListeners.push(f)},
        sync: {
          async get(defaults) {
            if (options.initialRead) { await options.initialRead; options.initialRead = null; }
            return {...defaults, ...structuredClone(stored)};
          },
          async set(patch) {
            if (holdWrite) { const waiting = holdWrite; holdWrite = null; await waiting; }
            if (failWrite) throw new Error('storage denied');
            const changes = Object.fromEntries(Object.entries(patch).map(([key, value]) => [key, {oldValue: stored[key], newValue: value}]));
            Object.assign(stored, patch);
            writes.push({...patch});
            for (const listener of storageListeners) listener(changes, 'sync');
          }
        }
      }
    };
    class FakeDate extends Date { static now() { return now; } }
    class Socket {
      static CONNECTING = 0; static OPEN = 1; static CLOSED = 3;
      constructor(url) {
        if (failConnection) throw new Error('constructor failure');
        this.url = url; this.sent = []; this.readyState = Socket.CONNECTING;
        sockets.push(this);
      }
      send(message) { this.sent.push(JSON.parse(message)); }
      open(ready = true) {
        this.readyState = Socket.OPEN;
        this.onopen();
        if (ready) {
          const hello = this.sent.at(-1).data;
          this.onmessage({data: JSON.stringify({type: 'hello', data: {
            version: hello.version, protocol_version: hello.protocol_version}})});
          this.onmessage({data: JSON.stringify({type: 'ready', data: {}})});
        }
      }
      close(code = 1000, reason = '') {
        this.readyState = Socket.CLOSED;
        if (this.onclose) this.onclose({code, reason});
      }
    }
    const setTimeout = (callback, delay) => { const id = ++nextTimer; timers.set(id, {callback, delay, due: now + delay}); return id; };
    const clearTimeout = id => timers.delete(id);
    const api = await new AsyncFunction('browser', 'window', 'WebSocket', 'setTimeout', 'clearTimeout', 'Date', 'console',
      sources.config + '\n' + sources.background + `\nreturn {
        status: getConnectionStatus, queue: queueConfigUpdate, reset: resetConfig,
        idle: () => configurationQueue, monitors: activeMonitors,
        get socket() { return websocket; }
      };`)(browser, {localStorage: {getItem: key => local.get(key), setItem: (key,value) => local.set(key,value)}}, Socket, setTimeout, clearTimeout, FakeDate, quiet);
    async function tick(ms) {
      const target = now + ms;
      while (true) {
        const next = [...timers].filter(([, timer]) => timer.due <= target).sort((a, b) => a[1].due - b[1].due)[0];
        if (!next) break;
        now = next[1].due; timers.delete(next[0]); next[1].callback(); await settle();
      }
      now = target; await settle();
    }
    async function message(request, sender = {url: 'moz-extension://test/popup/popup.html'}) {
      return new Promise((resolve, reject) => {
        try {
          const result = listeners[0](request, sender, resolve);
          if (result && result.then) result.then(resolve, reject);
        } catch (error) { reject(error); }
      });
    }
    if (!options.initialRead) await settle();
    return {api, timers, sockets, writes, stored, tick, message, browser,
      failWrites: value => { failWrite = value; }, failConnections: value => { failConnection = value; },
      holdNextWrite: promise => { holdWrite = promise; }};
  }

  const config = new Function(sources.config + '\nreturn FoxMCPConfig;')();
  for (const [input, valid] of [['localhost', true], ['example.org', true], ['127.0.0.1', true], ['::1', true],
    ['[2001:db8::1]', true], ['', false], ['ws://localhost', false], ['wss://localhost', false],
    ['localhost/path', false], ['localhost:8765', false], ['user@localhost', false], ['host?x=y', false],
    ['host#x', false], ['local host', false], ['[::1]:8765', false]]) {
    let accepted = true;
    try { config.group('endpoint', {hostname: input, port: '8765'}); } catch (_) { accepted = false; }
    check(accepted === valid, 'host validation: ' + input);
  }
  for (const [group, field, min, max] of [['endpoint', 'port', 1, 65535], ['retryInterval', 'retryInterval', 100, 30000]]) {
    for (const value of ['', '1.5', '1e3', '1000x', NaN, Infinity, null, true, min - 1, max + 1]) {
      let accepted = true;
      try { config.group(group, {hostname: 'localhost', [field]: value}); } catch (_) { accepted = false; }
      check(!accepted, 'numeric rejection: ' + field + ' ' + value);
    }
    for (const value of [min, max, String(min)]) check(config.group(group, {hostname: 'localhost', [field]: value})[field] === Number(value), 'numeric boundary');
  }
  check(config.socketUrl(config.effective({hostname: '::1', port: 8765})) === 'ws://[::1]:8765', 'IPv6 socket address');

  const diagnosticApp = await background();
  diagnosticApp.api.socket.open();
  await diagnosticApp.api.socket.onmessage({data:JSON.stringify({type:'request',id:'legacy-popup',action:'test.get_popup_state',data:{}})});
  const legacyPopupState = diagnosticApp.api.socket.sent.find(message=>message.id==='legacy-popup');
  check(!Object.hasOwn(legacyPopupState.data,'consentDiagnostics'), 'legacy popup projection keeps its default fields');
  await diagnosticApp.api.socket.onmessage({data:JSON.stringify({type:'request',id:'diagnostic-popup',action:'test.get_popup_state',data:{includeConsentDiagnostics:true}})});
  const popupDiagnostics = diagnosticApp.api.socket.sent.find(message=>message.id==='diagnostic-popup');
  check(popupDiagnostics.data.consentDiagnostics.implementation === 'visibility-recovery-2026-10-31' &&
    !popupDiagnostics.data.consentDiagnostics.pending, 'opt-in diagnostics identify running consent implementation without a pending prompt');

  const registration = await background();
  const registering = registration.api.socket;
  registering.open(false);
  check(!registration.api.status().connected && registration.api.status().state === 'connecting', 'transport open waits for profile registration');
  const announced = registering.sent[0].data;
  check(announced.protocol_version === 3 && !Object.hasOwn(announced, 'profile_id') && !Object.hasOwn(registration.api.status(), 'profileId'), 'extension has no routing identity');
  await registering.onmessage({data: JSON.stringify({type: 'request', action: 'ping', id: 'early'})});
  check(registering.sent.length === 1, 'browser requests ignored before profile registration');
  await registering.onmessage({data: JSON.stringify({type: 'ready'})});
  check(!registration.api.status().connected, 'malformed acknowledgement ignored');
  await registering.onmessage({data: JSON.stringify({type: 'hello', data: {version: '1.5.0', protocol_version: 3}})});
  await registering.onmessage({data: JSON.stringify({type: 'ready', data: {}})});
  check(registration.api.status().connected && registration.api.status().state === 'connected', 'registration sets connected state');
  registering.close();
  await registration.tick(1000);
  registration.api.socket.open();
  check(!Object.hasOwn(registration.api.status(), 'profileId') && registration.api.status().connected, 'reconnect needs no routing identity');
  const rejected = await background();
  rejected.api.socket.open(false);
  await rejected.api.socket.onmessage({data: JSON.stringify({type: 'hello', data: {version: '1.5.0', protocol_version: 2}})});
  check(rejected.api.socket === null && rejected.api.status().state === 'protocol_error', 'incompatible handshake closes socket and reports protocol error');
  check(rejected.timers.size === 0 && rejected.api.status().connectionError.includes('update'), 'incompatible peer does not loop retries');

  check(config.defaults.retryInterval === 1000, 'default reconnect interval is 1000ms');
  const migrated = await background({retryInterval: 60000});
  check(migrated.stored.retryInterval === 30000 && migrated.api.status().config.retryInterval === 30000 && migrated.sockets.length === 1, 'legacy interval is migrated without preventing connection');
  const life = await background({retryInterval: 5000, maxRetries: 0, pingTimeout: 1});
  check(life.sockets.length === 1, 'startup connects once with existing settings');
  life.api.socket.open();
  check(life.api.socket.sent[0].type === 'hello', 'version hello retained');
  for (let i = 0; i < 55; i++) {
    life.api.socket.close();
    check(life.timers.size === 1 && [...life.timers.values()][0].delay === 5000, 'constant retry delay ' + i);
    await life.tick(4999);
    check(life.api.socket === null, 'no early retry ' + i);
    await life.tick(1);
  }
  check(life.sockets.length === 56, 'legacy retry limit ignored beyond fifty attempts');
  life.api.socket.open(); life.api.socket.close();
  const obsoleteReconnect = [...life.timers.values()][0].callback;
  life.api.queue('endpoint', {hostname: '127.0.0.1', port: '9999'});
  await life.tick(500);
  life.api.socket.open();
  const healthy = life.api.socket;
  life.api.monitors.set('new-monitor', {});
  obsoleteReconnect();
  check(life.api.socket === healthy && healthy.readyState === 1 && life.api.monitors.has('new-monitor'), 'obsolete timer preserves new socket and monitors');
  life.api.queue('retryInterval', {retryInterval: '2000'});
  await life.tick(500);
  check(life.api.socket === healthy && life.api.monitors.size === 1, 'interval edit preserves healthy socket and monitors');
  healthy.close();
  check(life.api.monitors.size === 0, 'actual disconnect clears monitors');
  const oldDelay = [...life.timers.values()][0].callback;
  life.api.queue('retryInterval', {retryInterval: '3000'});
  await life.tick(500);
  check(life.api.status().retryDelayMs === 3000, 'waiting retry uses new interval');
  oldDelay();
  check(life.api.socket === null, 'obsolete rescheduled retry ignored');
  await life.tick(2999); check(life.api.socket === null, 'rescheduled timer starts at application');
  await life.tick(1); check(life.api.socket !== null, 'rescheduled retry executes');
  const socketCount = life.sockets.length;
  await life.browser.storage.sync.set({retryInterval: 3000}); await settle();
  check(life.sockets.length === socketCount, 'unchanged storage event does not reconnect');
  life.api.socket.close(); life.failConnections(true); await life.tick(3000);
  check(life.api.status().state === 'waiting_retry' && life.timers.size === 1, 'constructor failure keeps retrying');

  const saves = await background({testHostname: 'localhost', testPort: 31000, unrelated: 'keep'});
  saves.api.socket.open();
  const initialSocket = saves.api.socket;
  saves.api.queue('endpoint', {hostname: 'example.org', port: '9000'});
  const obsoleteSave = [...saves.timers.values()][0].callback;
  await saves.tick(300);
  saves.api.queue('endpoint', {hostname: 'example.org', port: ''});
  obsoleteSave(); await saves.tick(500);
  check(saves.writes.length === 0 && saves.api.status().settings.groups.endpoint.state === 'error', 'invalid draft cancels prior endpoint save');
  saves.api.queue('retryInterval', {retryInterval: '2500'}); await saves.tick(500);
  check(saves.stored.retryInterval === 2500 && saves.stored.hostname === undefined, 'valid interval independent of invalid endpoint');
  saves.api.queue('endpoint', {hostname: 'example.org', port: '9000'});
  await saves.tick(499); check(saves.stored.hostname === undefined, 'debounce waits 500ms');
  await saves.tick(1);
  check(saves.stored.hostname === 'example.org' && saves.stored.port === 9000, 'endpoint pair persists together');
  check(saves.api.status().config.port === 31000 && saves.api.status().configuredConfig.port === 9000, 'saved settings separate from effective overrides');
  check(saves.api.socket === initialSocket, 'overridden endpoint edit does not replace active socket');
  saves.failWrites(true);
  saves.api.queue('retryInterval', {retryInterval: '4000'}); await saves.tick(500);
  check(saves.stored.retryInterval === 2500 && saves.api.status().config.retryInterval === 2500, 'write error preserves active settings');
  check(saves.api.status().settings.groups.retryInterval.state === 'error', 'write error never reports saved');
  await saves.api.reset();
  check(saves.api.status().settings.groups.endpoint.state === 'error' && saves.stored.port === 9000, 'reset failure preserves prior configuration');
  saves.failWrites(false);
  saves.api.queue('endpoint', {hostname: 'other.example.org', port: 9999});
  const staleSave = [...saves.timers.values()][0].callback;
  await saves.api.reset(); staleSave(); await saves.tick(500);
  check(saves.stored.hostname === 'localhost' && saves.stored.port === 8765 && saves.stored.retryInterval === 1000, 'reset persists defaults and cancels debounce');
  check(saves.stored.testPort === 31000 && saves.stored.unrelated === 'keep', 'reset preserves overrides and unrelated keys');
  let release;
  saves.holdNextWrite(new Promise(resolve => { release = resolve; }));
  saves.api.queue('endpoint', {hostname: 'example.org', port: 9999}); await saves.tick(500);
  const resetting = saves.api.reset(); release(); await resetting; await settle();
  check(saves.stored.hostname === 'localhost' && saves.stored.port === 8765, 'reset wins over in-flight write');
  await saves.browser.storage.sync.set({testPort: 32000}); await settle();
  check(saves.api.status().config.port === 32000 && saves.api.socket.url === 'ws://localhost:32000', 'external storage change updates actual endpoint');

  let releaseRead;
  const startup = await background({}, {initialRead: new Promise(resolve => { releaseRead = resolve; })});
  startup.api.queue('endpoint', {hostname: '127.0.0.1', port: 9999}); await startup.tick(500);
  check(startup.sockets.length === 0, 'no connection before startup read completes');
  releaseRead(); await settle();
  check(startup.api.status().configuredConfig.port === 9999 && startup.api.socket.url === 'ws://127.0.0.1:9999', 'delayed initialization cannot overwrite queued save');
  const invalid = await background({hostname: 'ws://localhost', port: 8765});
  check(invalid.sockets.length === 0 && invalid.api.status().state === 'configuration_error', 'invalid stored config never connects to fallback');
  invalid.api.queue('endpoint', {hostname: 'localhost', port: 9000}); await invalid.tick(500);
  check(invalid.api.socket.url === 'ws://localhost:9000', 'correcting stored config recovers automatically');

  async function view(name, app) {
    const html = sources[name + 'Html'];
    const loaded = [], refresh = [], unloaded = [];
    let rejectMessages = false, closed = false;
    const elements = {};
    const realDoc = typeof document === 'undefined' ? null : document.implementation.createHTMLDocument('settings test');
    if (realDoc) realDoc.documentElement.innerHTML = html;
    for (const match of html.matchAll(/id="([^"]+)"/g)) {
      const listeners = {};
      elements[match[1]] = realDoc ? realDoc.getElementById(match[1]) : {
        value: '', textContent: '', style: {}, dataset: {}, className: '',
        addEventListener(type, fn) { listeners[type] = fn; },
        dispatchEvent(event) { if (listeners[event.type]) listeners[event.type](event); }
      };
    }
    const doc = {getElementById: id => elements[id] || null, addEventListener: (_, callback) => { loaded.push(callback); }};
    const browser = {runtime: {getManifest: () => ({version: '1.5.0'}), sendMessage: request => rejectMessages ? Promise.reject(new Error('background unavailable')) : app.message(request, {url: 'moz-extension://test/' + (name === 'popup' ? 'popup/popup.html' : 'options.html'), ...(name === 'options' ? {tab:{id:8}} : {})})}};
    await new AsyncFunction('browser', 'document', 'window', 'setInterval', 'clearInterval', 'console',
      sources.config + '\n' + sources.settings + '\n' + sources[name])(
        browser, doc, {close: () => { closed = true; for (const callback of unloaded) callback(); }, confirm: () => { throw new Error('Native confirmation dialogs must not be used in extension settings'); }, addEventListener: (_, callback) => { unloaded.push(callback); }},
        callback => { refresh.push(callback); return refresh.length; }, () => {}, quiet);
    for (const callback of loaded) await callback();
    await settle();
    async function input(id, value) {
      elements[id].value = value;
      elements[id].dispatchEvent(new Event('input')); await settle();
    }
    return {elements, input, get closed() { return closed; }, refresh: async () => { for (const callback of refresh) await callback(); }, close: () => { for (const callback of unloaded) callback(); },
      click: async id => { elements[id].dispatchEvent(new Event('click')); await settle(); },
      unavailable: () => { rejectMessages = true; }};
  }
  for (const name of ['popup', 'options']) {
    const app = await background({hostname: 'example.org', port: 9999, testHostname: 'localhost', testPort: 31000});
    app.api.socket.open();
    await app.api.socket.onmessage({data: JSON.stringify({type: 'hello', data: {version: '0.0.1', protocol_version: 3}})});
    const page = await view(name, app);
    check(page.elements.hostname.value === 'example.org' && Number(page.elements.port.value) === 9999, name + ' displays user configuration');
    check(!page.elements.scriptConsent.checked, name + ' consent defaults off');
    if (name === 'popup') check(!page.elements.settingsPanel.hidden, 'normal toolbar popup shows settings');
    page.elements.scriptConsent.checked = true;
    page.elements.scriptConsent.dispatchEvent(new Event('change'));
    await settle(); await app.tick(500); await page.refresh();
    check(page.elements.scriptConsent.checked && app.api.status().scriptConsent.enabled, name + ' consent toggle enables gate');
    page.elements.scriptConsent.checked = false;
    page.elements.scriptConsent.dispatchEvent(new Event('change'));
    await settle(); await app.tick(500); await page.refresh();
    check(!app.api.status().scriptConsent.enabled, name + ' consent toggle disables gate');
    check(page.elements.serverInfo.textContent.includes('localhost:31000') && page.elements.serverInfo.textContent.includes('overrides'), name + ' shows actual endpoint and overrides');
    check(!page.elements.serverUrl && !page.elements.maxRetries && !page.elements.pingTimeout && !page.elements.saveConfig && !page.elements.forceReconnect, name + ' removes obsolete controls');
    check(page.elements.versionInfo.textContent.includes('Version mismatch'), name + ' version warning retained');
    check(page.elements.versionInfo.textContent.includes('Protocol 3'), name + ' supported protocol version visible in footer');
    await page.input('port', '1234');
    await page.refresh();
    check(Number(page.elements.port.value) === 1234, name + ' polling preserves draft');
    check(page.elements.saveStatus.dataset.state === 'pending', name + ' reports pending save');
    await app.tick(500); await page.refresh();
    check(app.stored.port === 1234 && page.elements.saveStatus.dataset.state === 'saved', name + ' automatically saves valid input');
    await page.input('port', ''); await page.refresh();
    check(page.elements.port.value === '' && page.elements.saveStatus.dataset.state === 'error', name + ' preserves invalid draft and displays error');
    await page.input('retryInterval', '2000'); await app.tick(500); await page.refresh();
    check(app.stored.retryInterval === 2000 && app.stored.port === 1234, name + ' independent valid group still saves');
    app.api.socket.close(); await page.refresh();
    const text = page.elements[name === 'popup' ? 'status' : 'connectionText'].textContent;
    check(text.includes('Retry') && text.includes('2000ms'), name + ' live status shows actual retry interval');
    check(page.elements.versionInfo.textContent.includes('Protocol 3'), name + ' supported protocol remains visible while disconnected');
    {
      await page.click('resetDefaults'); await page.refresh();
      check(page.elements.hostname.value === 'localhost' && Number(page.elements.port.value) === 8765 && app.stored.retryInterval === 1000, name + ' reset applies immediately');
      let finishReset;
      app.holdNextWrite(new Promise(resolve => { finishReset = resolve; }));
      await page.click('resetDefaults');
      await page.input('port', '4321');
      finishReset(); await settle(); await page.refresh();
      check(Number(page.elements.port.value) === 4321, 'reset acknowledgement preserves a newer edit');
      await app.tick(500); await page.refresh();
      check(app.stored.port === 4321, 'edit made during reset is applied afterwards');
    }
    await page.input('port', '5432'); page.close(); await app.tick(500);
    check(app.stored.port === 5432, name + ' closing view does not lose queued save');
    const reopened = await view(name, app);
    check(Number(reopened.elements.port.value) === 5432, name + ' reopening reads persisted settings');
    app.api.socket.open();
    app.api.socket.close(1008, 'Update server and extension together');
    await reopened.refresh();
    check(reopened.elements.versionInfo.textContent.includes('Update server and extension together'), name + ' protocol error visible in footer');
    check(reopened.elements[name === 'popup' ? 'status' : 'connectionText'].textContent.includes('Update server and extension together'), name + ' protocol error visible in connection status');
    check(app.timers.size === 0 && app.api.status().protocolVersion === 3, name + ' protocol rejection has no pending retry and displays current protocol');
    reopened.unavailable(); await reopened.refresh();
    check(reopened.elements[name === 'popup' ? 'status' : 'connectionText'].textContent === 'Status unavailable', name + ' does not claim disconnected when background is unavailable');
    reopened.close();
  }
  const approvalApp = await background();
  let approval = {token: 'approval-token', tabId: 9, title: '<b>Example tab</b>',
    origin: 'https://example.org', deadline: Date.now() + 60000, visible: true};
  const decisions = [];
  const originalMessage = approvalApp.message;
  approvalApp.message = async request => {
    if (request.action === 'getScriptConsent') return approval;
    if (request.action === 'decideScriptConsent') { decisions.push(request); approval = null; return true; }
    return originalMessage(request);
  };
  const approvalPage = await view('popup', approvalApp);
  await approvalPage.refresh();
  check(!approvalPage.elements.scriptApproval.hidden && approvalPage.elements.approvalTab.textContent === '<b>Example tab</b>', 'popup displays target title as text');
  check(approvalPage.elements.settingsPanel.hidden, 'approval popup hides unrelated settings controls');
  check(approvalPage.elements.approvalOrigin.textContent === 'https://example.org', 'popup identifies approval origin');
  check(!approvalPage.elements.allowScripts.disabled, 'visible target enables approval');
  approval.visible = false; await approvalPage.refresh();
  check(approvalPage.elements.allowScripts.disabled && approvalPage.elements.denyScripts.disabled, 'hidden target disables both decision buttons');
  approval.visible = true; await approvalPage.refresh();
  await approvalPage.click('allowScripts');
  check(decisions[0].token === 'approval-token' && decisions[0].allowed === true, 'Allow submits the displayed token');
  check(approvalPage.closed, 'accepted approval closes the popup');
  approval = {token: 'deny-token', tabId: 10, title: 'Another tab', origin: 'https://example.org', deadline: Date.now() + 60000, visible: true};
  const denialPage = await view('popup', approvalApp);
  await denialPage.refresh(); await denialPage.click('denyScripts');
  check(decisions[1].token === 'deny-token' && decisions[1].allowed === false, 'Deny submits the next displayed token');
  check(denialPage.closed, 'accepted denial closes its popup');
  denialPage.close();
  approval = {token: 'expired-token', tabId: 11, title: 'Expiring tab', origin: 'https://example.org', deadline: Date.now() + 60000, visible: true};
  const expiringPage = await view('popup', approvalApp);
  await expiringPage.refresh();approval = null;await expiringPage.refresh();
  check(expiringPage.closed && expiringPage.elements.settingsPanel.hidden, 'expired approval closes without revealing settings');
  const broken = await background({port: 0});
  const brokenPage = await view('options', broken);
  check(brokenPage.elements.saveStatus.dataset.state === 'error', 'invalid stored settings never report saved');
  brokenPage.close();
  return checks;
})
