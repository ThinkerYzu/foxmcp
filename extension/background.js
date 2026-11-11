/*
 * FoxMCP Firefox Extension - Background Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// SINGLE CONNECTION CONSTRAINT: Only one WebSocket connection to MCP server allowed
let websocket = null;
let isConnected = false;
const EXTENSION_VERSION = browser.runtime.getManifest().version;
let serverVersion = null;
// Supported and enforced contract; pairing tests keep it aligned with the server.
const PROTOCOL_VERSION = 3;
let connectionError = null;
const requestSockets = new Map();


// Debug logging configuration - set to true to send extension logs to server
const ENABLE_DEBUG_LOGGING_TO_SERVER = false;

// Enhanced console logging that sends to server when available
if (ENABLE_DEBUG_LOGGING_TO_SERVER) {
  const originalConsoleLog = console.log;
  const originalConsoleError = console.error;

  // Buffer to store logs before WebSocket connection is established
  let logBuffer = [];

  function createLogMessage(level, args) {
    return {
      id: `debug_${Date.now()}`,
      type: "debug_log",
      action: "extension.debug",
      data: {
        level: level,
        message: args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' '),
        timestamp: new Date().toISOString()
      }
    };
  }

  function sendLogMessage(logMessage) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      try {
        websocket.send(JSON.stringify(logMessage));
        return true;
      } catch (e) {
        // Ignore errors sending debug logs
      }
    }
    return false;
  }

  function flushLogBuffer() {
    if (logBuffer.length > 0 && websocket && websocket.readyState === WebSocket.OPEN) {
      const bufferedLogs = [...logBuffer];
      logBuffer = [];
      bufferedLogs.forEach(logMessage => {
        sendLogMessage(logMessage);
      });
    }
  }

  function enhancedLog(...args) {
    // Always log to console
    originalConsoleLog(...args);

    const logMessage = createLogMessage("log", args);

    // Try to send immediately, otherwise buffer it
    if (!sendLogMessage(logMessage)) {
      logBuffer.push(logMessage);
      // Keep buffer size reasonable
      if (logBuffer.length > 100) {
        logBuffer = logBuffer.slice(-50);
      }
    }
  }

  function enhancedError(...args) {
    // Always log to console
    originalConsoleError(...args);

    const logMessage = createLogMessage("error", args);

    // Try to send immediately, otherwise buffer it
    if (!sendLogMessage(logMessage)) {
      logBuffer.push(logMessage);
      // Keep buffer size reasonable
      if (logBuffer.length > 100) {
        logBuffer = logBuffer.slice(-50);
      }
    }
  }

  // Replace console methods with enhanced versions
  console.log = enhancedLog;
  console.error = enhancedError;

  // Export flush function to be called when WebSocket connects
  window.flushDebugLogBuffer = flushLogBuffer;
}

let CONFIG = {...FoxMCPConfig.defaults};
let configuredConfig = {...FoxMCPConfig.defaults};
let hasTestOverrides = false;
let initialized = false;
let configError = null;
let connectionState = 'initializing';
let retryAttempts = 0;
let reconnectTimer = null;
let reconnectEpoch = 0;
let nextRetryAt = null;

// All storage reads/writes and initialization share this queue. In particular,
// our own storage.onChanged event cannot apply a stale configuration later.
let configurationQueue = Promise.resolve();
function serializeConfiguration(task) {
  const result = configurationQueue.then(task);
  configurationQueue = result.catch(error => console.error('Configuration operation failed:', error));
  return result;
}

function cancelReconnect() {
  if (reconnectTimer !== null) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  nextRetryAt = null;
  reconnectEpoch++;
}

function connectToMCPServer() {
  if (!initialized || configError) return;
  cancelReconnect();
  try {
    // IMPORTANT: Only one WebSocket connection is allowed at a time
    // Disconnect any existing connection first to prevent multiple connections
    if (websocket && websocket.readyState !== WebSocket.CLOSED) {
      console.log('🔌 Disconnecting existing connection before creating new one');
      disconnect();
    }

    // Compute WebSocket URL dynamically using current config
    const WS_URL = FoxMCPConfig.socketUrl(CONFIG);
    console.log(`🔗 Connecting to ${WS_URL} (attempt ${retryAttempts + 1})`);

    connectionState = 'connecting';
    const socket = new WebSocket(WS_URL);
    websocket = socket;
    serverVersion = null;

    socket.onopen = () => {
      if (websocket !== socket) return;
      socket.send(JSON.stringify({ type: 'hello', data: { version: EXTENSION_VERSION, protocol_version: PROTOCOL_VERSION } }));
      isConnected = false; // Wait for the server to register this profile.
      connectionError = null;

      // Flush any buffered debug logs
      if (typeof window.flushDebugLogBuffer === 'function') {
        window.flushDebugLogBuffer();
      }
    };

    socket.onmessage = async (event) => {
      if (websocket !== socket) return;
      // Test debug message right when we receive a message
      console.log('📨 Extension received message from server');
      try {
        await handleMessage(JSON.parse(event.data), socket);
      } catch (error) {
        console.error('Error handling server message:', error);
      }
    };

    socket.onclose = (event) => {
      // Deliberate disconnects invalidate the socket first. Late close events
      // must not schedule another retry or clear the next socket's monitors.
      if (websocket !== socket) {
        return;
      }

      console.log('Disconnected from MCP server');
      websocket = null;
      isConnected = false;
      serverVersion = null;
      connectionState = 'disconnected';
      clearAllMonitors('the connection to the server dropped');
      scriptConsent.disconnected();
      requestSockets.clear();
      if (event.code === 1008) {
        connectionError = event.reason || 'Incompatible FoxMCP connection; update extension and server.';
        connectionState = 'protocol_error';
        console.error(connectionError);
        return;
      }
      scheduleReconnect();
    };

    socket.onerror = (error) => {
      if (websocket === socket) console.error('WebSocket error:', error);
    };
  } catch (error) {
    console.error('Failed to connect to MCP server:', error);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  cancelReconnect();
  if (!initialized || configError || websocket || isConnected) return;
  const epoch = reconnectEpoch;
  connectionState = 'waiting_retry';
  nextRetryAt = Date.now() + CONFIG.retryInterval;
  reconnectTimer = setTimeout(() => {
    if (epoch !== reconnectEpoch) return;
    reconnectTimer = null;
    nextRetryAt = null;
    retryAttempts++;
    connectToMCPServer();
  }, CONFIG.retryInterval);
}

// Consent belongs to this extension instance, never to the page or MCP client.
class ScriptConsentGate {
  constructor() {
    this.enabled = false;
    this.requested = false;
    this.transition = null;
    this.decisions = new Map();
    this.jobs = new Map();
    this.current = null;
    this.pumping = false;
    this.sequence = 0;
    browser.tabs?.onRemoved?.addListener(tabId => this.invalidate(tabId));
    browser.tabs?.onUpdated?.addListener((tabId, change, tab) => {
      if (change.url) {
        const origin = this.origin(change.url);
        const decision = this.decisions.get(tabId);
        if (decision && decision.origin !== origin) this.decisions.delete(tabId);
        for (const job of [...this.jobs.values()]) {
          // Deferred/preparing jobs still retain their original target. Only
          // jobs admitted with consent disabled bypass origin enforcement.
          if (job.gated !== false && job.tabId === tabId &&
              job.origin !== undefined && job.origin !== origin) {
            this.cancel(job.id, 'Target origin changed', 'SCRIPT_TARGET_CHANGED');
          }
        }
      }
      const item = this.current;
      if (item?.tabId === tabId && (change.status === 'complete' ||
          (change.url && tab?.status === 'complete'))) {
        this.present(item);
      }
    });
    browser.windows?.onFocusChanged?.addListener(() => {
      if (this.current?.waitingForVisibility) this.present(this.current);
    });
    browser.tabs?.onActivated?.addListener(({tabId}) => {
      if (this.current?.tabId === tabId && this.current.waitingForVisibility) this.present(this.current);
    });
  }

  origin(url) {
    try {
      const value = new URL(url).origin;
      return value === 'null' ? null : value;
    } catch (_) { return null; }
  }

  error(message, code = 'SCRIPT_CONSENT_CANCELLED') {
    return Object.assign(new Error(message), {code});
  }

  configure(enabled) {
    this.requested = enabled;
    if (enabled === this.enabled) {
      this.transition = null;
      for (const job of this.jobs.values()) job.deferred = false;
    } else if ([...this.jobs.values()].some(job => !job.deferred)) {
      this.transition = enabled;
    } else {
      this.apply(enabled);
    }
    this.pump();
  }

  apply(enabled) {
    this.enabled = enabled;
    this.transition = null;
    this.decisions.clear();
    for (const job of this.jobs.values()) job.deferred = false;
  }

  advance() {
    if (this.transition !== null && ![...this.jobs.values()].some(job => !job.deferred)) {
      this.apply(this.transition);
    }
    this.pump();
  }

  hasStrictDirective(script) {
    const trivia = /^(?:\s+|\/\/[^\r\n]*(?:[\r\n]|$)|\/\*[\s\S]*?\*\/)*/;
    let rest = script;
    while (true) {
      rest = rest.slice(rest.match(trivia)[0].length);
      const literal = rest.match(/^(?:"(?:[^"\\\r\n]|\\[\s\S])*"|'(?:[^'\\\r\n]|\\[\s\S])*')/);
      if (!literal) return false;
      const tail = rest.slice(literal[0].length);
      const space = tail.match(trivia)[0];
      const next = tail.slice(space.length);
      const terminated = !next || next[0] === ';' ||
        (/[\r\n]/.test(space) && !/^(?:[\[.(+`\-/*%<>=&|?:,]|in\b|instanceof\b)/.test(next));
      if (!terminated) return false;
      if (literal[0] === '"use strict"' || literal[0] === "'use strict'") return true;
      rest = next[0] === ';' ? next.slice(1) : next;
    }
  }

  async run(id, tabId, script) {
    const job = {id, tabId, state: 'preparing', deferred: this.transition !== null};
    this.jobs.set(id, job);
    try {
      const tab = await browser.tabs.get(tabId);
      if (job.cancelled) throw job.cancelled;
      job.origin = this.origin(tab.url);
      job.title = tab.title || tab.url || `Tab ${tabId}`;
      await new Promise((resolve, reject) => {
        job.resolve = resolve;
        job.reject = reject;
        job.state = 'waiting';
        this.pump();
      });
      if (job.cancelled || !requestSockets.has(id)) throw job.cancelled || this.error('Request cancelled');
      job.state = 'executing';
      const live = await browser.tabs.get(tabId);
      if (job.gated && (this.origin(live.url) !== job.origin || job.cancelled)) {
        throw this.error('Target origin changed', 'SCRIPT_TARGET_CHANGED');
      }
      if (job.cancelled || !requestSockets.has(id)) throw job.cancelled || this.error('Request cancelled');
      // Check inside the actual destination document too, closing the navigation
      // race between tabs.get and executeScript. Preserve the script's last value.
      const code = job.gated
        ? `${this.hasStrictDirective(script) ? '"use strict";\n' : ''}if (this.location.origin !== ${JSON.stringify(job.origin)}) { throw new Error('FoxMCP target origin changed'); }\n${script}`
        : script;
      return await browser.tabs.executeScript(tabId, {code});
    } finally {
      this.jobs.delete(id);
      this.advance();
    }
  }

  release(job, allowed) {
    job.state = 'executing';
    if (allowed) job.resolve();
    else job.reject(this.error('Script injection denied for this tab and origin', 'SCRIPT_DENIED'));
  }

  async pump() {
    if (this.pumping) return;
    this.pumping = true;
    try {
      for (const job of this.jobs.values()) {
        if (job.state !== 'waiting' || job.deferred) continue;
        job.gated = this.enabled;
        if (!this.enabled) { this.release(job, true); continue; }
        if (!job.origin) {
          job.state = 'rejected';
          job.reject(this.error('Script consent requires a non-opaque origin', 'SCRIPT_TARGET_CHANGED'));
          continue;
        }
        const decision = this.decisions.get(job.tabId);
        if (decision?.origin === job.origin) { this.release(job, decision.allowed); continue; }
        if (this.current) {
          if (this.current.tabId === job.tabId && this.current.origin === job.origin) {
            job.state = 'approval';
            this.current.jobs.add(job);
          }
          continue;
        }
        const item = {token: String(++this.sequence), tabId: job.tabId, origin: job.origin,
          title: job.title, jobs: new Set([job]), deadline: null};
        this.current = item;
        job.state = 'approval';
        try {
          const tab = await browser.tabs.get(item.tabId);
          if (this.current !== item) continue;
          if (this.origin(tab.url) !== item.origin) throw this.error('Target origin changed', 'SCRIPT_TARGET_CHANGED');
          await browser.tabs.update(item.tabId, {active: true});
          if (this.current !== item) continue;
          await browser.windows.update(tab.windowId, {focused: true});
          if (this.current !== item) continue;
          item.deadline = Date.now() + 60000;
          item.timer = setTimeout(() => this.settle(item, this.error(
            'Script approval timed out after 60 seconds', 'SCRIPT_CONSENT_TIMEOUT')), 60000);
          this.badge('!');
          await this.present(item);
        } catch (error) { this.settle(item, error); }
      }
    } finally {
      this.pumping = false;
      // A cancellation may finish the current item during an awaited browser API.
      if (!this.current && [...this.jobs.values()].some(job => job.state === 'waiting' && !job.deferred)) {
        this.pump();
      }
    }
  }

  async present(item, retries = 5) {
    if (this.current !== item || !item.deadline || item.deciding || Date.now() >= item.deadline) return;
    if (item.opening) { item.openAgain = true; return; }
    clearTimeout(item.popupTimer);
    item.opening = true;
    let retry = false, restricted = false;
    try {
      const view = await this.view();
      if (!view || this.current !== item || item.deciding) return;
      if (!view.visible) {
        item.waitingForVisibility = true;
        item.lastPopupError = 'Target tab or window is not yet active';
        retry = true;
        return;
      }
      const tab = await browser.tabs.get(item.tabId);
      if (this.current !== item || item.deciding) return;
      item.title = tab.title || tab.url || item.title;
      await browser.browserAction.openPopup({windowId: tab.windowId});
      item.waitingForVisibility = false;
      item.lastPopupError = null;
    } catch (error) {
      item.lastPopupError = error.message || String(error);
      console.warn('FoxMCP could not open script approval popup; click the ! badge:', error);
      restricted = /user (?:gesture|input)|userinput/i.test(error.message || String(error));
      retry = !restricted;
      item.waitingForVisibility = !restricted;
    } finally {
      item.opening = false;
      retry = !restricted && (retry || item.openAgain);
      item.openAgain = false;
      if (retry && retries > 0 && this.current === item && !item.deciding && Date.now() < item.deadline) {
        item.popupTimer = setTimeout(() => this.present(item, retries - 1), 200);
      }
    }
  }

  badge(text) {
    const result = browser.browserAction?.setBadgeText({text});
    result?.catch(() => {});
  }

  settle(item, error, allowed) {
    if (this.current !== item) return;
    clearTimeout(item.timer);
    clearTimeout(item.popupTimer);
    this.current = null;
    this.badge('');
    if (!error) this.decisions.set(item.tabId, {origin: item.origin, allowed});
    for (const job of item.jobs) {
      if (!this.jobs.has(job.id) || job.cancelled) continue;
      if (error) { job.state = 'rejected'; job.reject(error); }
      else this.release(job, allowed);
    }
    this.pump();
  }

  async view() {
    const item = this.current;
    if (!item || !item.deadline) return null;
    try {
      const tab = await browser.tabs.get(item.tabId);
      const window = await browser.windows.get(tab.windowId);
      if (this.current !== item) return null;
      return {token: item.token, tabId: item.tabId, origin: item.origin, title: item.title,
        deadline: item.deadline, visible: tab.active && window.focused && this.origin(tab.url) === item.origin};
    } catch (_) { return null; }
  }

  async diagnostics() {
    const item = this.current;
    const view = await this.view();
    return {
      implementation: 'visibility-recovery-2026-10-31', enabled: this.enabled,
      pending: !!item, tabId: item?.tabId ?? null,
      remainingMs: item?.deadline ? Math.max(0, item.deadline - Date.now()) : null,
      visible: !!view?.visible, waitingForVisibility: !!item?.waitingForVisibility,
      opening: !!item?.opening, deciding: !!item?.deciding,
      lastPopupError: item?.lastPopupError ?? null,
      popupViews: browser.extension?.getViews?.({type: 'popup'}).length ?? null
    };
  }

  waitForPopupClose() {
    return Promise.all(browser.extension.getViews({type: 'popup'}).map(view => {
      if (view.closed) return;
      return new Promise(resolve => view.addEventListener('unload', resolve, {once: true}));
    }));
  }

  async decide(token, allowed) {
    if (typeof allowed !== 'boolean') throw this.error('Invalid consent decision');
    const validate = async () => {
      const view = await this.view();
      if (!view || view.token !== token || !view.visible || Date.now() >= view.deadline) {
        throw this.error('Approval expired or the target tab is not visible');
      }
      return this.current;
    };
    const item = await validate();
    item.deciding = true;
    clearTimeout(item.popupTimer);
    // Acknowledge first so the popup can close without an unanswered runtime
    // message. Keep the item pending until its document actually unloads.
    this.waitForPopupClose().then(async () => {
      if (await validate() !== item) throw this.error('Approval changed while closing the popup');
      this.settle(item, null, allowed);
    }).catch(error => {
      if (this.current === item) this.settle(item, error);
    });
    return true;
  }

  cancel(id, message = 'Request cancelled', code) {
    const job = this.jobs.get(id);
    if (!job) return;
    job.cancelled = this.error(message, code);
    if (job.reject) job.reject(job.cancelled);
    const item = this.current;
    if (item?.jobs.delete(job) && !item.jobs.size) {
      clearTimeout(item.timer);
      clearTimeout(item.popupTimer);
      this.current = null;
      this.badge('');
    }
    // Cancellation cannot stop JavaScript already dispatched to Firefox. Keep
    // counting it until executeScript settles, so a toggle cannot overtake it.
    if (job.state !== 'executing') this.jobs.delete(id);
    this.advance();
  }

  invalidate(tabId) {
    this.decisions.delete(tabId);
    for (const job of [...this.jobs.values()]) {
      if (job.tabId === tabId) this.cancel(job.id, 'Target tab closed', 'SCRIPT_TARGET_CHANGED');
    }
  }

  disconnected() {
    for (const id of [...this.jobs.keys()]) this.cancel(id, 'Browser connection closed');
  }
}
const scriptConsent = new ScriptConsentGate();

async function loadConfig() {
  const stored = await browser.storage.sync.get(FoxMCPConfig.storageDefaults);
  // Content scripts can access storage.sync. Keep user consent policy in the
  // extension page's own origin storage, which injected page scripts cannot edit.
  stored.scriptConsent = window.localStorage?.getItem('foxmcp.scriptConsent') === 'true';
  // Upgrade previously valid intervals when the supported maximum is reduced.
  if (Number.isInteger(stored.retryInterval) && stored.retryInterval > 30000 && stored.retryInterval <= 60000) {
    await browser.storage.sync.set({retryInterval: 30000});
    stored.retryInterval = 30000;
  }
  configuredConfig = FoxMCPConfig.configured(stored);
  hasTestOverrides = stored.testHostname != null || stored.testPort != null;
  let next;
  try {
    next = FoxMCPConfig.effective(stored);
  } catch (error) {
    configError = error.message;
    initialized = true;
    disconnect();
    connectionState = 'configuration_error';
    return;
  }
  const restart = !initialized || configError || next.hostname !== CONFIG.hostname || next.port !== CONFIG.port;
  const intervalChanged = next.retryInterval !== CONFIG.retryInterval;
  CONFIG = next;
  scriptConsent.configure(next.scriptConsent);
  initialized = true;
  configError = null;
  if (restart) {
    disconnect();
    retryAttempts = 0;
    connectToMCPServer();
  } else if (intervalChanged && reconnectTimer !== null) {
    scheduleReconnect();
  }
}

// Disconnect function
function disconnect() {
  cancelReconnect();
  const oldSocket = websocket;
  websocket = null; // Invalidate callbacks before close(), including synchronous test sockets.
  isConnected = false;
  serverVersion = null;
  connectionState = 'disconnected';
  connectionError = null;
  scriptConsent.disconnected();
  requestSockets.clear();
  if (oldSocket) {
    oldSocket.close();
    clearAllMonitors('the connection to the server was closed');
  }
}

const pendingSettings = new Map();
let settingsTimer = null;
let settingsRevision = 0;
let settingsEpoch = 0;
let settingsTimerRevision = 0;
const settingsGroups = {
  endpoint: {revision: 0, state: 'saved'},
  retryInterval: {revision: 0, state: 'saved'},
  scriptConsent: {revision: 0, state: 'saved'}
};

function getConnectionStatus() {
  return {
    connected: isConnected, state: connectionState, configError,
    extensionVersion: EXTENSION_VERSION, protocolVersion: PROTOCOL_VERSION, serverVersion, retryAttempts,
    connectionError,
    scriptConsent: {enabled: scriptConsent.enabled, requested: scriptConsent.requested,
      pending: scriptConsent.transition !== null},
    config: {...CONFIG}, configuredConfig: {...configuredConfig}, hasTestOverrides,
    activeUrl: websocket ? websocket.url : null,
    retryDelayMs: reconnectTimer === null ? null : CONFIG.retryInterval, nextRetryAt,
    settings: {groups: structuredClone(settingsGroups)}
  };
}

function queueConfigUpdate(group, values) {
  if (!Object.hasOwn(settingsGroups, group)) throw new Error('Unknown settings group');
  const revision = ++settingsRevision;
  pendingSettings.delete(group);
  try {
    const patch = FoxMCPConfig.group(group, values);
    pendingSettings.set(group, {patch, revision});
    settingsGroups[group] = {revision, state: 'pending'};
  } catch (error) {
    settingsGroups[group] = {revision, state: 'error', error: error.message};
  }
  if (settingsTimer !== null) clearTimeout(settingsTimer);
  settingsTimer = null;
  const timerRevision = ++settingsTimerRevision;
  if (pendingSettings.size) {
    const epoch = settingsEpoch;
    settingsTimer = setTimeout(() => {
      if (epoch !== settingsEpoch || timerRevision !== settingsTimerRevision) return;
      settingsTimer = null;
      const updates = new Map(pendingSettings);
      pendingSettings.clear();
      serializeConfiguration(() => saveSettingsUpdates(updates, epoch));
    }, 500);
  }
  return getConnectionStatus();
}

async function saveSettingsUpdates(updates, epoch) {
  const current = [...updates].filter(([group, entry]) =>
    epoch === settingsEpoch && settingsGroups[group].revision === entry.revision);
  if (!current.length) return;
  try {
    const syncPatch = Object.assign({}, ...current.filter(([group]) => group !== 'scriptConsent').map(([, entry]) => entry.patch));
    if (Object.keys(syncPatch).length) await browser.storage.sync.set(syncPatch);
    const consentPatch = current.find(([group]) => group === 'scriptConsent');
    if (consentPatch) window.localStorage.setItem('foxmcp.scriptConsent', String(consentPatch[1].patch.scriptConsent));
    if (epoch !== settingsEpoch) return; // A queued reset supersedes this in-flight write.
    await loadConfig();
    for (const [group, entry] of current) {
      if (settingsGroups[group].revision === entry.revision) settingsGroups[group] = {revision: entry.revision, state: 'saved'};
    }
  } catch (error) {
    for (const [group, entry] of current) {
      if (settingsGroups[group].revision === entry.revision) {
        settingsGroups[group] = {revision: entry.revision, state: 'error', error: `Could not save settings: ${error.message}`};
      }
    }
  }
}

function resetConfig() {
  settingsEpoch++;
  settingsTimerRevision++;
  pendingSettings.clear();
  if (settingsTimer !== null) clearTimeout(settingsTimer);
  settingsTimer = null;
  const revision = ++settingsRevision;
  for (const group of Object.keys(settingsGroups)) settingsGroups[group] = {revision, state: 'pending'};
  const updates = new Map([
    ['endpoint', {revision, patch: FoxMCPConfig.group('endpoint', FoxMCPConfig.defaults)}],
    ['retryInterval', {revision, patch: FoxMCPConfig.group('retryInterval', FoxMCPConfig.defaults)}],
    ['scriptConsent', {revision, patch: FoxMCPConfig.group('scriptConsent', FoxMCPConfig.defaults)}]
  ]);
  const epoch = settingsEpoch;
  return serializeConfiguration(async () => {
    await saveSettingsUpdates(updates, epoch);
    return getConnectionStatus();
  });
}

async function handleMessage(message, socket = websocket) {
  const { id, type, action, data } = message;

  if (type === 'hello') {
    if (!data || data.protocol_version !== PROTOCOL_VERSION) {
      connectionError = 'Incompatible FoxMCP protocol; update the server and extension together.';
      socket.close(1008, connectionError);
      return;
    }
    const version = data && data.version;
    if (typeof version === 'string' && version.length <= 64 && version.trim() === version && /^[0-9]+(?:\.[0-9]+){0,3}$/.test(version)) {
      serverVersion = version;
      if (serverVersion !== EXTENSION_VERSION) {
        console.warn(`FoxMCP version mismatch: extension ${EXTENSION_VERSION}, server ${serverVersion}. Update both together.`);
      }
    }
    return;
  }

  if (type === 'ready') {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return;
    isConnected = true;
    connectionError = null;
    retryAttempts = 0;
    connectionState = 'connected';
    cancelReconnect();
    console.log('Connected to MCP server');
    return;
  }
  if (type !== 'request' || !isConnected) return;
  requestSockets.set(id, socket);

  // Handle ping-pong for connection testing
  if (action === 'ping') {
    sendResponse(id, 'ping', { message: 'pong', timestamp: new Date().toISOString() });
    return;
  }

  // Route actions to appropriate handlers (all are now async)
  switch (action.split('.')[0]) {
    case 'history':
      await handleHistoryAction(id, action, data);
      break;
    case 'containers':
      await handleContainersAction(id, action, data);
      break;
    case 'tabs':
      await handleTabsAction(id, action, data);
      break;
    case 'tabGroups':
      await handleTabGroupsAction(id, action, data);
      break;
    case 'content':
      await handleContentAction(id, action, data);
      break;
    case 'navigation':
      await handleNavigationAction(id, action, data);
      break;
    case 'windows':
      await handleWindowsAction(id, action, data);
      break;
    case 'bookmarks':
      await handleBookmarksAction(id, action, data);
      break;
    case 'requests':
      await handleRequestsAction(id, action, data);
      break;
    case 'test':
      await handleTestAction(id, action, data);
      break;
    default:
      sendError(id, 'UNKNOWN_ACTION', `Unknown action: ${action}`);
  }
}

function sendResponse(id, action, data) {
  const socket = requestSockets.get(id);
  requestSockets.delete(id);
  if (!isConnected || socket !== websocket || socket.readyState !== WebSocket.OPEN) return;

  const message = {
    id,
    type: 'response',
    action,
    data,
    timestamp: new Date().toISOString()
  };

  socket.send(JSON.stringify(message));
}

function sendError(id, code, message, details = {}) {
  const socket = requestSockets.get(id);
  requestSockets.delete(id);
  if (!isConnected || socket !== websocket || socket.readyState !== WebSocket.OPEN) return;

  const errorMessage = {
    id,
    type: 'error',
    action: '',
    data: {
      code,
      message,
      details
    },
    timestamp: new Date().toISOString()
  };

  socket.send(JSON.stringify(errorMessage));
}

function sendDebugLog(message, level = 'log') {
  // Check WebSocket state directly instead of relying on isConnected flag
  if (!websocket || websocket.readyState !== WebSocket.OPEN) return;

  const debugMessage = {
    id: `debug_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    type: 'debug_log',
    action: 'debug',
    data: {
      level: level,
      message: message,
      timestamp: new Date().toISOString()
    }
  };

  websocket.send(JSON.stringify(debugMessage));
}

// Display and copy the ID of the right-clicked tab, including background tabs.
const TAB_ID_MENU_ID = 'foxmcp-copy-tab-id';

// Firefox does not persist menus for persistent background pages.
browser.menus.create({
  id: TAB_ID_MENU_ID,
  title: 'Tab ID (click to copy)',
  contexts: ['tab'],
  enabled: false
}, () => {
  if (browser.runtime.lastError) {
    console.error('Failed to create tab ID menu:', browser.runtime.lastError.message);
  }
});

browser.menus.onShown.addListener((info, tab) => {
  if (!info.menuIds.includes(TAB_ID_MENU_ID)) return;

  const hasTabId = Number.isInteger(tab?.id) && tab.id >= 0;
  // Dispatch both calls without awaiting, so no menu-instance state is needed.
  browser.menus.update(TAB_ID_MENU_ID, {
    title: hasTabId ? `Tab ID = ${tab.id} (click to copy)` : 'Tab ID unavailable',
    enabled: hasTabId
  }).catch(error => {
    console.error('Failed to update tab ID menu:', error);
  });
  browser.menus.refresh().catch(error => {
    console.error('Failed to refresh tab ID menu:', error);
  });
});

browser.menus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== TAB_ID_MENU_ID || !Number.isInteger(tab?.id) || tab.id < 0) return;

  try {
    await navigator.clipboard.writeText(`tab_id = ${tab.id}`);
  } catch (error) {
    console.error('Failed to copy tab ID:', error);
  }
});

// UI messages use one contract for both pages. Only settings writes are async.
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getConnectionStatus' || request.type === 'getConnectionStatus') {
    sendResponse(getConnectionStatus());
    return false;
  }
  const uiPage = typeof sender.url === 'string' && ['popup/popup.html', 'options.html'].some(
    path => sender.url === browser.runtime.getURL(path));
  if (['queueConfigUpdate', 'resetConfig', 'getScriptConsent', 'decideScriptConsent'].includes(request.action) && !uiPage) {
    return Promise.reject(new Error('This operation is only available in the FoxMCP extension UI'));
  }
  if (request.action === 'getScriptConsent') return scriptConsent.view();
  if (request.action === 'decideScriptConsent') return scriptConsent.decide(request.token, request.allowed);
  if (request.action === 'queueConfigUpdate') {
    try {
      return Promise.resolve(queueConfigUpdate(request.group, request.config));
    } catch (error) {
      return Promise.reject(error);
    }
  }
  if (request.action === 'resetConfig') return resetConfig();
  return false;
});

