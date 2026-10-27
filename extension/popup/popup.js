document.addEventListener('DOMContentLoaded', () => FoxMCPSettingsUI.mount(status => {
  const indicator = document.getElementById('status');
  indicator.textContent = FoxMCPSettingsUI.connectionText(status);
  indicator.className = `status ${status.connected ? 'connected' : 'disconnected'}`;
  indicator.dataset.state = status.state;
  document.getElementById('serverInfo').textContent = FoxMCPSettingsUI.serverText(status);
  FoxMCPSettingsUI.renderVersion(status);
}, () => {
  document.getElementById('status').textContent = 'Status unavailable';
  document.getElementById('status').className = 'status disconnected';
  document.getElementById('status').dataset.state = 'unavailable';
  document.getElementById('serverInfo').textContent = '';
  document.getElementById('versionInfo').textContent = '';
}));
