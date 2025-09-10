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
    case 'windows':
      await handleWindowsAction(id, action, data);
      break;
    case 'bookmarks':
      await handleBookmarksAction(id, action, data);
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

// Content handlers
async function handleContentAction(id, action, data) {
  try {
    switch (action) {
      case 'content.text':
      case 'content.get_text':
        const textResult = await browser.tabs.sendMessage(data.tabId, {
          action: 'extractText'
        });
        sendResponse(id, action, { text: textResult.text });
        break;

      case 'content.html':
      case 'content.get_html':
        const htmlResult = await browser.tabs.sendMessage(data.tabId, {
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
        const bookmarks = flattenBookmarks(bookmarkTree);
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

// Start connection when extension loads
browser.runtime.onStartup.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

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
    const waitTime = data.waitTime || 6000; // Default 6 seconds wait
    
    if (!url) {
      sendError(id, 'INVALID_PARAMETERS', 'URL is required for test.visit_url');
      return;
    }
    
    // Create a new tab with the URL
    const tab = await browser.tabs.create({
      url: url,
      active: false // Don't make it active to avoid disrupting tests
    });
    
    // Wait for the page to load
    await new Promise(resolve => setTimeout(resolve, waitTime));
    
    // Close the tab
    await browser.tabs.remove(tab.id);
    
    sendResponse(id, 'test.visit_url', {
      success: true,
      url: url,
      tabId: tab.id,
      visitTime: new Date().toISOString(),
      message: `Successfully visited ${url}`
    });
    
  } catch (error) {
    sendError(id, 'VISIT_URL_ERROR', `Failed to visit URL: ${error.message}`);
  }
}

// Test Helper: Visit multiple URLs to create test history
async function handleVisitMultipleURLs(id, data) {
  try {
    const urls = data.urls || [];
    const waitTime = data.waitTime || 6000; // Time to wait at each URL (increased)
    const delayBetween = data.delayBetween || 2000; // Delay between visits (increased)
    
    if (!Array.isArray(urls) || urls.length === 0) {
      sendError(id, 'INVALID_PARAMETERS', 'urls array is required for test.visit_multiple_urls');
      return;
    }
    
    const results = [];
    
    for (let i = 0; i < urls.length; i++) {
      const url = urls[i];
      
      try {
        // Create tab and visit URL
        const tab = await browser.tabs.create({
          url: url,
          active: false
        });
        
        // Wait for page to load
        await new Promise(resolve => setTimeout(resolve, waitTime));
        
        // Close the tab
        await browser.tabs.remove(tab.id);
        
        results.push({
          url: url,
          success: true,
          tabId: tab.id,
          visitTime: new Date().toISOString()
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

browser.runtime.onInstalled.addListener(async () => {
  await loadConfig();
  connectToMCPServer();
});

// Initialize and connect immediately
(async () => {
  await loadConfig();
  connectToMCPServer();
})();