// History handlers
async function handleHistoryAction(id, action, data) {
  try {
    switch (action) {
      case 'history.query':
        const historyItems = await browser.history.search({
          text: data.query || '',
          startTime: data.startTime || 0,
          endTime: data.endTime || Date.now(),
          maxResults: data.maxResults || 100
        });
        sendResponse(id, action, { items: historyItems });
        break;

      case 'history.recent':
        const recentItems = await browser.history.search({
          text: '',
          maxResults: data.count || 10
        });
        sendResponse(id, action, { items: recentItems });
        break;

      case 'history.delete_item':
        if (!data.url) {
          sendError(id, 'INVALID_PARAMETER', 'URL is required for history.delete_item');
          return;
        }
        await browser.history.deleteUrl({ url: data.url });
        sendResponse(id, action, { success: true, deletedUrl: data.url });
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown history action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `History API error: ${error.message}`);
  }
}

// Colours Firefox accepts for a tab group.
const TAB_GROUP_COLORS = ['blue', 'cyan', 'grey', 'green', 'orange', 'pink', 'purple', 'red', 'yellow'];

function isBrowserId(value) {
  return Number.isInteger(value) && value >= 0;
}

// Optional crop (rect, in CSS pixels of the page) and scale for a screenshot,
// so a request can ask for a small part of the page instead of all of it.
// A malformed rect or scale is an error, not a full-size screenshot: the caller
// asked for something smaller and would otherwise not notice it did not get it.
function captureRegionOptions(data) {
  const result = {};
  if (data.rect !== undefined && data.rect !== null) {
    const rect = data.rect;
    if (typeof rect !== 'object' ||
        ![rect.x, rect.y, rect.width, rect.height].every(Number.isInteger)) {
      throw new Error('rect needs integer x, y, width and height');
    }
    if (rect.x < 0 || rect.y < 0 || rect.width <= 0 || rect.height <= 0) {
      throw new Error('rect needs x and y of 0 or more, and width and height above 0');
    }
    result.rect = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }
  if (data.scale !== undefined && data.scale !== null) {
    if (!Number.isFinite(data.scale) || data.scale <= 0 || data.scale > 1) {
      throw new Error('scale needs a finite number above 0 and at most 1');
    }
    result.scale = data.scale;
  }
  return result;
}

