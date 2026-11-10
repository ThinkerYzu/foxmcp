// Fast check of loadDiscardedTab and sendMessageWithRetry in extension/background.js,
// run with Node by tests/unit/test_discarded_tab_loading.py. It extracts the two
// functions and runs them against a fake browser with a fake clock.
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, '..', 'extension', 'background.js'), 'utf8');

function extract(name) {
  const start = source.indexOf(`async function ${name}(`);
  if (start < 0) throw new Error(`${name} not found`);
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`${name} is not closed`);
}

const code = `${extract('loadDiscardedTab')}\n${extract('sendMessageWithRetry')}\nreturn {sendMessageWithRetry};`;

function run(tabStates, options = {}) {
  const calls = { reload: 0, send: 0, get: 0 };
  let clock = 0;
  const browser = {
    tabs: {
      async get() {
        calls.get++;
        if (tabStates === null) throw new Error('No tab with id');
        const state = tabStates[Math.min(calls.get - 1, tabStates.length - 1)];
        return { id: 1, url: 'https://example.org/', ...state };
      },
      async reload() { calls.reload++; },
      async sendMessage() {
        calls.send++;
        if (options.noReceiver) throw new Error('Receiving end does not exist');
        return { ok: true };
      },
    },
  };
  const fakeSetTimeout = (fn) => { clock += 250; return setImmediate(fn); };
  class FakeDate extends Date { static now() { return clock; } }
  const factory = new Function('browser', 'setTimeout', 'Date', code);
  return { calls, api: factory(browser, fakeSetTimeout, FakeDate) };
}

async function main() {
  const results = [];
  const check = (ok, label) => { if (!ok) throw new Error(label); results.push(label); };

  let t = run([{ discarded: false, status: 'complete' }]);
  check((await t.api.sendMessageWithRetry(1, {})).ok && t.calls.reload === 0,
    'a loaded tab is not reloaded');

  t = run([{ discarded: true, status: 'unloaded' }, { discarded: true, status: 'unloaded' },
    { discarded: false, status: 'loading' }, { discarded: false, status: 'complete' }]);
  check((await t.api.sendMessageWithRetry(1, {})).ok && t.calls.reload === 1 && t.calls.send === 1,
    'a discarded tab is reloaded once, awaited, and then answers');

  t = run([{ discarded: true, status: 'unloaded' }]);
  let message = '';
  try { await t.api.sendMessageWithRetry(1, {}); } catch (error) { message = error.message; }
  check(message.includes('did not finish loading') && t.calls.send === 0,
    'a tab that never loads fails with a clear message and no retries');

  t = run(null);
  message = '';
  try { await t.api.sendMessageWithRetry(1, {}, 2, 1); } catch (error) { message = error.message; }
  check(message.includes('Content script not available after 2 attempts') && t.calls.reload === 0,
    'a missing tab is still reported by the retry loop');

  console.log(`ok ${results.length}`);
}

main().catch(error => { console.error(error.message); process.exit(1); });
