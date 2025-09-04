let websocket = null;
let isConnected = false;

// Default configuration - will be loaded from storage
let CONFIG = {
  hostname: 'localhost',
  port: 8765,
  retryInterval: 5000, // milliseconds (5 seconds default)
  maxRetries: -1, // -1 for infinite retries, or set a number
  pingTimeout: 5000 // ping timeout in milliseconds
};

// Computed WebSocket URL
let WS_URL = `ws://${CONFIG.hostname}:${CONFIG.port}`;

let retryAttempts = 0;

function connectToMCPServer() {
  try {
    console.log(`Attempting to connect to ${WS_URL} (attempt ${retryAttempts + 1})`);
    websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
      console.log('Connected to MCP server');
      isConnected = true;
      retryAttempts = 0; // Reset retry counter on successful connection
    };

    websocket.onmessage = async (event) => {
      await handleMessage(JSON.parse(event.data));
    };

    websocket.onclose = () => {
      console.log('Disconnected from MCP server');
      isConnected = false;
      scheduleReconnect();
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  } catch (error) {
    console.error('Failed to connect to MCP server:', error);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  retryAttempts++;

  // Check if we've exceeded max retry attempts
  if (CONFIG.maxRetries > 0 && retryAttempts > CONFIG.maxRetries) {
    console.error(`Max retry attempts (${CONFIG.maxRetries}) exceeded. Stopping reconnection attempts.`);
    return;
  }

  console.log(`Scheduling reconnection attempt ${retryAttempts} in ${CONFIG.retryInterval}ms`);
  setTimeout(connectToMCPServer, CONFIG.retryInterval);
}

// Function to update configuration (can be called from popup or other scripts)
function updateConfig(newConfig) {
  Object.assign(CONFIG, newConfig);
  console.log('Configuration updated:', CONFIG);

  // Update WebSocket URL
  WS_URL = `ws://${CONFIG.hostname}:${CONFIG.port}`;

  // Save to storage for persistence
  browser.storage.sync.set({
    hostname: CONFIG.hostname,
    port: CONFIG.port,
    retryInterval: CONFIG.retryInterval,
    maxRetries: CONFIG.maxRetries,
    pingTimeout: CONFIG.pingTimeout
  });

  // Reconnect with new settings if currently connected
  if (isConnected || websocket) {
    console.log('Reconnecting with new configuration...');
    disconnect();
    connectToMCPServer();
  }
}

// Load configuration from storage on startup
async function loadConfig() {
  try {
    // Load from storage with defaults, including test overrides
    const result = await browser.storage.sync.get({
      hostname: 'localhost',
      port: 8765,
      retryInterval: 5000,
      maxRetries: -1,
      pingTimeout: 5000,
      // Test configuration overrides (set by test framework)
      testPort: null,
      testHostname: null
    });

    // Apply configuration with test overrides taking priority
    CONFIG.hostname = result.testHostname || result.hostname;
    CONFIG.port = result.testPort || result.port;
    CONFIG.retryInterval = result.retryInterval;
    CONFIG.maxRetries = result.maxRetries;
    CONFIG.pingTimeout = result.pingTimeout;

    // Update WebSocket URL with loaded configuration
    WS_URL = `ws://${CONFIG.hostname}:${CONFIG.port}`;

    console.log('Configuration loaded:', CONFIG);
    console.log('WebSocket URL:', WS_URL);

    if (result.testPort || result.testHostname) {
      console.log('Using test configuration overrides:', {
        testPort: result.testPort,
        testHostname: result.testHostname
      });
    }
  } catch (error) {
    console.error('Error loading configuration:', error);
  }
}

// Disconnect function
function disconnect() {
  if (websocket) {
    websocket.close();
    websocket = null;
  }
  isConnected = false;
}

async function handleMessage(message) {
  const { id, type, action, data } = message;

  if (type !== 'request') return;

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
    case 'tabs':
      await handleTabsAction(id, action, data);
      break;
    case 'content':
      await handleContentAction(id, action, data);
      break;
    case 'navigation':
      await handleNavigationAction(id, action, data);
      break;
    case 'bookmarks':
      await handleBookmarksAction(id, action, data);
      break;
    default:
      sendError(id, 'UNKNOWN_ACTION', `Unknown action: ${action}`);
  }
}

function sendResponse(id, action, data) {
  if (!isConnected) return;

  const message = {
    id,
    type: 'response',
    action,
    data,
    timestamp: new Date().toISOString()
  };

  websocket.send(JSON.stringify(message));
}

function sendError(id, code, message, details = {}) {
  if (!isConnected) return;

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

  websocket.send(JSON.stringify(errorMessage));
}