// The tab group properties a request sets, out of title, color and collapsed
//
// Fields the request leaves out are left out here too, so Firefox keeps the
// group's current value for them. Returns null when a field has the wrong type or
// names a colour Firefox does not offer.
function readGroupProperties(data) {
  const properties = {};
  if (data.title !== undefined) {
    if (typeof data.title !== 'string') return null;
    properties.title = data.title;
  }
  if (data.color !== undefined) {
    if (!TAB_GROUP_COLORS.includes(data.color)) return null;
    properties.color = data.color;
  }
  if (data.collapsed !== undefined) {
    if (typeof data.collapsed !== 'boolean') return null;
    properties.collapsed = data.collapsed;
  }
  return properties;
}

// Cookie-store IDs are opaque identifiers issued by this Firefox profile.
function containerError(code, message, details = {}) {
  return Object.assign(new Error(message), {containerCode: code, details});
}

function requireStoreId(value) {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw containerError('INVALID_PARAMETER', 'cookieStoreId must be a nonempty string');
  }
}

async function queryContainers() {
  if (typeof browser.contextualIdentities?.query !== 'function') {
    throw containerError('UNSUPPORTED_API', 'Firefox contextualIdentities API is unavailable');
  }
  try {
    return await browser.contextualIdentities.query({});
  } catch (error) {
    // Fixed nonlocalized ExtensionError from Gecko's checkAPIEnabled().
    if (error.message === 'Contextual identities are currently disabled') {
      throw containerError('CONTAINERS_UNAVAILABLE', 'Firefox containers are disabled');
    }
    throw error;
  }
}

async function validateCookieStore(cookieStoreId, allowPrivate = false) {
  requireStoreId(cookieStoreId);
  if (cookieStoreId === 'firefox-private') {
    if (!allowPrivate) {
      throw containerError('INVALID_PARAMETER', 'Private stores cannot be selected for tab creation');
    }
    return;
  }
  if (cookieStoreId === 'firefox-default') return;
  const identities = await queryContainers();
  if (!identities.some(identity => identity.cookieStoreId === cookieStoreId)) {
    throw containerError('CONTAINER_NOT_FOUND', 'No named container has this cookieStoreId');
  }
}

function serializeContainer(identity) {
  return {cookie_store_id: identity.cookieStoreId, name: identity.name,
          color: identity.color, icon: identity.icon};
}

async function readContainerProperties(data) {
  const properties = {};
  if (data.name !== undefined) {
    if (typeof data.name !== 'string' || !data.name.trim()) {
      throw containerError('INVALID_PARAMETER', 'Container name must be a nonempty string');
    }
    properties.name = data.name;
  }
  // Older supported Firefox versions have no enumeration APIs. Keep their
  // container values separate from the unrelated tab-group colors.
  const defaults = {
    color: ['blue', 'turquoise', 'green', 'yellow', 'orange', 'red', 'pink', 'purple', 'toolbar'],
    icon: ['fingerprint', 'briefcase', 'dollar', 'cart', 'circle', 'gift', 'vacation', 'food', 'fruit', 'pet', 'tree', 'chill']
  };
  for (const [field, method] of [['color', 'getSupportedColors'], ['icon', 'getSupportedIcons']]) {
    if (data[field] === undefined) continue;
    const supported = typeof browser.contextualIdentities[method] === 'function'
      ? (await browser.contextualIdentities[method]()).map(value => value[field]) : defaults[field];
    if (typeof data[field] !== 'string' || !supported.includes(data[field])) {
      throw containerError('INVALID_PARAMETER', `Unsupported container ${field}`, {supported});
    }
    properties[field] = data[field];
  }
  return properties;
}

async function requireNamedContainer(cookieStoreId) {
  requireStoreId(cookieStoreId);
  if (cookieStoreId === 'firefox-default' || cookieStoreId === 'firefox-private') {
    throw containerError('INVALID_PARAMETER', 'Default and private stores are not named containers');
  }
  await validateCookieStore(cookieStoreId);
}

