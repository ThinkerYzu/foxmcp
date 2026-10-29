// Shared UI controller. Debounce belongs to the background page, not this view.
const FoxMCPSettingsUI = {
  async mount(renderConnection, renderUnavailable) {
    const fields = Object.fromEntries(['hostname', 'port', 'retryInterval'].map(id => [id, document.getElementById(id)]));
    const feedback = document.getElementById('saveStatus');
    const dirty = new Map();
    const inputSequence = {endpoint: 0, retryInterval: 0};
    let alive = true;
    let refreshSequence = 0;
    let refreshTimer = null;
    window.addEventListener('unload', () => {
      alive = false;
      if (refreshTimer !== null) clearInterval(refreshTimer);
    });

    function render(status) {
      if (!alive) return;
      const groups = status.settings.groups;
      const config = status.configuredConfig;
      for (const [group, keys] of Object.entries({endpoint: ['hostname', 'port'], retryInterval: ['retryInterval']})) {
        const revision = dirty.get(group);
        if (dirty.has(group) && revision !== null && groups[group].revision >= revision && groups[group].state === 'saved') dirty.delete(group);
        if (!dirty.has(group)) for (const key of keys) fields[key].value = config[key] ?? '';
      }
      const errors = Object.values(groups).filter(group => group.state === 'error');
      const pending = Object.values(groups).some(group => group.state === 'pending');
      feedback.textContent = errors.length ? errors.map(group => group.error).join('; ')
        : pending ? 'Waiting to save…' : status.configError || 'Saved';
      feedback.dataset.state = errors.length || (!pending && status.configError) ? 'error' : pending ? 'pending' : 'saved';
      renderConnection(status);
    }

    function unavailable(error) {
      if (!alive) return;
      feedback.textContent = `Settings unavailable: ${error.message}`;
      feedback.dataset.state = 'error';
      renderUnavailable();
    }

    async function refresh() {
      const sequence = ++refreshSequence;
      try {
        const status = await browser.runtime.sendMessage({action: 'getConnectionStatus'});
        if (sequence === refreshSequence) render(status);
      } catch (error) {
        if (sequence === refreshSequence) unavailable(error);
      }
    }

    async function changed(group) {
      const sequence = ++inputSequence[group];
      refreshSequence++;
      dirty.set(group, null);
      feedback.textContent = 'Waiting to save…';
      feedback.dataset.state = 'pending';
      const config = group === 'endpoint'
        ? {hostname: fields.hostname.value, port: fields.port.value}
        : {retryInterval: fields.retryInterval.value};
      try {
        const status = await browser.runtime.sendMessage({action: 'queueConfigUpdate', group, config});
        if (sequence !== inputSequence[group]) return;
        dirty.set(group, status.settings.groups[group].revision);
        render(status);
      } catch (error) {
        if (sequence === inputSequence[group]) unavailable(error);
      }
    }

    for (const key of ['hostname', 'port']) fields[key].addEventListener('input', () => changed('endpoint'));
    fields.retryInterval.addEventListener('input', () => changed('retryInterval'));
    const reset = document.getElementById('resetDefaults');
    if (reset) reset.addEventListener('click', async () => {
      // Native modal dialogs can block Firefox toolbar popups. Reset directly.

      refreshSequence++;
      inputSequence.endpoint++;
      inputSequence.retryInterval++;
      const sequence = {...inputSequence};
      try {
        const status = await browser.runtime.sendMessage({action: 'resetConfig'});
        for (const group of Object.keys(sequence)) {
          if (sequence[group] === inputSequence[group] && status.settings.groups[group].state === 'saved') dirty.delete(group);
        }
        render(status);
      } catch (error) {
        unavailable(error);
      }
    });
    await refresh();
    if (!alive) return;
    refreshTimer = setInterval(refresh, 1000);
  },

  renderVersion(connection) {
    const element = document.getElementById('versionInfo');
    const extension = connection.extensionVersion || browser.runtime.getManifest().version;
    const server = connection.connected ? connection.serverVersion : null;
    const protocol = Number.isSafeInteger(connection.protocolVersion) && connection.protocolVersion > 0
      ? connection.protocolVersion : 'unavailable';
    element.dataset.state = '';
    if (connection.connectionError) {
      element.dataset.state = 'mismatch';
      element.textContent = connection.connectionError;
    } else if (!connection.connected) {
      element.textContent = `Extension ${extension}; server disconnected.`;
    } else if (!server) {
      element.textContent = `Extension ${extension}; server version unavailable. Older servers may not report a version. Update both together to check versions.`;
    } else if (server !== extension) {
      element.dataset.state = 'mismatch';
      element.textContent = `Version mismatch: extension ${extension}, server ${server}. Update extension and server together. Browser tools remain available.`;
    } else {
      element.textContent = `Extension ${extension} · Server ${server}`;
    }
    element.textContent += ` · Protocol ${protocol}`;
  },

  connectionText(status) {
    if (status.state === 'configuration_error') return `Configuration error: ${status.configError}`;
    if (status.connectionError) return `Connection error: ${status.connectionError}`;
    if (status.connected) return 'Connected';
    if (status.state === 'connecting') return 'Connecting…';
    if (status.state === 'waiting_retry') {
      const remaining = Math.max(0, status.nextRetryAt - Date.now());
      const wait = remaining < 1000 ? `${Math.ceil(remaining)}ms` : `${Math.ceil(remaining / 1000)}s`;
      return `Retry ${status.retryAttempts + 1} in ${wait} (${status.retryDelayMs}ms interval)`;
    }
    return status.state === 'initializing' ? 'Loading settings…' : 'Disconnected';
  },

  serverText(status) {
    return `Server: ${FoxMCPConfig.address(status.config)}${status.hasTestOverrides ? ' (test overrides active)' : ''}`;
  }
};
