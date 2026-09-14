// Execute the actual handler only: no extension startup, profile or WebSocket.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../extension/background.js'), 'utf8');
const start = source.indexOf('async function handleTabsAction(');
const end = source.indexOf('\nasync function ', start + 1);
const handler = source.slice(start, end);
function setup({ unsupported = false, failGroup = false, failUpdate = false } = {}) {
  const calls = [];
  let response;
  const context = vm.createContext({
    browser: {
      tabs: { get: async () => ({windowId: 5}), group: async options => {
        calls.push(['group', options]);
        if (failGroup) throw Error('Pinned tab');
        return 0;
      } },
      tabGroups: unsupported ? undefined : { update: async (id, properties) => {
        calls.push(['update', id, properties]);
        if (failUpdate) throw Error('Group removed');
      } },
    },
    sendResponse: (...args) => { response = args; },
    sendError: (...args) => { response = args; },
  });
  vm.runInContext(handler, context);
  return { calls, run: async data => {
    await context.handleTabsAction('req', 'tabs.group', data);
    return JSON.parse(JSON.stringify(response));
  } };
}
test('create and style, without activation/focus APIs', async () => {
  const s = setup();
  assert.deepEqual(await s.run({tabIds: [12], title: 'Research', color: 'blue'}),
    ['req', 'tabs.group', {groupId: 0}]);
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls)), [
    ['group', {tabIds: [12], createProperties: {windowId: 5}}], ['update', 0, {title: 'Research', color: 'blue'}]]);
});
test('reuse group zero without overwriting defaults', async () => {
  const s = setup();
  await s.run({tabIds: [12], groupId: 0});
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls)), [['group', {tabIds: [12], groupId: 0}]]);
});
test('clear title', async () => {
  const s = setup(); await s.run({tabIds: [12], title: ''});
  assert.equal(s.calls[1][2].title, '');
});
test('unsupported styling API fails before mutation', async () => {
  const s = setup({unsupported: true});
  assert.equal((await s.run({tabIds: [12]}))[1], 'UNSUPPORTED_API');
  assert.equal(s.calls.length, 0);
});
test('invalid arguments fail before mutation', async () => {
  for (const data of [{}, {tabIds: []}, {tabIds: [true]}, {tabIds: [1.5]},
    {tabIds: [12], groupId: -1}, {tabIds: [12], color: 'bad'}, {tabIds: [12], title: 1}]) {
    const s = setup(); assert.equal((await s.run(data))[1], 'INVALID_PARAMETER');
    assert.equal(s.calls.length, 0);
  }
});
test('group rejection does not style', async () => {
  const s = setup({failGroup: true});
  assert.equal((await s.run({tabIds: [12], color: 'blue'}))[1], 'API_ERROR');
  assert.equal(s.calls.length, 1);
});
test('partial success names group and does not retry', async () => {
  const s = setup({failUpdate: true});
  const response = await s.run({tabIds: [12], color: 'blue'});
  assert.equal(response[1], 'PARTIAL_SUCCESS'); assert.match(response[2], /group 0/);
  assert.equal(s.calls.length, 2);
});