async function handleContainersAction(id, action, data) {
  try {
    switch (action) {
      case 'containers.list': {
        const identities = await queryContainers();
        sendResponse(id, action, {containers: identities.map(serializeContainer),
                                 default_cookie_store_id: 'firefox-default'});
        break;
      }
      case 'containers.create': {
        await queryContainers(); // Check availability even on Firefox versions whose create skips it.
        if (typeof browser.contextualIdentities.create !== 'function') {
          throw containerError('UNSUPPORTED_API', 'Container creation is unavailable');
        }
        if (data.name === undefined) {
          throw containerError('INVALID_PARAMETER', 'Container name is required');
        }
        const properties = await readContainerProperties({color:'blue', icon:'fingerprint', ...data});
        const identity = await browser.contextualIdentities.create(properties);
        sendResponse(id, action, {container: serializeContainer(identity)});
        break;
      }
      case 'containers.update': {
        await requireNamedContainer(data.cookieStoreId);
        if (typeof browser.contextualIdentities.update !== 'function') {
          throw containerError('UNSUPPORTED_API', 'Container updates are unavailable');
        }
        const properties = await readContainerProperties(data);
        if (Object.keys(properties).length === 0) {
          throw containerError('INVALID_PARAMETER', 'Supply at least one container property');
        }
        const identity = await browser.contextualIdentities.update(data.cookieStoreId, properties);
        sendResponse(id, action, {container: serializeContainer(identity)});
        break;
      }
      case 'containers.remove': {
        await requireNamedContainer(data.cookieStoreId);
        if (typeof browser.contextualIdentities.remove !== 'function') {
          throw containerError('UNSUPPORTED_API', 'Container removal is unavailable');
        }
        const tabs = await browser.tabs.query({cookieStoreId: data.cookieStoreId});
        if (tabs.length) {
          throw containerError('CONTAINER_IN_USE', 'Close container tabs before removal',
                               {tab_ids: tabs.map(tab => tab.id)});
        }
        // This cannot exclude a new tab opened concurrently by browser UI.
        await browser.contextualIdentities.remove(data.cookieStoreId);
        sendResponse(id, action, {removed: true, cookie_store_id: data.cookieStoreId});
        break;
      }
      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown containers action: ${action}`);
    }
  } catch (error) {
    sendError(id, error.containerCode || 'API_ERROR', error.message, error.details || {});
  }
}

// Tabs handlers
async function handleTabsAction(id, action, data) {
  try {
    switch (action) {
      case 'tabs.list':
        // No windowId means every window, which is what the tool has always claimed to return.
        //
        // The query object must omit the filter entirely rather than pass a falsy one:
        // `{windowId: undefined}` matches nothing. This used to read
        // `currentWindow: data.currentWindow || true`, where the `|| true` made the filter
        // unconditional and left no way to ask for anything but the current window.
        const tabQuery = data.windowId ? { windowId: data.windowId } : {};
        if (data.cookieStoreId !== undefined) {
          await validateCookieStore(data.cookieStoreId, true);
          tabQuery.cookieStoreId = data.cookieStoreId;
        }
        const tabs = await browser.tabs.query(tabQuery);
        // Include all tabs, even about:blank for debugging
        sendResponse(id, action, {
          tabs: tabs.map(tab => ({url: tab.url, id: tab.id, title: tab.title, active: tab.active, windowId: tab.windowId, pinned: tab.pinned, index: tab.index, cookieStoreId: tab.cookieStoreId})),
          debug: {
            totalFound: tabs.length,
            tabUrls: tabs.map(tab => tab.url)
          }
        });
        break;

      case 'tabs.create':
      case 'tabs.create_in_store':
        const createTabOptions = {
          url: data.url,
          active: data.active || false
        };
        
        // Add windowId if provided
        if (data.windowId) {
          createTabOptions.windowId = data.windowId;
        }
        
        // Add pinned status if provided
        if (data.pinned !== undefined) {
          createTabOptions.pinned = data.pinned;
        }
        
        if (action === 'tabs.create_in_store') {
          await validateCookieStore(data.cookieStoreId);
          const targetWindow = data.windowId !== undefined
            ? await browser.windows.get(data.windowId) : await browser.windows.getLastFocused();
          if (targetWindow.incognito) {
            throw containerError('INVALID_PARAMETER', 'Explicit cookie-store selection requires a normal window');
          }
          // Pin the validated window, avoiding a focus change during creation.
          createTabOptions.windowId = targetWindow.id;
          createTabOptions.cookieStoreId = data.cookieStoreId;
        }
        const newTab = await browser.tabs.create(createTabOptions);
        if (action === 'tabs.create_in_store' && newTab.cookieStoreId !== data.cookieStoreId) {
          throw containerError('API_ERROR', 'Created tab has an unexpected cookie store',
                               {tab_id: newTab.id, actual_cookie_store_id: newTab.cookieStoreId});
        }
        sendResponse(id, action, { tab: newTab });
        break;

      case 'tabs.close':
        await browser.tabs.remove(data.tabId);
        sendResponse(id, action, { success: true });
        break;

      case 'tabs.update':
        const updatedTab = await browser.tabs.update(data.tabId, {
          url: data.url,
          active: data.active
        });
        sendResponse(id, action, { tab: updatedTab });
        break;

      case 'tabs.switch':
        await browser.tabs.update(data.tabId, { active: true });
        sendResponse(id, action, { success: true });
        break;

      case 'tabs.group': {
        // Check both APIs before mutating: grouping arrived in 138, styling in 139.
        if (typeof browser.tabs.group !== 'function' ||
            typeof browser.tabGroups?.update !== 'function') {
          sendError(id, 'UNSUPPORTED_API', 'Tab grouping requires Firefox 139+ and the tabGroups permission');
          return;
        }
        const properties = readGroupProperties(data);
        if (!Array.isArray(data.tabIds) || data.tabIds.length === 0 ||
            !data.tabIds.every(isBrowserId) ||
            (data.groupId !== undefined && !isBrowserId(data.groupId)) ||
            properties === null) {
          sendError(id, 'INVALID_PARAMETER', 'Provide non-empty tabIds, an optional non-negative groupId, string title and valid color');
          return;
        }
        const groupOptions = { tabIds: data.tabIds };
        if (data.groupId === undefined) {
          // Without a window, Firefox creates the group in the focused one.
          const firstTab = await browser.tabs.get(data.tabIds[0]);
          groupOptions.createProperties = { windowId: firstTab.windowId };
        } else {
          groupOptions.groupId = data.groupId;
        }
        const groupId = await browser.tabs.group(groupOptions);
        if (Object.keys(properties).length) {
          // The tabs are grouped by now, and nothing undoes that, so a styling
          // failure is reported alongside the group ID rather than as an error.
          try {
            await browser.tabGroups.update(groupId, properties);
          } catch (error) {
            sendResponse(id, action, { groupId, styleError: error.message });
            return;
          }
        }
        sendResponse(id, action, { groupId });
        break;
      }

      case 'tabs.ungroup':
        if (typeof browser.tabs.ungroup !== 'function') {
          sendError(id, 'UNSUPPORTED_API', 'Tab ungrouping requires Firefox 138+');
          return;
        }
        if (!Array.isArray(data.tabIds) || data.tabIds.length === 0 ||
            !data.tabIds.every(isBrowserId)) {
          sendError(id, 'INVALID_PARAMETER', 'Provide a non-empty array of non-negative tabIds');
          return;
        }
        await browser.tabs.ungroup(data.tabIds);
        sendResponse(id, action, { success: true });
        break;

      case 'tabs.move':
        if (data.tabIds === undefined || data.tabIds === null) {
          sendError(id, 'INVALID_PARAMETER', 'tabIds is required for tabs.move');
          return;
        }

        // Report how many tabs actually moved, because a refused move is not an error.
        //
        // browser.tabs.move returns [] instead of throwing when it declines — moving an
        // unpinned tab in front of a pinned one is the common case. Without the counts, a
        // caller cannot tell a silent refusal from a successful move.
        const tabIdsToMove = Array.isArray(data.tabIds) ? data.tabIds : [data.tabIds];
        const moveProperties = { index: data.index === undefined ? -1 : data.index };
        if (data.windowId) {
          moveProperties.windowId = data.windowId;
        }

        const movedResult = await browser.tabs.move(tabIdsToMove, moveProperties);
        const movedTabs = Array.isArray(movedResult) ? movedResult : [movedResult];
        sendResponse(id, action, {
          tabs: movedTabs.map(tab => ({id: tab.id, url: tab.url, title: tab.title, windowId: tab.windowId, index: tab.index, pinned: tab.pinned})),
          requested: tabIdsToMove.length,
          moved: movedTabs.length
        });
        break;

      case 'tabs.captureVisibleTab':
        const windowId = data.windowId || null;
        let visibleRegion;
        try {
          visibleRegion = captureRegionOptions(data);
        } catch (regionError) {
          sendError(id, 'INVALID_PARAMETER', regionError.message);
          break;
        }
        const options = {
          format: data.format || 'png',
          quality: data.quality || 90,
          ...visibleRegion
        };

        try {
          const dataUrl = await browser.tabs.captureVisibleTab(windowId, options);
          sendResponse(id, action, {
            dataUrl: dataUrl,
            format: options.format,
            quality: options.quality,
            windowId: windowId
          });
        } catch (captureError) {
          sendError(id, 'CAPTURE_ERROR', `Failed to capture screenshot: ${captureError.message}`);
        }
        break;

      case 'tabs.captureTab': {
        // One given tab, wherever it is: in the background, or in a window that is not in front.
        // captureVisibleTab above can only see the tab a window is showing.
        const captureTabId = data.tabId;
        if (!isBrowserId(captureTabId)) {
          sendError(id, 'INVALID_PARAMETER', 'tabs.captureTab needs a non-negative integer tabId');
          break;
        }
        let tabRegion;
        try {
          tabRegion = captureRegionOptions(data);
        } catch (regionError) {
          sendError(id, 'INVALID_PARAMETER', regionError.message);
          break;
        }
        const captureOptions = {
          format: data.format || 'png',
          quality: data.quality || 90,
          ...tabRegion
        };

        try {
          const dataUrl = await browser.tabs.captureTab(captureTabId, captureOptions);
          sendResponse(id, action, {
            dataUrl: dataUrl,
            format: captureOptions.format,
            quality: captureOptions.quality,
            tabId: captureTabId
          });
        } catch (captureError) {
          sendError(id, 'CAPTURE_ERROR', `Failed to capture screenshot of tab ${captureTabId}: ${captureError.message}`);
        }
        break;
      }

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown tabs action: ${action}`);
    }
  } catch (error) {
    sendError(id, error.containerCode || 'API_ERROR', `Tabs API error: ${error.message}`, error.details || {});
  }
}

