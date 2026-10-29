document.addEventListener('DOMContentLoaded', () => FoxMCPSettingsUI.mount(status => {
  document.getElementById('connectionIndicator').className = `status-indicator ${status.connected ? 'connected' : 'disconnected'}`;
  document.getElementById('connectionText').textContent = FoxMCPSettingsUI.connectionText(status);
  document.getElementById('serverInfo').textContent = FoxMCPSettingsUI.serverText(status);
  document.getElementById('connectionIndicator').dataset.state = status.state;
  FoxMCPSettingsUI.renderVersion(status);
}, () => {
  document.getElementById('connectionIndicator').className = 'status-indicator disconnected';
  document.getElementById('connectionText').textContent = 'Status unavailable';
  document.getElementById('connectionIndicator').dataset.state = 'unavailable';
  document.getElementById('serverInfo').textContent = '';
  document.getElementById('versionInfo').textContent = '';
}));
