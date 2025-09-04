// Options page script for FoxMCP extension configuration

document.addEventListener('DOMContentLoaded', function() {
    // Load saved settings
    loadSettings();

    // Update WebSocket URL when hostname or port changes
    document.getElementById('hostname').addEventListener('input', updateWebSocketUrl);
    document.getElementById('port').addEventListener('input', updateWebSocketUrl);

    // Form submission
    document.getElementById('optionsForm').addEventListener('submit', saveSettings);

    // Button event listeners
    document.getElementById('testConnection').addEventListener('click', testConnection);
    document.getElementById('refreshStatus').addEventListener('click', refreshConnectionStatus);
    document.getElementById('saveAdvanced').addEventListener('click', saveAdvancedSettings);
    document.getElementById('resetDefaults').addEventListener('click', resetToDefaults);

    // Initial connection status check
    refreshConnectionStatus();
});

async function loadSettings() {
    try {
        const result = await browser.storage.sync.get({
            hostname: 'localhost',
            port: 8765,
            retryInterval: 5000,
            maxRetries: -1,
            pingTimeout: 5000,
            // Test configuration overrides
            testPort: null,
            testHostname: null
        });

        // Use test overrides if they exist, otherwise use regular config
        const displayHostname = result.testHostname || result.hostname;
        const displayPort = result.testPort || result.port;

        document.getElementById('hostname').value = displayHostname;
        document.getElementById('port').value = displayPort;
        document.getElementById('retryInterval').value = result.retryInterval;
        document.getElementById('maxRetries').value = result.maxRetries;
        document.getElementById('pingTimeout').value = result.pingTimeout;

        // Show warning if test overrides are active
        if (result.testPort || result.testHostname) {
            showStatus(`Using test configuration overrides (port: ${result.testPort || 'default'}, hostname: ${result.testHostname || 'default'})`, 'success');
        }

        updateWebSocketUrl();
    } catch (error) {
        console.error('Error loading settings:', error);
        showStatus('Error loading settings', 'error');
    }
}

async function saveSettings(event) {
    event.preventDefault();

    const hostname = document.getElementById('hostname').value.trim();
    const port = parseInt(document.getElementById('port').value);

    if (!hostname) {
        showStatus('Hostname is required', 'error');
        return;
    }

    if (port < 1 || port > 65535) {
        showStatus('Port must be between 1 and 65535', 'error');
        return;
    }

    try {
        // Get existing configuration to preserve test overrides
        const existingConfig = await browser.storage.sync.get({
            testPort: null,
            testHostname: null,
            retryInterval: 5000,
            maxRetries: -1,
            pingTimeout: 5000
        });

        // Save the new settings while preserving test overrides
        await browser.storage.sync.set({
            hostname: hostname,
            port: port,
            // Preserve existing test overrides and other settings
            testPort: existingConfig.testPort,
            testHostname: existingConfig.testHostname,
            retryInterval: existingConfig.retryInterval,
            maxRetries: existingConfig.maxRetries,
            pingTimeout: existingConfig.pingTimeout
        });

        // Notify background script of configuration change
        await browser.runtime.sendMessage({
            type: 'configUpdated',
            config: { hostname, port }
        });

        if (existingConfig.testPort || existingConfig.testHostname) {
            showStatus('Settings saved! (Test overrides are still active)', 'success');
        } else {
            showStatus('Settings saved successfully!', 'success');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showStatus('Error saving settings', 'error');
    }
}

async function saveAdvancedSettings() {
    const retryInterval = parseInt(document.getElementById('retryInterval').value);
    const maxRetries = parseInt(document.getElementById('maxRetries').value);
    const pingTimeout = parseInt(document.getElementById('pingTimeout').value);

    if (retryInterval < 1000 || retryInterval > 60000) {
        showStatus('Retry interval must be between 1000 and 60000ms', 'error');
        return;
    }

    if (maxRetries < -1 || maxRetries > 100) {
        showStatus('Max retries must be -1 or between 0 and 100', 'error');
        return;
    }

    if (pingTimeout < 1000 || pingTimeout > 30000) {
        showStatus('Ping timeout must be between 1000 and 30000ms', 'error');
        return;
    }

    try {
        // Get existing configuration to preserve all settings including test overrides
        const existingConfig = await browser.storage.sync.get({
            hostname: 'localhost',
            port: 8765,
            testPort: null,
            testHostname: null
        });

        await browser.storage.sync.set({
            retryInterval: retryInterval,
            maxRetries: maxRetries,
            pingTimeout: pingTimeout,
            // Preserve existing configuration
            hostname: existingConfig.hostname,
            port: existingConfig.port,
            testPort: existingConfig.testPort,
            testHostname: existingConfig.testHostname
        });

        // Notify background script of advanced configuration change
        await browser.runtime.sendMessage({
            type: 'advancedConfigUpdated',
            config: { retryInterval, maxRetries, pingTimeout }
        });

        showStatus('Advanced settings saved successfully!', 'success');
    } catch (error) {
        console.error('Error saving advanced settings:', error);
        showStatus('Error saving advanced settings', 'error');
    }
}

async function testConnection() {
    const button = document.getElementById('testConnection');
    const originalText = button.textContent;

    button.textContent = 'Testing...';
    button.disabled = true;

    try {
        const response = await browser.runtime.sendMessage({
            type: 'testConnection'
        });

        if (response && response.success) {
            showStatus('Connection test successful!', 'success');
            updateConnectionStatus(true);
        } else {
            showStatus(`Connection test failed: ${response?.error || 'Unknown error'}`, 'error');
            updateConnectionStatus(false);
        }
    } catch (error) {
        console.error('Error testing connection:', error);
        showStatus('Connection test failed', 'error');
        updateConnectionStatus(false);
    } finally {
        button.textContent = originalText;
        button.disabled = false;
    }
}

async function refreshConnectionStatus() {
    try {
        const response = await browser.runtime.sendMessage({
            type: 'getConnectionStatus'
        });

        if (response) {
            updateConnectionStatus(response.connected);
        }
    } catch (error) {
        console.error('Error getting connection status:', error);
        updateConnectionStatus(false);
    }
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connectionIndicator');
    const text = document.getElementById('connectionText');

    if (connected) {
        indicator.className = 'status-indicator connected';
        text.textContent = 'Connected';
    } else {
        indicator.className = 'status-indicator disconnected';
        text.textContent = 'Disconnected';
    }
}

function updateWebSocketUrl() {
    const hostname = document.getElementById('hostname').value.trim();
    const port = document.getElementById('port').value;

    if (hostname && port) {
        const wsUrl = `ws://${hostname}:${port}`;
        document.getElementById('wsUrl').value = wsUrl;
    }
}

function resetToDefaults() {
    if (confirm('Reset all settings to default values?')) {
        document.getElementById('hostname').value = 'localhost';
        document.getElementById('port').value = 8765;
        document.getElementById('retryInterval').value = 5000;
        document.getElementById('maxRetries').value = -1;
        document.getElementById('pingTimeout').value = 5000;

        updateWebSocketUrl();
        showStatus('Settings reset to defaults', 'success');
    }
}

function showStatus(message, type) {
    const statusDiv = document.getElementById('status');
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.style.display = 'block';

    // Hide status after 5 seconds
    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 5000);
}