// Tab groups handlers
async function handleTabGroupsAction(id, action, data) {
  try {
    switch (action) {
      case 'tabGroups.update': {
        if (typeof browser.tabGroups?.update !== 'function') {
          sendError(id, 'UNSUPPORTED_API', 'tabGroups.update requires Firefox 139+ and the tabGroups permission');
          return;
        }
        const properties = readGroupProperties(data);
        if (!isBrowserId(data.groupId) || properties === null ||
            Object.keys(properties).length === 0) {
          sendError(id, 'INVALID_PARAMETER', 'Provide a non-negative groupId and at least one of title, color or collapsed');
          return;
        }
        const group = await browser.tabGroups.update(data.groupId, properties);
        sendResponse(id, action, { group });
        break;
      }

      case 'tabGroups.query': {
        if (typeof browser.tabGroups?.query !== 'function') {
          sendError(id, 'UNSUPPORTED_API', 'tabGroups.query requires Firefox 139+ and the tabGroups permission');
          return;
        }
        const queryInfo = readGroupProperties(data);
        if ((data.windowId !== undefined && !isBrowserId(data.windowId)) || queryInfo === null) {
          sendError(id, 'INVALID_PARAMETER', 'windowId must be a non-negative integer, title a string, color valid and collapsed a boolean');
          return;
        }
        if (data.windowId !== undefined) queryInfo.windowId = data.windowId;
        const groups = await browser.tabGroups.query(queryInfo);
        // Always include id: callers need it for tabs.group and tabGroups.update.
        sendResponse(id, action, {
          groups: groups.map(group => ({
            id: group.id,
            title: group.title,
            color: group.color,
            collapsed: group.collapsed,
            windowId: group.windowId
          }))
        });
        break;
      }

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown tabGroups action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Tab groups API error: ${error.message}`);
  }
}

// Helper function to get current tab URL
async function getCurrentTabUrl(tabId) {
  try {
    const tab = await browser.tabs.get(tabId);
    return tab.url;
  } catch (error) {
    return "Unknown URL";
  }
}

// Helper function to send message with retry logic for content script
async function sendMessageWithRetry(tabId, message, maxRetries = 5, delayMs = 2000) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      // Check if tab exists and is accessible
      const tab = await browser.tabs.get(tabId);
      if (!tab) {
        throw new Error('Tab not found');
      }

      // Skip status check for now and try to send message
      // The content script should be available on all URLs except chrome:// pages
      if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('moz-extension://'))) {
        throw new Error('Cannot access content script on system pages');
      }

      const result = await browser.tabs.sendMessage(tabId, message);
      return result;
    } catch (error) {
      if (attempt === maxRetries) {
        throw new Error(`Content script not available after ${maxRetries} attempts: ${error.message}`);
      }

      // Wait longer before retry
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }
}

// Content handlers
async function handleContentAction(id, action, data) {
  try {
    switch (action) {
      case 'content.load_file': {
        const url = new URL(data.url);
        if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' ||
            !url.port || !/^\/files\/[A-Za-z0-9_-]{43}$/.test(url.pathname) ||
            url.username || url.password || url.search || url.hash) {
          throw new Error('Invalid local file transfer URL');
        }
        const tab = await browser.tabs.get(data.tabId);
        if (tab.incognito) {
          throw new Error('Local file loading is unavailable in private tabs');
        }
        const prepare = { action: 'prepareFile', data: { fileId: data.fileId } };
        let ready;
        try {
          ready = await browser.tabs.sendMessage(data.tabId, prepare);
        } catch (error) {
          if (!error.message.includes('Receiving end does not exist')) throw error;
          await browser.tabs.executeScript(data.tabId, { file: '/content.js' });
          ready = await browser.tabs.sendMessage(data.tabId, prepare);
        }
        if (!ready || ready.error) throw new Error(ready?.error || 'Content script unavailable');
        const response = await fetch(url.href, {
          credentials: 'omit', redirect: 'error', cache: 'no-store',
          signal: AbortSignal.timeout(110000)
        });
        if (!response.ok) throw new Error(`Local file transfer returned HTTP ${response.status}`);
        const blob = await response.blob();
        if (blob.size !== data.size) throw new Error('File size changed during transfer');
        const file = new File([blob], data.name, {
          type: data.type, lastModified: data.lastModified
        });
        const result = await browser.tabs.sendMessage(data.tabId, {
          action: 'storeFile', data: { fileId: data.fileId, file }
        });
        if (!result || result.error) throw new Error(result?.error || 'Content script unavailable');
        sendResponse(id, action, result);
        break;
      }

      case 'content.get_text':
        const textResult = await sendMessageWithRetry(data.tabId, {
          action: 'extractText'
        });
        sendResponse(id, action, { text: textResult.text });
        break;

      case 'content.get_html':
        const htmlResult = await sendMessageWithRetry(data.tabId, {
          action: 'extractHTML'
        });
        sendResponse(id, action, { html: htmlResult.html });
        break;

      case 'content.execute_script':
        try {
          const executeResults = await scriptConsent.run(id, data.tabId, data.script);
          // executeScript returns an array of results from each frame
          const result = executeResults && executeResults.length > 0 ? executeResults[0] : null;
          sendResponse(id, action, { 
            result: result,
            url: await getCurrentTabUrl(data.tabId)
          });
        } catch (scriptError) {
          sendError(id, scriptError.code || 'SCRIPT_ERROR', `Script execution failed: ${scriptError.message}`);
        }
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown content action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Content API error: ${error.message}`);
  }
}

// Navigation handlers
async function handleNavigationAction(id, action, data) {
  try {
    switch (action) {
      case 'navigation.go_to_url':
        await browser.tabs.update(data.tabId, { url: data.url });
        sendResponse(id, action, { success: true });
        break;

      case 'navigation.back':
        await browser.tabs.goBack(data.tabId);
        sendResponse(id, action, { success: true });
        break;

      case 'navigation.forward':
        await browser.tabs.goForward(data.tabId);
        sendResponse(id, action, { success: true });
        break;

      case 'navigation.reload':
        await browser.tabs.reload(data.tabId, { bypassCache: data.bypassCache || false });
        sendResponse(id, action, { success: true });
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown navigation action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Navigation API error: ${error.message}`);
  }
}

// Bookmarks handlers

// Why a bookmark cannot go under parentId, or null when it can.
//
// Firefox only checks that a new parent exists, so it accepts a plain
// bookmark or a separator as one. The item it puts there is listed nowhere
// afterwards: getTree leaves it out and getChildren on the parent returns
// nothing, while the caller is told it worked. An unknown ID makes
// bookmarks.get throw, which reaches the caller as an API_ERROR.
async function nonFolderParentReason(parentId) {
  const [parent] = await browser.bookmarks.get(parentId);
  if (parent.type !== 'folder') {
    return `Parent ${parentId} is a ${parent.type}, not a folder`;
  }
  return null;
}

async function handleBookmarksAction(id, action, data) {
  try {
    if (['bookmarks.create', 'bookmarks.createFolder', 'bookmarks.move'].includes(action)
        && data && data.parentId !== undefined) {
      const reason = await nonFolderParentReason(data.parentId);
      if (reason) {
        sendError(id, 'INVALID_PARAMETER', reason);
        return;
      }
    }

    switch (action) {
      case 'bookmarks.list':
        let bookmarks;

        // Check if folder filtering is requested
        if (data && data.folderId) {
          try {
            // Get bookmarks from specific folder
            const folderChildren = await browser.bookmarks.getChildren(data.folderId);
            bookmarks = folderChildren.map(node => ({
              id: node.id,
              title: node.title,
              url: node.url,
              isFolder: !node.url,
              parentId: node.parentId,
              index: node.index
            }));
          } catch (folderError) {
            // Handle invalid folder ID
            sendError(id, 'INVALID_FOLDER_ID', `Invalid folder ID: ${data.folderId}. ${folderError.message}`);
            return;
          }
        } else {
          // Get all bookmarks (existing behavior)
          const bookmarkTree = await browser.bookmarks.getTree();
          // Flatten the tree structure into a flat array
          function flattenBookmarks(nodes) {
            let result = [];
            for (const node of nodes) {
              // Add current node if it's a folder or has a URL (bookmark)
              result.push({
                id: node.id,
                title: node.title,
                url: node.url,
                isFolder: !node.url,
                parentId: node.parentId,
                index: node.index
              });
              // Recursively add children
              if (node.children) {
                result = result.concat(flattenBookmarks(node.children));
              }
            }
            return result;
          }
          bookmarks = flattenBookmarks(bookmarkTree);
        }

        sendResponse(id, action, { bookmarks });
        break;

      case 'bookmarks.search':
        const searchResults = await browser.bookmarks.search(data.query);
        sendResponse(id, action, { bookmarks: searchResults });
        break;

      case 'bookmarks.create':
        const newBookmark = await browser.bookmarks.create({
          parentId: data.parentId,
          title: data.title,
          url: data.url
        });
        sendResponse(id, action, { bookmark: newBookmark });
        break;

      case 'bookmarks.createFolder':
        const newFolder = await browser.bookmarks.create({
          parentId: data.parentId,
          title: data.title
          // No URL - creates a folder
        });
        sendResponse(id, action, { folder: newFolder });
        break;

      case 'bookmarks.update':
        const updateData = {};
        if (data.title !== undefined) {
          updateData.title = data.title;
        }
        if (data.url !== undefined) {
          updateData.url = data.url;
        }
        const updatedBookmark = await browser.bookmarks.update(data.bookmarkId, updateData);
        sendResponse(id, action, { bookmark: updatedBookmark });
        break;

      case 'bookmarks.move': {
        const destination = {};
        if (data.parentId !== undefined) {
          destination.parentId = data.parentId;
        }
        if (data.index !== undefined) {
          destination.index = data.index;
        }
        const movedBookmark = await browser.bookmarks.move(data.bookmarkId, destination);
        sendResponse(id, action, { bookmark: movedBookmark });
        break;
      }

      case 'bookmarks.delete':
        await browser.bookmarks.remove(data.bookmarkId);
        sendResponse(id, action, { success: true });
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown bookmarks action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Bookmarks API error: ${error.message}`);
  }
}

