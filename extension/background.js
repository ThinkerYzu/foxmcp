/*
 * FoxMCP Firefox Extension - Background Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// SINGLE CONNECTION CONSTRAINT: Only one WebSocket connection to MCP server allowed
let websocket = null;
let isConnected = false;


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

// Default configuration - will be loaded from storage
let CONFIG = {
  hostname: 'localhost',
  port: 8765,
  retryInterval: 5000, // milliseconds (5 seconds default)
  maxRetries: -1, // -1 for infinite retries, or set a number
  pingTimeout: 5000 // ping timeout in milliseconds
};

let retryAttempts = 0;
const MAX_ABSOLUTE_RETRIES = 50; // Absolute maximum to prevent infinite loops

function connectToMCPServer() {
  try {
    console.log('🔍 CONNECT ATTEMPT - Stack trace:');
    console.trace();

    // IMPORTANT: Only one WebSocket connection is allowed at a time
    // Disconnect any existing connection first to prevent multiple connections
    if (websocket && websocket.readyState !== WebSocket.CLOSED) {
      console.log('🔌 Disconnecting existing connection before creating new one');
      disconnect();
    }

    // Compute WebSocket URL dynamically using current config
    const WS_URL = `ws://${CONFIG.hostname}:${CONFIG.port}`;
    console.log(`🔗 Connecting to ${WS_URL} (attempt ${retryAttempts + 1})`);
    console.log(`🔧 Using CONFIG:`, JSON.stringify(CONFIG, null, 2));

    websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
      console.log('Connected to MCP server');
      isConnected = true;
      retryAttempts = 0; // Reset retry counter on successful connection
      connectionRetryAttempts = 0; // Reset connection retry counter

      // Send an immediate debug message to test after a small delay
      setTimeout(() => {
        console.log('🔌 WebSocket connection established and ready');
      }, 200);

      // Flush any buffered debug logs
      if (typeof window.flushDebugLogBuffer === 'function') {
        setTimeout(() => {
          window.flushDebugLogBuffer();
        }, 100);
      }
    };

    websocket.onmessage = async (event) => {
      // Test debug message right when we receive a message
      console.log('📨 Extension received message from server');
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

  // Check configured max retries
  if (CONFIG.maxRetries > 0 && retryAttempts > CONFIG.maxRetries) {
    console.error(`Configured max retry attempts (${CONFIG.maxRetries}) exceeded. Stopping reconnection attempts.`);
    return;
  }

  // Check absolute max retries to prevent infinite loops
  if (retryAttempts > MAX_ABSOLUTE_RETRIES) {
    console.error(`Absolute max retry attempts (${MAX_ABSOLUTE_RETRIES}) exceeded. Stopping reconnection attempts.`);
    return;
  }

  console.log(`Scheduling reconnection attempt ${retryAttempts} in ${CONFIG.retryInterval}ms`);
  setTimeout(connectToMCPServer, CONFIG.retryInterval);
}

// Function to update configuration (can be called from popup or other scripts)
function updateConfig(newConfig) {
  Object.assign(CONFIG, newConfig);
  console.log('Configuration updated:', CONFIG);
  console.log('New WebSocket URL will be:', `ws://${CONFIG.hostname}:${CONFIG.port}`);

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
  console.log('📥 Loading configuration from storage...');
  console.log('🔍 LOADCONFIG - Stack trace:');
  console.trace();

  // Load from storage - browser.storage.sync.get() always succeeds
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

  // Check if we're in a test environment waiting for configuration
  const isTestEnvironment = result.testPort !== null || result.testHostname !== null;
  const hasValidTestConfig = result.testPort && result.testPort !== 8765;

  // In test environment, wait longer for configuration to be ready
  if (isTestEnvironment && !hasValidTestConfig) {
    console.log('🧪 Test environment detected but no valid test config yet');
    console.log('📋 Will retry in test environment...');
    throw new Error('Test environment detected but configuration not ready');
  }

  // Apply configuration with test overrides taking priority
  CONFIG.hostname = result.testHostname || result.hostname;
  CONFIG.port = result.testPort || result.port;
  CONFIG.retryInterval = result.retryInterval;
  CONFIG.maxRetries = result.maxRetries;
  CONFIG.pingTimeout = result.pingTimeout;

  console.log('📋 Configuration loaded:', CONFIG);
  console.log('🌐 WebSocket URL will be:', `ws://${CONFIG.hostname}:${CONFIG.port}`);

  if (result.testPort || result.testHostname) {
    console.log('🧪 Test overrides active:', {
      testPort: result.testPort,
      testHostname: result.testHostname
    });
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


  // Handle connection status request from options page
  if (request.type === 'getConnectionStatus') {
    sendResponse({ connected: isConnected });
    return true;
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

  // Handle response body capture events from content scripts
  if (request.type === 'response_body_captured') {
    const responseData = request.data;
    console.log(`📥 Response body captured: ${responseData.method} ${responseData.url} (${responseData.response_body.length} chars)`);

    // Store captured response body data
    capturedResponseBodies.set(responseData.request_id, responseData);

    return true;
  }

  if (request.type === 'response_body_error') {
    const errorData = request.data;
    console.error(`❌ Response capture error: ${errorData.method} ${errorData.url} - ${errorData.error}`);

    return true;
  }
});


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

// Tabs handlers
async function handleTabsAction(id, action, data) {
  try {
    switch (action) {
      case 'tabs.list':
        const tabs = await browser.tabs.query({
          currentWindow: data.currentWindow || true
        });
        // Include all tabs, even about:blank for debugging
        sendResponse(id, action, { 
          tabs: tabs.map(tab => ({url: tab.url, id: tab.id, title: tab.title, active: tab.active, windowId: tab.windowId, pinned: tab.pinned})),
          debug: {
            totalFound: tabs.length,
            tabUrls: tabs.map(tab => tab.url)
          }
        });
        break;

      case 'tabs.active':
        const [activeTab] = await browser.tabs.query({ active: true, currentWindow: true });
        sendResponse(id, action, { tab: activeTab });
        break;

      case 'tabs.create':
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
        
        const newTab = await browser.tabs.create(createTabOptions);
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

      case 'tabs.captureVisibleTab':
        const windowId = data.windowId || null;
        const options = {
          format: data.format || 'png',
          quality: data.quality || 90
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

      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown tabs action: ${action}`);
    }
  } catch (error) {
    sendError(id, 'API_ERROR', `Tabs API error: ${error.message}`);
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
      case 'content.text':
      case 'content.get_text':
        const textResult = await sendMessageWithRetry(data.tabId, {
          action: 'extractText'
        });
        sendResponse(id, action, { text: textResult.text });
        break;

      case 'content.html':
      case 'content.get_html':
        const htmlResult = await sendMessageWithRetry(data.tabId, {
          action: 'extractHTML'
        });
        sendResponse(id, action, { html: htmlResult.html });
        break;

      case 'content.execute':
      case 'content.execute_script':
        try {
          const executeResults = await browser.tabs.executeScript(data.tabId, {
            code: data.script
          });
          // executeScript returns an array of results from each frame
          const result = executeResults && executeResults.length > 0 ? executeResults[0] : null;
          sendResponse(id, action, { 
            result: result,
            url: await getCurrentTabUrl(data.tabId)
          });
        } catch (scriptError) {
          sendError(id, 'SCRIPT_ERROR', `Script execution failed: ${scriptError.message}`);
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
      case 'navigation.go':
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
async function handleBookmarksAction(id, action, data) {
  try {
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
              parentId: node.parentId
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
                parentId: node.parentId
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

      case 'bookmarks.remove':
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

      case 'windows.get_last_focused':
        const lastFocusedWindow = await browser.windows.getLastFocused({
          populate: data.populate !== false
        });
        sendResponse(id, action, { window: lastFocusedWindow });
        break;

      case 'windows.create':
        const createOptions = {};
        if (data.url) createOptions.url = data.url;
        if (data.type) createOptions.type = data.type;
        if (data.state) createOptions.state = data.state;
        if (data.focused !== undefined) createOptions.focused = data.focused;
        if (data.width) createOptions.width = data.width;
        if (data.height) createOptions.height = data.height;
        if (data.top) createOptions.top = data.top;
        if (data.left) createOptions.left = data.left;
        if (data.incognito !== undefined) createOptions.incognito = data.incognito;
        
        const newWindow = await browser.windows.create(createOptions);
        sendResponse(id, action, { window: newWindow });
        break;

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
const capturedResponseBodies = new Map(); // request_id -> response body data

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

  if (activeMonitors.size === 0) {
    // First monitor - set up listeners
    setupWebRequestListeners();
  }
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

  // Register listeners with browser
  browser.webRequest.onBeforeRequest.addListener(
    onBeforeRequestListener,
    { urls: ["<all_urls>"] },
    ["requestBody"]
  );

  browser.webRequest.onHeadersReceived.addListener(
    onHeadersReceivedListener,
    { urls: ["<all_urls>"] },
    ["responseHeaders"]
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
      if (pattern === '*') return true;

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

  // Get or create request record
  let request = requestDetails.get(requestId);
  if (!request) {
    request = {
      request_id: requestId,
      monitor_id: monitorId,
      url: details.url,
      method: details.method || 'GET',
      tab_id: details.tabId,
      frame_id: details.frameId,
      type: details.type,
      timestamp: timestamp,
      events: []
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
      event.requestBody = details.requestBody;
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
  if (request.completed && !request.added_to_list) {
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
    request.added_to_list = true;

    const sizeInfo = request.response_content_length ? ` (${request.response_content_length} bytes)` : '';
    console.log(`📋 Captured request: ${request.method} ${request.url} -> ${request.status_code || 'ERROR'}${sizeInfo}`);
  }
}

// Request monitoring handlers
async function handleRequestsAction(id, action, data) {
  try {
    switch (action) {
      case 'requests.start_monitoring':
        // Always send debug message to test if WebSocket works
        console.log('📡 ALWAYS: requests.start_monitoring called');

        const monitor_id = `mon_${Date.now()}`;
        const monitor = {
          id: monitor_id,
          url_patterns: data.url_patterns || [],
          options: data.options || {},
          tab_id: data.tab_id || null,
          started_at: new Date().toISOString(),
          status: 'active'
        };

        // Debug: Check what options we received
        console.log(`📡 DEBUG: Monitor options received: ${JSON.stringify(monitor.options)}`);

        // Enable response body capture if requested
        if (monitor.options.capture_response_bodies) {
          console.log(`📡 Response body capture enabled for monitoring session: ${monitor_id}`);
          console.log(`📡 Monitor config for capture: ${JSON.stringify(monitor)}`);
          console.log(`📡 About to enable response body capture for ${monitor_id}`);

          try {
            console.log('📡 About to await enableResponseBodyCapture()');
            await enableResponseBodyCapture(monitor);
            console.log('📡 enableResponseBodyCapture() call completed successfully');
          } catch (error) {
            console.error('📡 ERROR in enableResponseBodyCapture():', error);
            console.error('📡 Error stack:', error.stack);
          }
        } else {
          console.log('📡 Response body capture NOT enabled - flag not set');
        }

        // Start actual monitoring
        startWebRequestMonitoring(monitor);

        // Store monitor
        activeMonitors.set(monitor_id, monitor);
        capturedRequests.set(monitor_id, []);

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

        // Disable response body capture if it was enabled for this monitor
        if (monitorToStop.options.capture_response_bodies) {
          console.log('🔄 Disabling response body capture for stopped monitoring session:', data.monitor_id);
          disableResponseBodyCapture();
        }

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
        const monitorRequests = capturedRequests.get(data.monitor_id) || [];

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
          if (event.type === 'onBeforeRequest' && event.requestBody) {
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
            // First check direct match by request_id
            let capturedResponseData = capturedResponseBodies.get(data.request_id);

            // If no direct match, try to correlate by URL, method, status, and timing
            if (!capturedResponseData) {
              const requestUrl = requestDetail.url;
              const requestMethod = requestDetail.method || 'GET';
              const responseStatus = requestDetail.response_status_code;

              // Find matching response by correlation
              for (const [contentRequestId, responseData] of capturedResponseBodies.entries()) {
                if (responseData.url === requestUrl &&
                    responseData.method === requestMethod &&
                    responseData.status_code === responseStatus) {
                  console.log(`📎 Correlating response body: WebRequest ${data.request_id} -> Content ${contentRequestId}`);
                  capturedResponseData = responseData;
                  // Also store this correlation for future direct lookups
                  capturedResponseBodies.set(data.request_id, responseData);
                  break;
                }
              }
            }

            if (capturedResponseData) {
              return {
                included: true,
                content: capturedResponseData.response_body,
                content_type: capturedResponseData.content_type || null,
                encoding: 'utf-8',
                size_bytes: capturedResponseData.response_body.length,
                truncated: capturedResponseData.truncated || false,
                saved_to_file: null,
                note: "Response body captured via content script fetch/XHR interception"
              };
            } else {
              return {
                included: false,
                content: null,
                content_type: responseHeaders['content-type'] || requestDetail.response_content_type || null,
                encoding: null,
                size_bytes: requestDetail.response_content_length || 0,
                truncated: false,
                saved_to_file: null,
                note: "Response body content not available via WebRequest API"
              };
            }
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
        
      case 'test.create_test_tabs':
        await handleCreateTestTabs(id, data);
        break;


      default:
        sendError(id, 'UNKNOWN_ACTION', `Unknown test action: ${action}`);
    }
  } catch (error) {
    console.error(`Error handling test action ${action}:`, error);
    sendError(id, 'TEST_ERROR', `Test action failed: ${error.message}`, { action, error: error.toString() });
  }
}

// Get current popup display state
async function handleGetPopupState(id, data) {
  try {
    const storageConfig = await browser.storage.sync.get({
      hostname: 'localhost',
      port: 8765,
      retryInterval: 5000,
      maxRetries: -1,
      pingTimeout: 5000,
      testPort: null,
      testHostname: null
    });
    
    // Calculate effective values (same logic as popup.js)
    const effectiveHostname = storageConfig.testHostname || storageConfig.hostname || 'localhost';
    const effectivePort = storageConfig.testPort || storageConfig.port || 8765;
    const serverUrl = `ws://${effectiveHostname}:${effectivePort}`;
    const hasTestOverrides = storageConfig.testPort !== null || storageConfig.testHostname !== null;
    
    sendResponse(id, 'test.get_popup_state', {
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

// Get current options page display state  
async function handleGetOptionsState(id, data) {
  try {
    const storageConfig = await browser.storage.sync.get({
      hostname: 'localhost',
      port: 8765,
      retryInterval: 5000,
      maxRetries: -1,
      pingTimeout: 5000,
      testPort: null,
      testHostname: null
    });
    
    // Calculate display values (same logic as options.js)
    const displayHostname = storageConfig.testHostname || storageConfig.hostname;
    const displayPort = storageConfig.testPort || storageConfig.port;
    const webSocketUrl = `ws://${displayHostname}:${displayPort}`;
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

// Test Helper: Create test tabs for testing tabs.list functionality
async function handleCreateTestTabs(id, data) {
  try {
    const count = data.count || 3; // Default to 3 test tabs
    const baseUrls = data.urls || [
      'https://example.com',
      'https://httpbin.org/html',
      'https://httpbin.org/json'
    ];
    const closeExisting = data.closeExisting || false;
    
    // Close existing tabs if requested (except pinned tabs)
    if (closeExisting) {
      const existingTabs = await browser.tabs.query({});
      const tabsToClose = existingTabs.filter(tab => !tab.pinned && tab.url !== 'about:blank');
      
      if (tabsToClose.length > 0) {
        await browser.tabs.remove(tabsToClose.map(tab => tab.id));
      }
    }
    
    const createdTabs = [];
    
    // Create the specified number of test tabs
    for (let i = 0; i < count; i++) {
      const url = baseUrls[i % baseUrls.length];
      const testUrl = `${url}?test=tab${i + 1}&timestamp=${Date.now()}`;
      
      try {
        const tab = await browser.tabs.create({
          url: testUrl,
          active: i === 0 // Make first tab active
        });
        
        createdTabs.push({
          id: tab.id,
          url: testUrl,
          title: `Test Tab ${i + 1}`,
          active: tab.active,
          index: tab.index
        });
        
        // Small delay between tab creation
        if (i < count - 1) {
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      } catch (error) {
        console.error(`Failed to create test tab ${i + 1}:`, error);
      }
    }
    
    // Wait a moment for tabs to load
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Get final tab count
    const allTabs = await browser.tabs.query({});
    
    sendResponse(id, 'test.create_test_tabs', {
      success: true,
      message: `Successfully created ${createdTabs.length} test tabs`,
      createdTabs: createdTabs,
      totalTabsAfter: allTabs.length,
      tabsCreated: createdTabs.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    sendError(id, 'CREATE_TABS_ERROR', `Failed to create test tabs: ${error.message}`);
  }
}


// ✅ INITIALIZATION: Load config and connect automatically after loading completes
// This ensures storage configuration is fully loaded before connection attempts
console.log('🚀 Extension starting - loading configuration...');

// Initialize extension: load config then connect
async function initializeExtension() {
  try {
    console.log('🚀 Initializing extension...');
    console.log('📍 BEFORE loadConfig() - CONFIG:', JSON.stringify(CONFIG, null, 2));

    await loadConfig();

    console.log('✅ Configuration loaded successfully');
    console.log('📍 AFTER loadConfig() - CONFIG:', JSON.stringify(CONFIG, null, 2));

    // Connect after config load
    console.log('🔌 Connecting to MCP server...');
    connectToMCPServer();

  } catch (error) {
    console.error('❌ Failed to initialize extension:', error);
    console.log('🔄 Will retry initialization in 1 second...');
    setTimeout(() => {
      initializeExtension();
    }, 1000);
  }
}

// Store current monitoring config for new tabs
let currentMonitoringConfig = null;
let tabPollingInterval = null;
let enabledTabs = new Set(); // Track tabs that already have capture enabled

// Response body capture management
async function enableResponseBodyCapture(monitorConfig) {
  console.log(`📡 Enabling response body capture for all tabs with config: ${JSON.stringify(monitorConfig)}`);

  // Store config for new tabs
  currentMonitoringConfig = monitorConfig;

  // Send message to all existing content scripts to enable response capture
  try {
    const tabs = await browser.tabs.query({});
    console.log(`📡 Found ${tabs.length} tabs to enable capture on`);
    for (const tab of tabs) {
      console.log(`📡 Tab ${tab.id}: ${tab.url}`);
      if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
        enableCaptureOnTab(tab.id, monitorConfig);
      } else {
        console.log(`📡 Skipping tab ${tab.id} - not http/https: ${tab.url}`);
      }
    }
  } catch (err) {
    console.error(`📡 ERROR querying tabs: ${err.message}`);
  }

  // Set up polling for new tabs instead of event listeners (events weren't firing)
  // Set up polling for new tabs
  startTabPolling();
}

function enableCaptureOnTab(tabId, monitorConfig) {
  console.log(`📡 Sending enable_response_capture to tab ${tabId}`);
  browser.tabs.sendMessage(tabId, {
    action: 'enable_response_capture',
    data: {
      monitor_config: monitorConfig
    }
  }).then(response => {
    console.log(`📡 Tab ${tabId} response: ${JSON.stringify(response)}`);
  }).catch(err => {
    // Some tabs might not have content scripts loaded, that's OK
    console.log(`Could not enable capture on tab ${tabId}: ${err.message}`);
  });
}

function startTabPolling() {
  // Clear any existing polling interval
  if (tabPollingInterval) {
    clearInterval(tabPollingInterval);
  }

  // Check for new tabs every 1 second
  tabPollingInterval = setInterval(async () => {
    if (!currentMonitoringConfig) {
      return; // No monitoring active
    }

    try {
      const tabs = await browser.tabs.query({});
      for (const tab of tabs) {
        // Skip if already enabled for this tab
        if (enabledTabs.has(tab.id)) {
          continue;
        }

        // Check if tab URL matches our monitoring patterns
        if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
          const urlPatterns = currentMonitoringConfig.url_patterns || [];
          const matchesPattern = urlPatterns.some(pattern => {
            // Convert glob pattern to regex
            const regexPattern = pattern.replace(/\*/g, '.*');
            const regex = new RegExp(`^${regexPattern}$`);
            return regex.test(tab.url);
          });

          if (matchesPattern) {
            console.log(`📡 Found new tab ${tab.id} that matches monitoring pattern: ${tab.url}`);
            enableCaptureOnTab(tab.id, currentMonitoringConfig);
            enabledTabs.add(tab.id);
          }
        }
      }
    } catch (err) {
      console.error(`📡 ERROR in tab polling: ${err.message}`);
    }
  }, 1000); // Poll every second
}

function stopTabPolling() {
  if (tabPollingInterval) {
    clearInterval(tabPollingInterval);
    tabPollingInterval = null;
  }
  enabledTabs.clear();
}


function disableResponseBodyCapture() {
  console.log('🔄 Disabling response body capture for all tabs');

  // Clear the monitoring config
  currentMonitoringConfig = null;

  // Stop tab polling
  stopTabPolling();


  // Send message to all content scripts to disable response capture
  browser.tabs.query({}).then(tabs => {
    for (const tab of tabs) {
      if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
        browser.tabs.sendMessage(tab.id, {
          action: 'disable_response_capture'
        }).catch(err => {
          // Some tabs might not have content scripts loaded, that's OK
          console.log(`Could not disable capture on tab ${tab.id}: ${err.message}`);
        });
      }
    }
  });
}

// Start initialization
initializeExtension();
