// Shared by the persistent background page, popup and options page.
const FoxMCPConfig = (() => {
  const defaults = Object.freeze({hostname: 'localhost', port: 8765, retryInterval: 1000});
  const storageDefaults = Object.freeze({...defaults, testHostname: null, testPort: null});

  function integer(value, min, max, label) {
    if (typeof value === 'string' && /^\d+$/.test(value.trim())) value = Number(value.trim());
    if (typeof value !== 'number' || !Number.isInteger(value) || value < min || value > max) {
      throw new Error(`${label} must be an integer between ${min} and ${max}`);
    }
    return value;
  }

  function endpoint(values) {
    const port = integer(values.port, 1, 65535, 'Port');
    let hostname = typeof values.hostname === 'string' ? values.hostname.trim() : '';
    if (!hostname || /[\s/?#@\\%]/.test(hostname)) {
      throw new Error('Host must be a hostname or IP address, without a scheme, path or port');
    }
    // URL parses IPv6 literals only inside brackets. Store its canonical host.
    if (hostname.includes(':') && !hostname.startsWith('[')) hostname = `[${hostname}]`;
    try {
      const url = new URL(`ws://${hostname}:${port}/`);
      if (!url.hostname || url.pathname !== '/' || url.search || url.hash || url.username || url.password) {
        throw new Error('Invalid host');
      }
      hostname = url.hostname;
    } catch (_) {
      throw new Error('Host must be a hostname or IP address, without a scheme, path or port');
    }
    return {hostname, port};
  }

  function group(name, values) {
    if (name === 'endpoint') return endpoint(values);
    if (name === 'retryInterval') {
      return {retryInterval: integer(values.retryInterval, 100, 30000, 'Reconnect interval (ms)')};
    }
    throw new Error('Unknown settings group');
  }

  function configured(stored) {
    return Object.fromEntries(Object.keys(defaults).map(key => [key, stored[key] === undefined ? defaults[key] : stored[key]]));
  }

  function effective(stored) {
    const config = configured(stored);
    const userEndpoint = endpoint(config);
    return {
      ...endpoint({
        hostname: stored.testHostname ?? userEndpoint.hostname,
        port: stored.testPort ?? userEndpoint.port
      }),
      ...group('retryInterval', config)
    };
  }

  const address = config => `${config.hostname}:${config.port}`;
  return Object.freeze({defaults, storageDefaults, group, configured, effective, address,
    socketUrl: config => `ws://${address(config)}`});
})();