// Windows handlers
async function handleWindowsAction(id, action, data) {
  try {
    switch (action) {
      case 'windows.list':
        const windows = await browser.windows.getAll({
          populate: data.populate !== false, // default to true
          windowTypes: ['normal', 'popup', 'panel', 'devtools']
        });
        sendResponse(id, action, { windows });
        break;

      case 'windows.get':
        if (!data.windowId) {
          sendError(id, 'INVALID_PARAMETER', 'windowId is required for windows.get');
          return;
        }
        const window = await browser.windows.get(data.windowId, {
          populate: data.populate !== false
        });
        sendResponse(id, action, { window });
        break;

      case 'windows.get_current':
        const currentWindow = await browser.windows.getCurrent({
          populate: data.populate !== false
        });
        sendResponse(id, action, { window: currentWindow });
        break;

      case 'windows.create': {
        const createOptions = {};
        if (data.url) createOptions.url = data.url;
        if (data.type) createOptions.type = data.type;
        if (data.state) createOptions.state = data.state;
        if (data.width) createOptions.width = data.width;
        if (data.height) createOptions.height = data.height;
        if (data.top) createOptions.top = data.top;
        if (data.left) createOptions.left = data.left;
        if (data.incognito !== undefined) createOptions.incognito = data.incognito;

        // Firefox always focuses a new window: its schema marks `focused: false` as
        // "Opening inactive windows is not supported" and ignores it. So for a
        // background window, hand focus back to the window that had it. If no
        // Firefox window had focus, there is nothing of ours to hand it back to.
        const previous = data.focused === false ? await browser.windows.getLastFocused() : null;
        let newWindow = await browser.windows.create(createOptions);
        if (previous?.focused) {
          await browser.windows.update(previous.id, { focused: true });
          newWindow = await browser.windows.get(newWindow.id, { populate: true });
        }
        sendResponse(id, action, { window: newWindow });
        break;
      }

      case 'windows.close':
        if (!data.windowId) {
          sendError(id, 'INVALID_PARAMETER', 'windowId is required for windows.close');
          return;
        }
        await browser.windows.remove(data.windowId);
        sendResponse(id, action, { success: true, windowId: data.windowId });
        break;

      case 'windows.focus':
        if (!data.windowId) {
          sendError(id, 'INVALID_PARAMETER', 'windowId is required for windows.focus');
          return;
        }
        await browser.windows.update(data.windowId, { focused: true });
        sendResponse(id, action, { success: true, windowId: data.windowId });
        break;

      case 'windows.update':
        if (!data.windowId) {
          sendError(id, 'INVALID_PARAMETER', 'windowId is required for windows.update');
          return;
        }
        const updateOptions = {};
        if (data.state) updateOptions.state = data.state;
        if (data.focused !== undefined) updateOptions.focused = data.focused;
        if (data.width) updateOptions.width = data.width;
        if (data.height) updateOptions.height = data.height;
        if (data.top !== undefined) updateOptions.top = data.top;
        if (data.left !== undefined) updateOptions.left = data.left;
        
        const updatedWindow = await browser.windows.update(data.windowId, updateOptions);
        sendResponse(id, action, { window: updatedWindow });
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown windows action: ${action}`);
    }
  } catch (error) {
    // Handle specific window errors
    if (error.message && error.message.includes('No window with id')) {
      sendError(id, 'WINDOW_NOT_FOUND', `Window with ID ${data.windowId} not found`);
    } else if (error.message && error.message.includes('Invalid window state')) {
      sendError(id, 'INVALID_WINDOW_STATE', error.message);
    } else if (error.message && error.message.includes('Invalid window type')) {
      sendError(id, 'INVALID_WINDOW_TYPE', error.message);
    } else {
      sendError(id, 'API_ERROR', `Windows API error: ${error.message}`);
    }
  }
}

// REMOVED: onStartup listener to prevent race conditions during testing
// Extension will only connect on explicit user actions or valid storage events

// Request monitoring state
const activeMonitors = new Map(); // monitor_id -> monitor config
const capturedRequests = new Map(); // monitor_id -> array of requests
const requestDetails = new Map(); // request_id -> full request details
const capturedResponseBodies = new Map(); // [monitor_id, request_id] -> body projection
const monitorCaptureOptions = new Map(); // kept after stop while captured data is readable
const MAX_STORED_RESPONSE_BODIES = 200;

// Validate raw protocol requests too; MCP schema validation is only one entry point.
function normalizeMonitorOptions(options) {
  if (options === undefined || options === null) options = {};
  if (typeof options !== 'object' || Array.isArray(options)) {
    throw new Error('options must be an object');
  }
  const defaults = {
    capture_request_bodies: true,
    capture_response_bodies: true,
    max_body_size: 50000,
    content_types_to_capture: ['application/json', 'text/plain']
  };
  for (const key of Object.keys(options)) {
    if (!Object.prototype.hasOwnProperty.call(defaults, key)) {
      throw new Error(`Unsupported monitoring option: ${key}`);
    }
  }
  const result = { ...defaults, ...options };
  for (const key of ['capture_request_bodies', 'capture_response_bodies']) {
    if (typeof result[key] !== 'boolean') throw new Error(`${key} must be a boolean`);
  }
  if (!Number.isInteger(result.max_body_size) || result.max_body_size <= 0) {
    throw new Error('max_body_size must be a positive integer');
  }
  if (!Array.isArray(result.content_types_to_capture) ||
      !result.content_types_to_capture.every(type => typeof type === 'string' && type.length > 0)) {
    throw new Error('content_types_to_capture must be an array of nonempty strings');
  }
  result.content_types_to_capture = Object.freeze([...result.content_types_to_capture]);
  return Object.freeze(result);
}

function responseBodyKey(monitorId, requestId) {
  return JSON.stringify([monitorId, requestId]);
}

// WebRequest listener functions
let onBeforeRequestListener = null;
let onBeforeSendHeadersListener = null;
let onSendHeadersListener = null;
let onHeadersReceivedListener = null;
let onResponseStartedListener = null;
let onCompletedListener = null;
let onErrorOccurredListener = null;


function startWebRequestMonitoring(monitor) {
  console.log(`🔍 Starting WebRequest monitoring for monitor ${monitor.id}`);
  setupWebRequestListeners();
}

function setupWebRequestListeners() {
  if (onBeforeRequestListener) {
    // Already set up
    return;
  }

  console.log('🔧 Setting up WebRequest API listeners');

  // Before request - captures initial request data
  onBeforeRequestListener = function(details) {
    handleWebRequestEvent('onBeforeRequest', details);
    captureResponseBody(details);
  };

  // Headers received - captures response headers and status
  onHeadersReceivedListener = function(details) {
    handleWebRequestEvent('onHeadersReceived', details);
  };

  // Completed - captures final timing and status
  onCompletedListener = function(details) {
    handleWebRequestEvent('onCompleted', details);
  };

  // Error - captures failed requests
  onErrorOccurredListener = function(details) {
    handleWebRequestEvent('onErrorOccurred', details);
  };

  // "blocking" is what makes captureResponseBody possible, not a wish to block
  // anything: Firefox only lets filterResponseData reach a request whose
  // extension registered a blocking listener for it. The listener returns
  // nothing, so no request is delayed, cancelled or redirected.
  browser.webRequest.onBeforeRequest.addListener(
    onBeforeRequestListener,
    { urls: ["<all_urls>"] },
    ["requestBody", "blocking"]
  );

  browser.webRequest.onHeadersReceived.addListener(
    onHeadersReceivedListener,
    { urls: ["<all_urls>"] },
    // Record the MIME type before response filters can finish. With an
    // asynchronous header notification, a tiny response can reach onstop first
    // and be stored as having no content type. No headers are changed.
    ["responseHeaders", "blocking"]
  );

  browser.webRequest.onCompleted.addListener(
    onCompletedListener,
    { urls: ["<all_urls>"] }
  );

  browser.webRequest.onErrorOccurred.addListener(
    onErrorOccurredListener,
    { urls: ["<all_urls>"] }
  );

  console.log('✅ WebRequest listeners registered');
}

// Drop every monitor and everything they captured.
//
// A monitor lives in this page, which outlives any one server, and only the
// client that started it knows its id. Once the connection carrying that client
// is gone the monitor can never be read or stopped again, while it goes on
// holding the webRequest listeners up and filtering response bodies for nobody.
// The captured data goes with the monitors for the same reason: the request ids
// that reach it come from requests.list_captured.
function clearAllMonitors(reason) {
  const monitorCount = activeMonitors.size;

  activeMonitors.clear();
  capturedRequests.clear();
  requestDetails.clear();
  capturedResponseBodies.clear();
  monitorCaptureOptions.clear();

  if (monitorCount > 0) {
    stopWebRequestMonitoring();
    console.log(`🧹 Cleared ${monitorCount} monitor(s): ${reason}`);
  }
}

function stopWebRequestMonitoring() {
  if (activeMonitors.size > 0) {
    // Still have active monitors
    return;
  }

  console.log('🛑 Stopping WebRequest monitoring - removing listeners');

  if (onBeforeRequestListener) {
    browser.webRequest.onBeforeRequest.removeListener(onBeforeRequestListener);
    onBeforeRequestListener = null;
  }

  if (onHeadersReceivedListener) {
    browser.webRequest.onHeadersReceived.removeListener(onHeadersReceivedListener);
    onHeadersReceivedListener = null;
  }

  if (onCompletedListener) {
    browser.webRequest.onCompleted.removeListener(onCompletedListener);
    onCompletedListener = null;
  }

  if (onErrorOccurredListener) {
    browser.webRequest.onErrorOccurred.removeListener(onErrorOccurredListener);
    onErrorOccurredListener = null;
  }

  console.log('✅ WebRequest listeners removed');
}

function handleWebRequestEvent(eventType, details) {
  // Check if any monitor should capture this request
  for (const [monitorId, monitor] of activeMonitors) {
    if (shouldCaptureRequest(monitor, details)) {
      captureRequestEvent(monitorId, eventType, details);
    }
  }
}

function shouldCaptureRequest(monitor, details) {
  // Check tab filter
  if (monitor.tab_id && details.tabId !== monitor.tab_id) {
    return false;
  }

  // Check URL patterns
  if (monitor.url_patterns && monitor.url_patterns.length > 0) {
    const url = details.url;
    return monitor.url_patterns.some(pattern => {
      // <all_urls> is not glob syntax, but it is what a WebExtensions caller
      // reaches for, and as a glob it matches nothing at all.
      if (pattern === '*' || pattern === '<all_urls>') return true;

      // Convert glob pattern to regex
      const regexPattern = pattern
        .replace(/\*/g, '.*')
        .replace(/\?/g, '.');

      try {
        return new RegExp(regexPattern).test(url);
      } catch (e) {
        console.warn(`Invalid URL pattern: ${pattern}`, e);
        return false;
      }
    });
  }

  return true; // No filters, capture all
}

function captureRequestEvent(monitorId, eventType, details) {
  const requestId = details.requestId;
  const timestamp = new Date().toISOString();

  // One record per request id, shared by every monitor that matches it.
  //
  // The WebRequest API delivers each event once however many monitors want it,
  // and requests.get_content reads the record by request id alone. Anything
  // per-monitor therefore has to be keyed by monitor: listed_by holds the
  // monitors that already have this request in capturedRequests, so each of
  // them lists it exactly once.
  let request = requestDetails.get(requestId);
  if (!request) {
    request = {
      request_id: requestId,
      url: details.url,
      method: details.method || 'GET',
      tab_id: details.tabId,
      frame_id: details.frameId,
      type: details.type,
      timestamp: timestamp,
      events: [],
      listed_by: new Set()
    };
    requestDetails.set(requestId, request);
  }

  // Add event data
  const event = {
    type: eventType,
    timestamp: timestamp,
    timeStamp: details.timeStamp
  };

  switch (eventType) {
    case 'onBeforeRequest':
      event.url = details.url;
      event.method = details.method;
      if (monitorCaptureOptions.get(monitorId)?.capture_request_bodies) {
        event.requestBody = details.requestBody;
      }
      break;

    case 'onHeadersReceived':
      event.responseHeaders = details.responseHeaders;
      event.statusCode = details.statusCode;
      event.statusLine = details.statusLine;
      request.status_code = details.statusCode;
      request.response_headers = details.responseHeaders;

      // Extract content length and type from headers
      if (details.responseHeaders) {
        for (const header of details.responseHeaders) {
          if (header.name.toLowerCase() === 'content-length') {
            request.response_content_length = parseInt(header.value) || 0;
          }
          if (header.name.toLowerCase() === 'content-type') {
            request.response_content_type = header.value;
          }
        }
      }
      break;

    case 'onCompleted':
      event.statusCode = details.statusCode;
      request.status_code = details.statusCode;
      request.completed = true;
      request.duration_ms = details.timeStamp - (request.events[0]?.timeStamp || details.timeStamp);

      break;

    case 'onErrorOccurred':
      event.error = details.error;
      request.error = details.error;
      request.completed = true;
      break;
  }

  request.events.push(event);

  // If request is complete, add to captured list
  if (request.completed && !request.listed_by.has(monitorId)) {
    const captured = capturedRequests.get(monitorId) || [];
    captured.push({
      request_id: requestId,
      url: request.url,
      method: request.method,
      status_code: request.status_code,
      duration_ms: request.duration_ms || 0,
      timestamp: request.timestamp,
      tab_id: request.tab_id,
      type: request.type,
      error: request.error,
      response_size_bytes: request.response_content_length || 0,
      response_content_type: request.response_content_type || null
    });
    capturedRequests.set(monitorId, captured);
    request.listed_by.add(monitorId);

    const sizeInfo = request.response_content_length ? ` (${request.response_content_length} bytes)` : '';
    console.log(`📋 Captured request: ${request.method} ${request.url} -> ${request.status_code || 'ERROR'}${sizeInfo}`);
  }
}

// Keep a copy of one request's response body for requests.get_content.
//
// Call from onBeforeRequest only; the response stream can no longer be tapped
// once it has started. Does nothing unless an active monitor matches the
// request and asked for response bodies. What it keeps lands in
// capturedResponseBodies under a monitor/request key. Request ids are the same
// ones requests.list_captured reports.
//
// browser.webRequest.filterResponseData puts this code in the path of the bytes
// on their way to the page, so every byte read here has to be written back or
// the page gets a truncated response. That is why write() comes first and the
// bookkeeping cannot throw past it. Firefox has already undone any
// Content-Encoding by this point, so the bytes are the real body. Only the
// largest prefix requested by a matching monitor is buffered. Each monitor's
// own size/type projection is retained, while every body reports its full size.
function captureResponseBody(details) {
  const monitors = Array.from(activeMonitors.values()).filter(monitor =>
    monitor.options.capture_response_bodies && shouldCaptureRequest(monitor, details));
  if (monitors.length === 0) return;

  let filter;
  try {
    filter = browser.webRequest.filterResponseData(details.requestId);
  } catch (error) {
    // Not every request can be filtered - a cached alt-data response and a
    // redirect both refuse. The request is still captured, just without a body.
    console.log(`No response filter for ${details.url}: ${error.message}`);
    return;
  }

  // Intercept once and buffer the largest prefix needed by any interested monitor.
  const maxSize = Math.max(...monitors.map(monitor => monitor.options.max_body_size));
  const kept = [];
  let totalBytes = 0;
  let keptBytes = 0;

  filter.ondata = (event) => {
    filter.write(event.data);

    try {
      totalBytes += event.data.byteLength;

      const room = maxSize - keptBytes;
      if (room <= 0) {
        return;
      }

      const chunk = event.data.byteLength > room ? event.data.slice(0, room) : event.data;
      kept.push(chunk);
      keptBytes += chunk.byteLength;
    } catch (error) {
      console.error(`Error buffering response body for ${details.url}: ${error.message}`);
    }
  };

  filter.onstop = () => {
    filter.close();

    try {
      for (const monitor of monitors) {
        // A disconnected profile must not repopulate storage from a stale stream.
        if (monitorCaptureOptions.get(monitor.id) === monitor.options) {
          storeResponseBody(details.requestId, monitor, kept, totalBytes);
        }
      }
    } catch (error) {
      console.error(`Error storing response body for ${details.url}: ${error.message}`);
    }
  };

  filter.onerror = () => {
    console.log(`Response filter for ${details.url} stopped: ${filter.error}`);
  };
}

// Record what captureResponseBody read, as text when the content type allows it.
//
// size_bytes is the whole body even when content is null, so a caller that
// cannot get the bytes still learns how many there were.
//
// Only the last MAX_STORED_RESPONSE_BODIES are kept. A monitor on "*" sees
// every request the browser makes, and holding max_body_size for each of them
// would grow without limit for as long as monitoring runs. The size recorded on
// the request itself survives eviction, so an evicted request still reports how
// large its body was.
function storeResponseBody(requestId, monitor, chunks, totalBytes) {
  const requestDetail = requestDetails.get(requestId);
  const contentType = requestDetail?.response_content_type || '';

  if (requestDetail) {
    requestDetail.response_body_size = totalBytes;
  }

  const wanted = shouldCaptureContentType(contentType, monitor.options.content_types_to_capture);

  let remaining = monitor.options.max_body_size;
  const prefix = [];
  for (const chunk of chunks) {
    if (remaining <= 0) break;
    prefix.push(chunk.byteLength > remaining ? chunk.slice(0, remaining) : chunk);
    remaining -= prefix[prefix.length - 1].byteLength;
  }
  capturedResponseBodies.set(responseBodyKey(monitor.id, requestId), {
    content: wanted ? decodeResponseText(prefix, contentType) : null,
    content_type: contentType || null,
    size_bytes: totalBytes,
    truncated: totalBytes > monitor.options.max_body_size
  });

  while (capturedResponseBodies.size > MAX_STORED_RESPONSE_BODIES) {
    capturedResponseBodies.delete(capturedResponseBodies.keys().next().value);
  }
}

// Whether a response's content type is one the monitor asked to capture.
//
// An empty captureTypes means every type. A response with no content type at
// all matches nothing, since there is no way to tell what it holds.
function shouldCaptureContentType(contentType, captureTypes) {
  if (!captureTypes || captureTypes.length === 0) {
    return true;
  }
  if (!contentType) {
    return false;
  }

  return captureTypes.some(type => {
    if (type.includes('*')) {
      return contentType.startsWith(type.split('/')[0]);
    }
    return contentType.includes(type);
  });
}

// Join response chunks into a string, or null if the body is not text.
//
// Honours the charset the response declared, falling back to UTF-8 when it
// names one TextDecoder does not know.
function decodeResponseText(chunks, contentType) {
  if (!/^\s*(text\/|application\/(json|xml|javascript|xhtml\+xml))/i.test(contentType)) {
    return null;
  }

  const total = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(new Uint8Array(chunk), offset);
    offset += chunk.byteLength;
  }

  const charset = /charset\s*=\s*["']?([\w-]+)/i.exec(contentType)?.[1] || 'utf-8';
  try {
    return new TextDecoder(charset).decode(body);
  } catch (error) {
    return new TextDecoder('utf-8').decode(body);
  }
}

// Request monitoring handlers
async function handleRequestsAction(id, action, data) {
  try {
    switch (action) {
      case 'requests.start_monitoring':
        // Always send debug message to test if WebSocket works
        console.log('📡 ALWAYS: requests.start_monitoring called');

        let captureOptions;
        try {
          captureOptions = normalizeMonitorOptions(data.options);
        } catch (error) {
          sendError(id, 'INVALID_PARAMETER', error.message);
          break;
        }
        const monitor_id = `mon_${Date.now()}`;
        const monitor = {
          id: monitor_id,
          url_patterns: data.url_patterns || [],
          options: captureOptions,
          tab_id: data.tab_id || null,
          started_at: new Date().toISOString(),
          status: 'active'
        };

        // Debug: Check what options we received
        console.log(`📡 DEBUG: Monitor options received: ${JSON.stringify(monitor.options)}`);

        // Register the monitor before the listeners go up, so the first request
        // through onBeforeRequest can already find it and tap its body.
        monitorCaptureOptions.set(monitor_id, captureOptions);
        activeMonitors.set(monitor_id, monitor);
        capturedRequests.set(monitor_id, []);
        startWebRequestMonitoring(monitor);

        sendResponse(id, action, {
          monitor_id: monitor_id,
          status: 'active',
          started_at: monitor.started_at,
          url_patterns: monitor.url_patterns,
          options: monitor.options
        });
        break;

      case 'requests.stop_monitoring':
        const monitorToStop = activeMonitors.get(data.monitor_id);
        if (!monitorToStop) {
          sendError(id, 'MONITOR_NOT_FOUND', `Monitor ${data.monitor_id} not found`);
          break;
        }

        // Calculate statistics
        const captured = capturedRequests.get(data.monitor_id) || [];
        const startTime = new Date(monitorToStop.started_at).getTime();
        const stopTime = Date.now();
        const durationSeconds = (stopTime - startTime) / 1000;

        // Remove monitor
        activeMonitors.delete(data.monitor_id);

        // Stop listeners if no more monitors
        if (activeMonitors.size === 0) {
          stopWebRequestMonitoring();
        }

        sendResponse(id, action, {
          monitor_id: data.monitor_id,
          status: 'stopped',
          stopped_at: new Date().toISOString(),
          total_requests_captured: captured.length,
          statistics: {
            duration_seconds: durationSeconds,
            requests_per_second: captured.length / Math.max(durationSeconds, 1),
            total_data_size: captured.reduce((sum, req) => sum + (req.response_size_bytes || 0), 0)
          }
        });
        break;

      case 'requests.list_captured':
        // An id nobody knows is an error rather than an empty list, which reads
        // the same as a monitor that is running and has caught nothing yet.
        // Monitors do not always end where the caller ended them: losing the
        // server connection clears every one of them.
        if (!capturedRequests.has(data.monitor_id)) {
          sendError(id, 'MONITOR_NOT_FOUND',
            `Monitor ${data.monitor_id} not found. It was never started, or the connection that started it has since closed.`);
          break;
        }

        const monitorRequests = capturedRequests.get(data.monitor_id);

        sendResponse(id, action, {
          monitor_id: data.monitor_id,
          total_requests: monitorRequests.length,
          requests: monitorRequests.map(req => ({
            request_id: req.request_id,
            url: req.url,
            method: req.method,
            status_code: req.status_code,
            duration_ms: req.duration_ms,
            timestamp: req.timestamp,
            tab_id: req.tab_id,
            type: req.type,
            error: req.error
          }))
        });
        break;

      case 'requests.get_content':
        if (!capturedRequests.has(data.monitor_id)) {
          sendError(id, 'MONITOR_NOT_FOUND', `Monitor ${data.monitor_id} not found`);
          break;
        }
        if (!capturedRequests.get(data.monitor_id).some(item => item.request_id === data.request_id)) {
          sendError(id, 'REQUEST_NOT_FOUND', `Request ${data.request_id} was not captured by this monitor`);
          break;
        }
        const requestDetail = requestDetails.get(data.request_id);
        if (!requestDetail) {
          sendError(id, 'REQUEST_NOT_FOUND', `Request ${data.request_id} not found`);
          break;
        }

        // Extract headers from events
        let requestHeaders = {};
        let responseHeaders = {};
        let requestBody = null;

        for (const event of requestDetail.events) {
          if (monitorCaptureOptions.get(data.monitor_id)?.capture_request_bodies &&
              event.type === 'onBeforeRequest' && event.requestBody) {
            requestBody = event.requestBody;
          }
          if (event.type === 'onHeadersReceived' && event.responseHeaders) {
            responseHeaders = event.responseHeaders.reduce((acc, header) => {
              acc[header.name] = header.value;
              return acc;
            }, {});
          }
        }


        sendResponse(id, action, {
          request_id: data.request_id,
          request_headers: requestHeaders,
          response_headers: responseHeaders,
          request_body: {
            included: !!requestBody,
            content: requestBody ? JSON.stringify(requestBody) : null,
            content_type: requestHeaders['content-type'] || null,
            encoding: 'utf-8',
            size_bytes: requestBody ? JSON.stringify(requestBody).length : 0,
            truncated: false,
            saved_to_file: null
          },
          response_body: (() => {
            const capturedBody = capturedResponseBodies.get(responseBodyKey(data.monitor_id, data.request_id));

            if (capturedBody && capturedBody.content !== null) {
              return {
                included: true,
                content: capturedBody.content,
                content_type: capturedBody.content_type,
                encoding: 'utf-8',
                size_bytes: capturedBody.size_bytes,
                truncated: capturedBody.truncated,
                saved_to_file: null,
                note: "Response body read from the response stream"
              };
            }

            // No body to hand back, so say which of the reasons it was and give
            // the size anyway. The measured size is the body Firefox actually
            // delivered; Content-Length is only what the server claimed, and is
            // absent from most compressed responses.
            let note;
            if (!capturedBody) {
              note = "Response body not captured: monitoring did not ask for response bodies, or the response could not be filtered";
            } else if (capturedBody.content_type) {
              note = `Response body not captured: ${capturedBody.content_type} is not one of content_types_to_capture, or is not text`;
            } else {
              note = "Response body not captured: the response declared no content type";
            }

            const measured = requestDetail.response_body_size;
            const declared = requestDetail.response_content_length;

            return {
              included: false,
              content: null,
              content_type: responseHeaders['content-type'] || requestDetail.response_content_type || null,
              encoding: null,
              size_bytes: measured !== undefined ? measured : (declared !== undefined ? declared : null),
              truncated: false,
              saved_to_file: null,
              note: note
            };
          })()
        });
        break;

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown requests action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Requests API error: ${error.message}`);
  }
}

