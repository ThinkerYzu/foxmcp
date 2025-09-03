let websocket = null;
let isConnected = false;

// Configuration - make these configurable
const CONFIG = {
  WS_URL: 'ws://localhost:8765',
  RETRY_INTERVAL: 5000, // milliseconds (5 seconds default)
  MAX_RETRY_ATTEMPTS: -1, // -1 for infinite retries, or set a number
  PING_TIMEOUT: 5000 // ping timeout in milliseconds
};

let retryAttempts = 0;

function connectToMCPServer() {
  try {
    console.log(`Attempting to connect to ${CONFIG.WS_URL} (attempt ${retryAttempts + 1})`);
    websocket = new WebSocket(CONFIG.WS_URL);
    
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
  if (CONFIG.MAX_RETRY_ATTEMPTS > 0 && retryAttempts > CONFIG.MAX_RETRY_ATTEMPTS) {
    console.error(`Max retry attempts (${CONFIG.MAX_RETRY_ATTEMPTS}) exceeded. Stopping reconnection attempts.`);
    return;
  }
  
  console.log(`Scheduling reconnection attempt ${retryAttempts} in ${CONFIG.RETRY_INTERVAL}ms`);
  setTimeout(connectToMCPServer, CONFIG.RETRY_INTERVAL);
}

// Function to update configuration (can be called from popup or other scripts)
function updateConfig(newConfig) {
  Object.assign(CONFIG, newConfig);
  console.log('Configuration updated:', CONFIG);
  
  // Save to storage for persistence
  chrome.storage.local.set({ foxmcpConfig: CONFIG });
}

// Load configuration from storage on startup
async function loadConfig() {
  try {
    const result = await chrome.storage.local.get(['foxmcpConfig']);
    if (result.foxmcpConfig) {
      Object.assign(CONFIG, result.foxmcpConfig);
      console.log('Configuration loaded from storage:', CONFIG);
    }
  } catch (error) {
    console.error('Error loading configuration:', error);
  }
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
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getConnectionStatus') {
    sendResponse({ 
      connected: isConnected, 
      retryAttempts: retryAttempts,
      config: CONFIG 
    });
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
        const historyItems = await chrome.history.search({
          text: data.text || '',
          startTime: data.startTime || 0,
          endTime: data.endTime || Date.now(),
          maxResults: data.maxResults || 100
        });
        sendResponse(id, action, { items: historyItems });
        break;
        
      case 'history.recent':
        const recentItems = await chrome.history.search({
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
        const tabs = await chrome.tabs.query({
          currentWindow: data.currentWindow || false
        });
        sendResponse(id, action, { tabs });
        break;
        
      case 'tabs.active':
        const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
        sendResponse(id, action, { tab: activeTab });
        break;
        
      case 'tabs.create':
        const newTab = await chrome.tabs.create({
          url: data.url,
          active: data.active || false
        });
        sendResponse(id, action, { tab: newTab });
        break;
        
      case 'tabs.close':
        await chrome.tabs.remove(data.tabId);
        sendResponse(id, action, { success: true });
        break;
        
      case 'tabs.update':
        const updatedTab = await chrome.tabs.update(data.tabId, {
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
        const textResult = await chrome.tabs.sendMessage(data.tabId, {
          action: 'extractText'
        });
        sendResponse(id, action, { text: textResult.text });
        break;
        
      case 'content.html':
        const htmlResult = await chrome.tabs.sendMessage(data.tabId, {
          action: 'extractHTML'
        });
        sendResponse(id, action, { html: htmlResult.html });
        break;
        
      case 'content.execute':
        const executeResult = await chrome.tabs.sendMessage(data.tabId, {
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
        await chrome.tabs.update(data.tabId, { url: data.url });
        sendResponse(id, action, { success: true });
        break;
        
      case 'navigation.back':
        await chrome.tabs.goBack(data.tabId);
        sendResponse(id, action, { success: true });
        break;
        
      case 'navigation.forward':
        await chrome.tabs.goForward(data.tabId);
        sendResponse(id, action, { success: true });
        break;
        
      case 'navigation.reload':
        await chrome.tabs.reload(data.tabId, { bypassCache: data.bypassCache || false });
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
        const bookmarks = await chrome.bookmarks.getTree();
        sendResponse(id, action, { bookmarks });
        break;
        
      case 'bookmarks.search':
        const searchResults = await chrome.bookmarks.search(data.query);
        sendResponse(id, action, { bookmarks: searchResults });
        break;
        
      case 'bookmarks.create':
        const newBookmark = await chrome.bookmarks.create({
          parentId: data.parentId,
          title: data.title,
          url: data.url
        });
        sendResponse(id, action, { bookmark: newBookmark });
        break;
        
      case 'bookmarks.remove':
        await chrome.bookmarks.remove(data.bookmarkId);
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
chrome.runtime.onStartup.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

chrome.runtime.onInstalled.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

// Initialize and connect immediately
(async () => {
  await loadConfig();
  connectToMCPServer();
})();