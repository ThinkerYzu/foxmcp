// Check connection status on popup open
document.addEventListener('DOMContentLoaded', () => {
  const statusElement = document.getElementById('status');
  const retryInfo = document.getElementById('retryInfo');
  const testButton = document.getElementById('testPing');
  const testResult = document.getElementById('testResult');
  const forceReconnectButton = document.getElementById('forceReconnect');
  const saveConfigButton = document.getElementById('saveConfig');
  const serverInfo = document.getElementById('serverInfo');
  
  // Configuration elements
  const serverUrlInput = document.getElementById('serverUrl');
  const retryIntervalInput = document.getElementById('retryInterval');
  const maxRetriesInput = document.getElementById('maxRetries');
  const pingTimeoutInput = document.getElementById('pingTimeout');
  
  // Request connection status from background script
  function updateDisplay() {
    browser.runtime.sendMessage({ action: 'getConnectionStatus' }, (response) => {
      if (browser.runtime.lastError) {
        updateStatus(false, 0, {});
        return;
      }
      
      updateStatus(response?.connected || false, response?.retryAttempts || 0, response?.config || {});
      loadConfigToUI(response?.config || {});
    });
  }
  
  // Load configuration into UI fields
  function loadConfigToUI(config) {
    serverUrlInput.value = config.WS_URL || 'ws://localhost:8765';
    retryIntervalInput.value = config.RETRY_INTERVAL || 5000;
    maxRetriesInput.value = config.MAX_RETRY_ATTEMPTS || -1;
    pingTimeoutInput.value = config.PING_TIMEOUT || 5000;
    serverInfo.textContent = `Server: ${config.WS_URL || 'ws://localhost:8765'}`;
  }
  
  // Initial display update
  updateDisplay();
  
  // Handle test ping button
  testButton.addEventListener('click', async () => {
    testButton.disabled = true;
    testButton.textContent = 'Testing...';
    testResult.textContent = 'Sending ping...';
    
    browser.runtime.sendMessage({ action: 'testPing' }, (response) => {
      testButton.disabled = false;
      testButton.textContent = 'Test Connection';
      
      if (browser.runtime.lastError) {
        testResult.textContent = `Error: ${browser.runtime.lastError.message}`;
        testResult.style.color = 'red';
        return;
      }
      
      if (response.success) {
        testResult.textContent = `✅ Ping successful! Received: ${response.response.data.message}`;
        testResult.style.color = 'green';
      } else {
        testResult.textContent = `❌ Ping failed: ${response.error}`;
        testResult.style.color = 'red';
      }
    });
  });
  
  // Handle force reconnect button
  forceReconnectButton.addEventListener('click', () => {
    browser.runtime.sendMessage({ action: 'forceReconnect' }, (response) => {
      if (response?.success) {
        testResult.textContent = '🔄 Reconnection initiated';
        testResult.style.color = 'blue';
        setTimeout(updateDisplay, 1000); // Update display after a second
      }
    });
  });
  
  // Handle save configuration button
  saveConfigButton.addEventListener('click', () => {
    const newConfig = {
      WS_URL: serverUrlInput.value.trim(),
      RETRY_INTERVAL: parseInt(retryIntervalInput.value) || 5000,
      MAX_RETRY_ATTEMPTS: parseInt(maxRetriesInput.value) || -1,
      PING_TIMEOUT: parseInt(pingTimeoutInput.value) || 5000
    };
    
    // Validate configuration
    if (!newConfig.WS_URL.startsWith('ws://') && !newConfig.WS_URL.startsWith('wss://')) {
      testResult.textContent = '❌ Invalid WebSocket URL. Must start with ws:// or wss://';
      testResult.style.color = 'red';
      return;
    }
    
    if (newConfig.RETRY_INTERVAL < 1000) {
      testResult.textContent = '❌ Retry interval must be at least 1000ms';
      testResult.style.color = 'red';
      return;
    }
    
    browser.runtime.sendMessage({ action: 'updateConfig', config: newConfig }, (response) => {
      if (response?.success) {
        testResult.textContent = '✅ Configuration saved successfully!';
        testResult.style.color = 'green';
        serverInfo.textContent = `Server: ${newConfig.WS_URL}`;
        setTimeout(updateDisplay, 500);
      } else {
        testResult.textContent = '❌ Failed to save configuration';
        testResult.style.color = 'red';
      }
    });
  });
});

function updateStatus(connected, retryAttempts, config) {
  const statusElement = document.getElementById('status');
  const retryInfo = document.getElementById('retryInfo');
  
  if (connected) {
    statusElement.textContent = 'Status: Connected';
    statusElement.className = 'status connected';
    retryInfo.textContent = retryAttempts > 0 ? `Connected after ${retryAttempts} retry attempts` : '';
  } else {
    statusElement.textContent = 'Status: Disconnected';
    statusElement.className = 'status disconnected';
    
    if (retryAttempts > 0) {
      const maxRetries = config.MAX_RETRY_ATTEMPTS || -1;
      const retryInterval = config.RETRY_INTERVAL || 5000;
      
      if (maxRetries > 0) {
        retryInfo.textContent = `Retry ${retryAttempts}/${maxRetries} (every ${retryInterval}ms)`;
      } else {
        retryInfo.textContent = `Retry attempt ${retryAttempts} (every ${retryInterval}ms)`;
      }
    } else {
      retryInfo.textContent = '';
    }
  }
}