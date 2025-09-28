/*
 * FoxMCP Firefox Extension - Popup Script
 * Copyright (c) 2024 FoxMCP Project
 * Licensed under the MIT License - see LICENSE file for details
 */

// Check connection status on popup open
document.addEventListener('DOMContentLoaded', async () => {
  const statusElement = document.getElementById('status');
  const retryInfo = document.getElementById('retryInfo');
  const testResult = document.getElementById('testResult');
  const forceReconnectButton = document.getElementById('forceReconnect');
  const saveConfigButton = document.getElementById('saveConfig');
  const serverInfo = document.getElementById('serverInfo');

  // Configuration elements
  const serverUrlInput = document.getElementById('serverUrl');
  const retryIntervalInput = document.getElementById('retryInterval');
  const maxRetriesInput = document.getElementById('maxRetries');
  const pingTimeoutInput = document.getElementById('pingTimeout');

  // Load configuration from storage and background script
  async function updateDisplay() {
    try {
      // Get connection status from background script
      const connectionResponse = await new Promise((resolve) => {
        browser.runtime.sendMessage({ action: 'getConnectionStatus' }, (response) => {
          if (browser.runtime.lastError) {
            resolve({ connected: false, retryAttempts: 0, config: {} });
          } else {
            resolve(response || { connected: false, retryAttempts: 0, config: {} });
          }
        });
      });

      // Load configuration directly from storage to ensure accuracy
      const storageConfig = await browser.storage.sync.get({
        hostname: 'localhost',
        port: 8765,
        retryInterval: 5000,
        maxRetries: -1,
        pingTimeout: 5000,
        // Test configuration overrides
        testPort: null,
        testHostname: null
      });

      updateStatus(connectionResponse.connected, connectionResponse.retryAttempts, storageConfig);
      loadConfigToUI(storageConfig);

    } catch (error) {
      console.error('Error updating display:', error);
      updateStatus(false, 0, {});
    }
  }

  // Load configuration into UI fields
  function loadConfigToUI(config) {
    // Use test overrides if they exist, otherwise use regular config
    const effectiveHostname = config.testHostname || config.hostname || 'localhost';
    const effectivePort = config.testPort || config.port || 8765;
    const wsUrl = `ws://${effectiveHostname}:${effectivePort}`;

    serverUrlInput.value = wsUrl;
    retryIntervalInput.value = config.retryInterval || 5000;
    maxRetriesInput.value = config.maxRetries !== undefined ? config.maxRetries : -1;
    pingTimeoutInput.value = config.pingTimeout || 5000;
    serverInfo.textContent = `Server: ${wsUrl}`;

    // Show test override indicator if active
    if (config.testPort || config.testHostname) {
      const testIndicator = document.createElement('div');
      testIndicator.style.cssText = 'font-size: 10px; color: #0066cc; margin-top: 2px;';
      testIndicator.textContent = `⚙️ Test config active (${effectivePort})`;
      serverInfo.appendChild(testIndicator);
    }
  }

  // Initial display update
  await updateDisplay();

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
  saveConfigButton.addEventListener('click', async () => {
    const serverUrl = serverUrlInput.value.trim();
    const retryInterval = parseInt(retryIntervalInput.value) || 5000;
    const maxRetries = parseInt(maxRetriesInput.value) || -1;
    const pingTimeout = parseInt(pingTimeoutInput.value) || 5000;

    // Validate configuration
    if (!serverUrl.startsWith('ws://') && !serverUrl.startsWith('wss://')) {
      testResult.textContent = '❌ Invalid WebSocket URL. Must start with ws:// or wss://';
      testResult.style.color = 'red';
      return;
    }

    if (retryInterval < 1000) {
      testResult.textContent = '❌ Retry interval must be at least 1000ms';
      testResult.style.color = 'red';
      return;
    }

    try {
      // Parse hostname and port from WebSocket URL
      const url = new URL(serverUrl);
      const hostname = url.hostname;
      const port = parseInt(url.port) || 8765;

      // Get existing configuration to preserve test overrides
      const existingConfig = await browser.storage.sync.get({
        testPort: null,
        testHostname: null
      });

      // Save configuration to storage.sync
      await browser.storage.sync.set({
        hostname: hostname,
        port: port,
        retryInterval: retryInterval,
        maxRetries: maxRetries,
        pingTimeout: pingTimeout,
        // Preserve test overrides
        testPort: existingConfig.testPort,
        testHostname: existingConfig.testHostname
      });

      // Notify background script of configuration change
      const messageResponse = await new Promise((resolve) => {
        browser.runtime.sendMessage({
          action: 'updateConfig',
          config: { hostname, port, retryInterval, maxRetries, pingTimeout }
        }, (response) => {
          resolve(response);
        });
      });

      if (messageResponse?.success) {
        if (existingConfig.testPort || existingConfig.testHostname) {
          testResult.textContent = '✅ Configuration saved! (Test overrides still active)';
        } else {
          testResult.textContent = '✅ Configuration saved successfully!';
        }
        testResult.style.color = 'green';
        setTimeout(() => updateDisplay(), 500);
      } else {
        testResult.textContent = '❌ Failed to notify background script';
        testResult.style.color = 'red';
      }

    } catch (error) {
      console.error('Error saving configuration:', error);
      testResult.textContent = '❌ Failed to save configuration';
      testResult.style.color = 'red';
    }
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
      const maxRetries = config.maxRetries !== undefined ? config.maxRetries : -1;
      const retryInterval = config.retryInterval || 5000;

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