// Handle popup requests for connection status
browser.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getConnectionStatus') {
    sendResponse({
      connected: isConnected,
      retryAttempts: retryAttempts,
      config: CONFIG
    });
    return true;
  }

  // Handle options page configuration updates
  if (request.type === 'configUpdated') {
    updateConfig(request.config);
    sendResponse({ success: true });
    return true;
  }

  // Handle advanced configuration updates
  if (request.type === 'advancedConfigUpdated') {
    updateConfig(request.config);
    sendResponse({ success: true });
    return true;
  }

  // Handle connection test from options page
  if (request.type === 'testConnection') {
    testPingPong().then(result => {
      sendResponse(result);
    }).catch(error => {
      sendResponse({ success: false, error: error.message });
    });
    return true; // Keep message channel open for async response
  }

  // Handle connection status request from options page
  if (request.type === 'getConnectionStatus') {
    sendResponse({ connected: isConnected });
    return true;
  }

  if (request.action === 'testPing') {
    testPingPong().then(result => {
      sendResponse(result);
    }).catch(error => {
      sendResponse({ success: false, error: error.message });
    });
    return true; // Keep channel open for async response
  }

  if (request.action === 'updateConfig') {
    updateConfig(request.config);
    sendResponse({ success: true, config: CONFIG });
    return true;
  }

  if (request.action === 'forceReconnect') {
    if (websocket) {
      websocket.close();
    }
    retryAttempts = 0;
    connectToMCPServer();
    sendResponse({ success: true });
    return true;
  }
});

// Test ping-pong functionality
async function testPingPong() {
  if (!isConnected) {
    return { success: false, error: 'Not connected to server' };
  }

  const testId = `ping_test_${Date.now()}`;
  const pingMessage = {
    id: testId,
    type: 'request',
    action: 'ping',
    data: { test: true },
    timestamp: new Date().toISOString()
  };

  return new Promise((resolve, reject) => {
    // Set up response handler
    const originalHandler = websocket.onmessage;
    const timeout = setTimeout(() => {
      websocket.onmessage = originalHandler;
      reject(new Error('Ping timeout'));
    }, CONFIG.PING_TIMEOUT);

    websocket.onmessage = (event) => {
      const response = JSON.parse(event.data);
      if (response.id === testId && response.type === 'response') {
        clearTimeout(timeout);
        websocket.onmessage = originalHandler;
        resolve({ success: true, response });
      } else {
        // Pass other messages to original handler
        originalHandler(event);
      }
    };

    // Send ping
    websocket.send(JSON.stringify(pingMessage));
  });
}

// History handlers
async function handleHistoryAction(id, action, data) {
  try {
    switch (action) {
      case 'history.query':
        const historyItems = await browser.history.search({
          text: data.text || '',
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

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown history action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `History API error: ${error.message}`);
  }
}

// Tabs handlers
async function handleTabsAction(id, action, data) {
  try {
    switch (action) {
      case 'tabs.list':
        const tabs = await browser.tabs.query({
          currentWindow: data.currentWindow || false
        });
        sendResponse(id, action, { tabs });
        break;

      case 'tabs.active':
        const [activeTab] = await browser.tabs.query({ active: true, currentWindow: true });
        sendResponse(id, action, { tab: activeTab });
        break;

      case 'tabs.create':
        const newTab = await browser.tabs.create({
          url: data.url,
          active: data.active || false
        });
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

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown tabs action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Tabs API error: ${error.message}`);
  }
}

// Content handlers
async function handleContentAction(id, action, data) {
  try {
    switch (action) {
      case 'content.text':
        const textResult = await browser.tabs.sendMessage(data.tabId, {
          action: 'extractText'
        });
        sendResponse(id, action, { text: textResult.text });
        break;

      case 'content.html':
        const htmlResult = await browser.tabs.sendMessage(data.tabId, {
          action: 'extractHTML'
        });
        sendResponse(id, action, { html: htmlResult.html });
        break;

      case 'content.execute':
        const executeResult = await browser.tabs.sendMessage(data.tabId, {
          action: 'executeScript',
          script: data.script
        });
        sendResponse(id, action, { result: executeResult });
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
      case 'navigation.go':
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
async function handleBookmarksAction(id, action, data) {
  try {
    switch (action) {
      case 'bookmarks.list':
        const bookmarks = await browser.bookmarks.getTree();
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

      case 'bookmarks.remove':
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

// Start connection when extension loads
browser.runtime.onStartup.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

browser.runtime.onInstalled.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

// Initialize and connect immediately
(async () => {
  await loadConfig();
  connectToMCPServer();
})();