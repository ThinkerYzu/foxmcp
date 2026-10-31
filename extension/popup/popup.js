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


// The background owns the queue and deadline; closing/reopening cannot reset it.
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('scriptApproval');
  const settings = document.getElementById('settingsPanel');
  const allow = document.getElementById('allowScripts');
  const deny = document.getElementById('denyScripts');
  let token = null;
  let approvalMode = false;
  let busy = false;
  async function refresh() {
    if (busy) return;
    try {
      const item = await browser.runtime.sendMessage({action: 'getScriptConsent'});
      if (!item && approvalMode) { window.close(); return; }
      if (item) approvalMode = true;
      settings.hidden = !!item;
      panel.hidden = !item;
      token = item?.token || null;
      if (!item) return;
      document.getElementById('approvalTab').textContent = item.title;
      document.getElementById('approvalOrigin').textContent = item.origin;
      const seconds = Math.max(0, Math.ceil((item.deadline - Date.now()) / 1000));
      document.getElementById('approvalTime').textContent = item.visible
        ? `${seconds}s remaining. This choice applies to agent scripts in this tab on this site.`
        : 'Return to the target tab and window to decide.';
      allow.disabled = deny.disabled = !item.visible || !seconds;
    } catch (error) {
      if (!approvalMode) settings.hidden = false;
      allow.disabled = deny.disabled = true;
      document.getElementById('approvalError').textContent = error.message;
    }
  }
  async function decide(allowed) {
    if (!token || busy) return;
    busy = true;
    allow.disabled = deny.disabled = true;
    try {
      await browser.runtime.sendMessage({action: 'decideScriptConsent', token, allowed});
      window.close();
    } catch (error) {
      document.getElementById('approvalError').textContent = error.message;
      busy = false;
      refresh();
    }
  }
  allow.addEventListener('click', () => decide(true));
  deny.addEventListener('click', () => decide(false));
  refresh();
  const timer = setInterval(refresh, 250);
  window.addEventListener('unload', () => clearInterval(timer));
});