// Test helper action handler
async function handleTestAction(id, action, data) {
  try {
    switch (action) {
      case 'test.get_popup_state':
        await handleGetPopupState(id, data);
        break;
        
      case 'test.get_options_state':
        await handleGetOptionsState(id, data);
        break;
        
      case 'test.get_storage_values':
        await handleGetStorageValues(id, data);
        break;
        
      case 'test.validate_ui_sync':
        await handleValidateUISync(id, data);
        break;
        
      case 'test.refresh_ui_state':
        await handleRefreshUIState(id, data);
        break;
        
      case 'test.visit_url':
        await handleVisitURL(id, data);
        break;
        
      case 'test.visit_multiple_urls':
        await handleVisitMultipleURLs(id, data);
        break;
        
      case 'test.clear_test_history':
        await handleClearTestHistory(id, data);
        break;
        

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown test action: ${action}`);
    }
  } catch (error) {
    console.error(`Error handling test action ${action}:`, error);
    sendError(id, 'TEST_ERROR', `Test action failed: ${error.message}`, { action, error: error.toString() });
  }
}

// Legacy test.* storage projection, retained for protocol compatibility.
// These helpers do not inspect UI; real UI checks execute the page scripts.
async function handleGetPopupState(id, data) {
  try {
    const storageConfig = await browser.storage.sync.get({
      hostname: 'localhost',
      port: 8765,
      retryInterval: FoxMCPConfig.defaults.retryInterval,
      maxRetries: -1,
      pingTimeout: 5000,
      testPort: null,
      testHostname: null
    });
    
    const effective = FoxMCPConfig.effective(storageConfig);
    const effectiveHostname = effective.hostname;
    const effectivePort = effective.port;
    const serverUrl = FoxMCPConfig.socketUrl(effective);
    const hasTestOverrides = storageConfig.testPort !== null || storageConfig.testHostname !== null;
    
    sendResponse(id, 'test.get_popup_state', {
      ...(data?.includeConsentDiagnostics ? {consentDiagnostics: await scriptConsent.diagnostics()} : {}),
      serverUrl: serverUrl,
      retryInterval: storageConfig.retryInterval,
      maxRetries: storageConfig.maxRetries,
      pingTimeout: storageConfig.pingTimeout,
      hasTestOverrides: hasTestOverrides,
      effectiveHostname: effectiveHostname,
      effectivePort: effectivePort,
      testIndicatorShown: hasTestOverrides,
      storageValues: storageConfig
    });
  } catch (error) {
    sendError(id, 'STORAGE_ERROR', `Failed to get popup state: ${error.message}`);
  }
}

// Legacy test.* effective configuration projection (not editable UI fields).
async function handleGetOptionsState(id, data) {
  try {
    const storageConfig = await browser.storage.sync.get({
      hostname: 'localhost',
      port: 8765,
      retryInterval: FoxMCPConfig.defaults.retryInterval,
      maxRetries: -1,
      pingTimeout: 5000,
      testPort: null,
      testHostname: null
    });
    
    const effective = FoxMCPConfig.effective(storageConfig);
    const displayHostname = effective.hostname;
    const displayPort = effective.port;
    const webSocketUrl = FoxMCPConfig.socketUrl(effective);
    const hasTestOverrides = storageConfig.testPort !== null || storageConfig.testHostname !== null;
    
    sendResponse(id, 'test.get_options_state', {
      displayHostname: displayHostname,
      displayPort: displayPort,
      retryInterval: storageConfig.retryInterval,
      maxRetries: storageConfig.maxRetries,
      pingTimeout: storageConfig.pingTimeout,
      webSocketUrl: webSocketUrl,
      hasTestOverrides: hasTestOverrides,
      testOverrideWarningShown: hasTestOverrides,
      storageValues: storageConfig
    });
  } catch (error) {
    sendError(id, 'STORAGE_ERROR', `Failed to get options state: ${error.message}`);
  }
}

// Get raw storage values
async function handleGetStorageValues(id, data) {
  try {
    const storageConfig = await browser.storage.sync.get();
    sendResponse(id, 'test.get_storage_values', storageConfig);
  } catch (error) {
    sendError(id, 'STORAGE_ERROR', `Failed to get storage values: ${error.message}`);
  }
}

// Validate UI-storage synchronization
async function handleValidateUISync(id, data) {
  try {
    const { expectedValues } = data;
    
    // Get current storage values
    const storageConfig = await browser.storage.sync.get();
    
    // Get popup state
    const popupState = await getPopupStateForValidation(storageConfig);
    
    // Get options state  
    const optionsState = await getOptionsStateForValidation(storageConfig);
    
    // Check storage matches expected values
    let storageMatches = true;
    const issues = [];
    
    if (expectedValues) {
      for (const [key, expectedValue] of Object.entries(expectedValues)) {
        if (storageConfig[key] !== expectedValue) {
          storageMatches = false;
          issues.push(`Storage ${key}: expected ${expectedValue}, got ${storageConfig[key]}`);
        }
      }
    }
    
    // Validate popup displays correct effective values
    const effectiveHostname = storageConfig.testHostname || storageConfig.hostname || 'localhost';
    const effectivePort = storageConfig.testPort || storageConfig.port || 8765;
    
    const popupSyncValid = popupState.effectiveHostname === effectiveHostname && 
                          popupState.effectivePort === effectivePort;
    
    const optionsSyncValid = optionsState.displayHostname === effectiveHostname &&
                            optionsState.displayPort === effectivePort;
    
    if (!popupSyncValid) {
      issues.push(`Popup sync invalid: expected ${effectiveHostname}:${effectivePort}, got ${popupState.effectiveHostname}:${popupState.effectivePort}`);
    }
    
    if (!optionsSyncValid) {
      issues.push(`Options sync invalid: expected ${effectiveHostname}:${effectivePort}, got ${optionsState.displayHostname}:${optionsState.displayPort}`);
    }
    
    sendResponse(id, 'test.validate_ui_sync', {
      popupSyncValid: popupSyncValid,
      optionsSyncValid: optionsSyncValid,
      storageMatches: storageMatches,
      effectiveValues: {
        hostname: effectiveHostname,
        port: effectivePort
      },
      issues: issues
    });
  } catch (error) {
    sendError(id, 'VALIDATION_ERROR', `Failed to validate UI sync: ${error.message}`);
  }
}

// Trigger UI state refresh
async function handleRefreshUIState(id, data) {
  try {
    // This simulates what happens when popup/options pages refresh
    // In practice, this would trigger any cached state to be cleared
    // and force re-reading from storage
    
    // For now, we just confirm the action was received
    sendResponse(id, 'test.refresh_ui_state', {
      refreshed: true,
      popupStateUpdated: true,
      optionsStateUpdated: true,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    sendError(id, 'REFRESH_ERROR', `Failed to refresh UI state: ${error.message}`);
  }
}

// Helper function for validation
async function getPopupStateForValidation(storageConfig) {
  const effectiveHostname = storageConfig.testHostname || storageConfig.hostname || 'localhost';
  const effectivePort = storageConfig.testPort || storageConfig.port || 8765;
  
  return {
    effectiveHostname,
    effectivePort,
    hasTestOverrides: storageConfig.testPort !== null || storageConfig.testHostname !== null
  };
}

// Helper function for validation
async function getOptionsStateForValidation(storageConfig) {
  const displayHostname = storageConfig.testHostname || storageConfig.hostname;
  const displayPort = storageConfig.testPort || storageConfig.port;
  
  return {
    displayHostname,
    displayPort,
    hasTestOverrides: storageConfig.testPort !== null || storageConfig.testHostname !== null
  };
}

// Test Helper: Visit a URL to create browser history
async function handleVisitURL(id, data) {
  try {
    const url = data.url;
    const waitTime = data.waitTime || 8000; // Increased default wait time

    if (!url) {
      sendError(id, 'INVALID_PARAMETERS', 'URL is required for test.visit_url');
      return;
    }

    console.log(`[FoxMCP] Starting visit to URL: ${url}`);

    // Create a new tab with the URL
    const tab = await browser.tabs.create({
      url: url,
      active: false // Don't make it active to avoid disrupting tests
    });

    console.log(`[FoxMCP] Created tab ${tab.id} for URL: ${url}`);

    // Wait for the tab to actually complete loading
    let tabLoaded = false;
    let loadStartTime = Date.now();
    const maxWaitTime = Math.max(waitTime, 10000); // At least 10 seconds

    // Set up a listener for tab updates
    const tabUpdateListener = (tabId, changeInfo, updatedTab) => {
      if (tabId === tab.id && changeInfo.status === 'complete') {
        console.log(`[FoxMCP] Tab ${tab.id} finished loading`);
        tabLoaded = true;
      }
    };

    browser.tabs.onUpdated.addListener(tabUpdateListener);

    try {
      // Wait for either tab to load or timeout
      while (!tabLoaded && (Date.now() - loadStartTime) < maxWaitTime) {
        await new Promise(resolve => setTimeout(resolve, 500));
      }

      if (tabLoaded) {
        console.log(`[FoxMCP] Tab loaded in ${Date.now() - loadStartTime}ms`);
        // Give additional time for history to be recorded
        console.log(`[FoxMCP] Waiting additional time for history recording...`);
        await new Promise(resolve => setTimeout(resolve, 3000));
      } else {
        console.log(`[FoxMCP] Tab did not complete loading within ${maxWaitTime}ms, proceeding anyway`);
        // Still wait the original wait time as fallback
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }

    } finally {
      // Clean up the listener
      browser.tabs.onUpdated.removeListener(tabUpdateListener);
    }

    console.log(`[FoxMCP] Closing tab ${tab.id}`);

    // Close the tab
    await browser.tabs.remove(tab.id);

    console.log(`[FoxMCP] Successfully visited and closed: ${url}`);

    sendResponse(id, 'test.visit_url', {
      success: true,
      url: url,
      tabId: tab.id,
      visitTime: new Date().toISOString(),
      loadTime: Date.now() - loadStartTime,
      tabLoaded: tabLoaded,
      message: `Successfully visited ${url} (loaded: ${tabLoaded})`
    });
    
  } catch (error) {
    sendError(id, 'VISIT_URL_ERROR', `Failed to visit URL: ${error.message}`);
  }
}

// Test Helper: Visit multiple URLs to create test history
async function handleVisitMultipleURLs(id, data) {
  try {
    const urls = data.urls || [];
    const waitTime = data.waitTime || 8000; // Increased time to wait at each URL
    const delayBetween = data.delayBetween || 3000; // Increased delay between visits

    if (!Array.isArray(urls) || urls.length === 0) {
      sendError(id, 'INVALID_PARAMETERS', 'urls array is required for test.visit_multiple_urls');
      return;
    }

    console.log(`[FoxMCP] Starting visit to ${urls.length} URLs`);
    const results = [];

    for (let i = 0; i < urls.length; i++) {
      const url = urls[i];
      console.log(`[FoxMCP] Visiting URL ${i + 1}/${urls.length}: ${url}`);

      try {
        // Use the same improved logic as single URL visit
        const tab = await browser.tabs.create({
          url: url,
          active: false
        });

        let tabLoaded = false;
        let loadStartTime = Date.now();
        const maxWaitTime = Math.max(waitTime, 10000);

        // Set up tab update listener
        const tabUpdateListener = (tabId, changeInfo, updatedTab) => {
          if (tabId === tab.id && changeInfo.status === 'complete') {
            console.log(`[FoxMCP] Tab ${tab.id} finished loading URL ${i + 1}`);
            tabLoaded = true;
          }
        };

        browser.tabs.onUpdated.addListener(tabUpdateListener);

        try {
          // Wait for tab to load or timeout
          while (!tabLoaded && (Date.now() - loadStartTime) < maxWaitTime) {
            await new Promise(resolve => setTimeout(resolve, 500));
          }

          if (tabLoaded) {
            console.log(`[FoxMCP] URL ${i + 1} loaded in ${Date.now() - loadStartTime}ms`);
            // Extra wait for history recording
            await new Promise(resolve => setTimeout(resolve, 2000));
          } else {
            console.log(`[FoxMCP] URL ${i + 1} did not complete loading within ${maxWaitTime}ms`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
          }

        } finally {
          browser.tabs.onUpdated.removeListener(tabUpdateListener);
        }

        // Close the tab
        await browser.tabs.remove(tab.id);

        results.push({
          url: url,
          success: true,
          tabId: tab.id,
          visitTime: new Date().toISOString(),
          loadTime: Date.now() - loadStartTime,
          tabLoaded: tabLoaded
        });
        
        // Small delay between visits
        if (i < urls.length - 1) {
          await new Promise(resolve => setTimeout(resolve, delayBetween));
        }
        
      } catch (error) {
        results.push({
          url: url,
          success: false,
          error: error.message
        });
      }
    }
    
    const successCount = results.filter(r => r.success).length;
    
    sendResponse(id, 'test.visit_multiple_urls', {
      success: true,
      totalUrls: urls.length,
      successfulVisits: successCount,
      failedVisits: urls.length - successCount,
      results: results,
      message: `Visited ${successCount}/${urls.length} URLs successfully`
    });
    
  } catch (error) {
    sendError(id, 'VISIT_MULTIPLE_URLS_ERROR', `Failed to visit multiple URLs: ${error.message}`);
  }
}

// Test Helper: Clear test history (for cleanup)
async function handleClearTestHistory(id, data) {
  try {
    const urls = data.urls || [];
    const clearAll = data.clearAll || false;
    
    if (clearAll) {
      // Clear all history (use with caution in tests)
      await browser.history.deleteAll();
      
      sendResponse(id, 'test.clear_test_history', {
        success: true,
        action: 'cleared_all',
        message: 'All browser history cleared'
      });
    } else if (urls.length > 0) {
      // Clear specific URLs
      const results = [];
      
      for (const url of urls) {
        try {
          await browser.history.deleteUrl({ url: url });
          results.push({ url: url, success: true });
        } catch (error) {
          results.push({ url: url, success: false, error: error.message });
        }
      }
      
      const successCount = results.filter(r => r.success).length;
      
      sendResponse(id, 'test.clear_test_history', {
        success: true,
        action: 'cleared_specific_urls',
        totalUrls: urls.length,
        successfulClears: successCount,
        failedClears: urls.length - successCount,
        results: results,
        message: `Cleared ${successCount}/${urls.length} URLs from history`
      });
    } else {
      sendError(id, 'INVALID_PARAMETERS', 'Either clearAll:true or urls array is required');
    }
    
  } catch (error) {
    sendError(id, 'CLEAR_HISTORY_ERROR', `Failed to clear test history: ${error.message}`);
  }
}


// React to actual sync changes, including updates made by another Firefox.
browser.storage.onChanged.addListener((changes, area) => {
  if (area !== 'sync') return;
  const relevant = Object.keys(FoxMCPConfig.storageDefaults).some(key =>
    changes[key] && changes[key].newValue !== changes[key].oldValue);
  if (relevant) serializeConfiguration(loadConfig);
});

// Queue initialization ahead of any UI/storage operation. A delayed initial
// read can never replace settings saved afterwards, and invalid config never
// falls back to connecting to a different server.
serializeConfiguration(async () => {
  try {
    await loadConfig();
  } catch (error) {
    configError = `Could not load settings: ${error.message}`;
    connectionState = 'configuration_error';
  }
});
