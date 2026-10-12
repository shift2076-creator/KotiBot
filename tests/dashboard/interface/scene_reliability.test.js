// Run with: node --test tests/dashboard/interface/scene_reliability.test.js
// Executes the actual Scene functions; transport and DOM are controlled fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(path.resolve(__dirname, '../../..', 'static/js/dashboard-actions.js'), 'utf8');
const queueSource = source.slice(source.indexOf('const dashboardHomeLightingSession'), source.indexOf('const DASHBOARD_HOME_LIGHTING_MODES'));
const batchSource = source.slice(source.indexOf('async function dashboardHomeSendLightingCommandBatch('), source.indexOf('async function dashboardHomeApplyConfiguredLightingMode('));
const syncSource = source.slice(source.indexOf('window.syncDashboardHomeModeButtons ='), source.indexOf('const DASHBOARD_HOME_ARMING_MODES'));

function fixture(fetch, crypto = { randomUUID: () => 'fixture-page' }) {
  const applied = [];
  const context = {
    crypto,
    window: {}, S: { currentClients: [{ deviceID: 'bad', clientName: 'Desk light' }] },
    console: { warn() {} },
    document: { querySelectorAll: () => [], getElementById: () => { throw new Error('Scene must not access an inline status'); } },
    dashboardHomeCleanLightingMode: value => value,
    dashboardHomeResolveTapoCommandPayload: value => value,
    dashboardHomeSetActiveLightingModeLocally() {},
    dashboardHomeCurrentArmMode: () => 'day',
    dashboardHomeActiveLightingModeFromServer: () => 'day',
    dashboardHomeLightingRetryDelay: async () => {},
    dashboardFetch: fetch,
  };
  context.window.applyDashboardTapoLightingState = data => applied.push(data);
  vm.createContext(context);
  vm.runInContext(syncSource + queueSource + batchSource, context);
  return { context, applied };
}

const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const tick = () => new Promise(resolve => setImmediate(resolve));

test('partial failure is reported once without replaying successful commands', async () => {
  let calls = 0;
  const { context, applied } = fixture(async () => {
    calls++;
    return response({ ok: false, results: [{ ok: true, deviceID: 'good' }, { ok: false, deviceID: 'bad', error: 'unavailable' }] });
  });
  await assert.rejects(context.dashboardHomeSendLightingCommandBatch([], 'day'), /Desk light: unavailable/);
  assert.equal(calls, 1);
  assert.equal(applied.length, 0);
});

test('HTTP errors, unreadable replies and network loss never replay the batch', async () => {
  const outcomes = [
    () => response({ error: 'server error' }, 500),
    () => ({ ok: true, status: 200, json: async () => { throw new Error('invalid JSON'); } }),
    () => { throw new Error('network lost after sending'); },
  ];
  for (const outcome of outcomes) {
    let calls = 0;
    const { context } = fixture(async () => { calls++; return outcome(); });
    await assert.rejects(context.dashboardHomeSendLightingCommandBatch([], 'day'));
    assert.equal(calls, 1);
  }
});

test('inconsistent success flag cannot hide a failed command', async () => {
  const { context } = fixture(async () => response({ ok: true, results: [{ ok: false, error: 'failed' }] }));
  await assert.rejects(context.dashboardHomeSendLightingCommandBatch([], 'day'), /failed/);
});

test('successful reply applies state exactly once', async () => {
  const { context, applied } = fixture(async () => response({ ok: true, results: [{ ok: true }] }));
  await context.dashboardHomeSendLightingCommandBatch([], 'day');
  assert.equal(applied.length, 1);
});

test('fifteen completed selections each execute and leave the queue reusable', async () => {
  const { context } = fixture();
  const seen = [];
  context.runDashboardHomeLightingMode = async mode => seen.push(mode);
  const modes = Array.from({ length: 15 }, (_, n) => ['day', 'evening', 'night'][n % 3]);
  for (const mode of modes) await context.window.setDashboardHomeLightMode(mode);
  assert.deepEqual(seen, modes);
});

test('every selection dispatches without waiting for an older response', async () => {
  const { context } = fixture();
  const seen = [];
  let release;
  context.runDashboardHomeLightingMode = async mode => {
    seen.push(mode);
    if (seen.length === 1) await new Promise(resolve => { release = resolve; });
  };
  const first = context.window.setDashboardHomeLightMode('day');
  const later = [];
  for (let n = 0; n < 14; n++) later.push(context.window.setDashboardHomeLightMode(n === 13 ? 'night' : 'evening'));
  assert.equal(seen.length, 15);
  assert.equal(seen[14], 'night');
  await Promise.all(later);
  release();
  await first;
});

test('an older failure still propagates after a newer selection succeeds', async () => {
  const { context } = fixture();
  let release;
  context.runDashboardHomeLightingMode = async mode => {
    if (mode === 'day') {
      await new Promise(resolve => { release = resolve; });
      throw new Error('old request failed');
    }
  };
  const first = context.window.setDashboardHomeLightMode('day');
  const rejected = assert.rejects(first, /old request failed/);
  await context.window.setDashboardHomeLightMode('evening');
  release();
  await rejected;
});

test('an older HTTP reply cannot reapply stale lighting state', async () => {
  let release;
  const { context, applied } = fixture(async () => new Promise(resolve => { release = resolve; }));
  const first = context.dashboardHomeSendLightingCommandBatch([], 'day');
  context.runDashboardHomeLightingMode = async () => {};
  await context.window.setDashboardHomeLightMode('evening');
  release(response({ ok: true, results: [{ ok: true }], activeSchemes: { home: 'day' } }));
  await first;
  assert.equal(applied.length, 0);
});

test('scene errors propagate without inline messages and next click can recover', async () => {
  const { context } = fixture();
  context.runDashboardHomeLightingMode = async () => { throw new Error('<b>device offline</b>'); };
  await assert.rejects(context.window.setDashboardHomeLightMode('day'), /device offline/);
  context.window.syncDashboardHomeModeButtons();
  context.runDashboardHomeLightingMode = async () => {};
  await context.window.setDashboardHomeLightMode('evening');
  await tick();
});

test('plain HTTP contexts without randomUUID can still dispatch Scenes', async () => {
  const { context } = fixture(undefined, {});
  const seen = [];
  context.runDashboardHomeLightingMode = async mode => seen.push(mode);
  await context.window.setDashboardHomeLightMode('day');
  assert.deepEqual(seen, ['day']);
});

// Exercise the full button-to-configuration-to-payload path, without replacing
// scene planning, mode selection, or the loader with canned results.
const tapoSource = fs.readFileSync(path.resolve(__dirname, '../../..',
  'subsystems/client-tapo/static/js/tapo-actions.js'), 'utf8');
const apiSource = fs.readFileSync(path.resolve(__dirname, '../../..', 'static/js/dashboard-api.js'), 'utf8');
function fullSceneFixture(fetch, clients = []) {
  const context = { console: { warn() {} }, crypto: { randomUUID: () => 'full-page' },
    appState: { currentClients: clients }, dashboardFetch: fetch,
    document: { querySelectorAll: () => [] },
    localStorage: { removeItem() {}, getItem() { return null; } },
    setTimeout, clearTimeout, setInterval, clearInterval,
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(source, context);
  vm.runInContext(apiSource.slice(apiSource.indexOf('window.applyDashboardTapoLightingState ='),
    apiSource.indexOf('const DASHBOARD_BOOTSTRAP_MAX_AGE_MS')), context);
  vm.runInContext('let tapoLightingStateLoadPromise = null;\n' +
    tapoSource.slice(tapoSource.indexOf('function getTapoLightingState()'),
      tapoSource.indexOf('async function saveTapoLightingStateNow()')), context);
  return context;
}
const bulb = (id, room = 'Studio') => ({ deviceID: id, clientRole: 'TAPO', provisioned: true,
  tapo_kind: 'bulb', zone_name: room, tapo_is_on: false,
  tapo_supports_power: true, tapo_supports_brightness: true,
  tapo_supports_color: true, tapo_supports_color_temp: true });

test('first click waits for real configuration and sends saved On + brightness + color in one batch', async () => {
  const requests = [];
  let load;
  const context = fullSceneFixture(async (url, opts) => {
    requests.push({ url, body: opts?.body && JSON.parse(opts.body) });
    if (url.startsWith('/api/tapo/lighting-state')) {
      return new Promise(resolve => { load = resolve; });
    }
    return response({ ok: true, results: [{ deviceID: 'tapo:a', ok: true }],
      schemes: {}, modeConfig: { evening: { 'room:Studio': { power: 'on', preset: 'evening' } } },
      activeSchemes: { home: 'evening' } });
  }, [bulb('tapo:a')]);
  const click = context.setDashboardHomeLightMode('evening');
  await tick();
  assert.equal(requests.length, 1);
  assert.equal(context.TAPO_LIGHTING_STATE.loaded, undefined);
  load(response({ ok: true, schemes: { 'device:tapo:a': [
    { mode: 'evening', preset: { brightness: 24, hue: 123, saturation: 60 } }
  ] }, modeConfig: { evening: { 'room:Studio': { power: 'on', preset: 'evening' } } }, activeSchemes: {} }));
  await click;
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[1].body.commands.map(c => [c.action, c.value]),
    [['on', undefined], ['brightness_no_power', 24], ['color_no_power', { hue: 123, saturation: 60 }]]);
});

test('failed configuration load never dispatches defaults and the next click can recover', async () => {
  const requests = [];
  let available = false;
  const context = fullSceneFixture(async (url, opts) => {
    requests.push(url);
    if (url.startsWith('/api/tapo/lighting-state')) {
      return response(available ? { ok: true, schemes: {}, modeConfig: {}, activeSchemes: {} }
        : { ok: false, error: 'unavailable' }, available ? 200 : 503);
    }
    return response({ ok: true, results: [], schemes: {}, modeConfig: {}, activeSchemes: {} });
  }, [bulb('tapo:a')]);
  await assert.rejects(context.setDashboardHomeLightMode('day'), /settings could not be loaded/);
  assert.equal(requests.filter(url => url.includes('command-batch')).length, 0);
  available = true;
  await context.setDashboardHomeLightMode('evening');
  assert.equal(requests.filter(url => url.includes('command-batch')).length, 1);
});

test('room devices, individual devices and extender children enter the same scene payload', async () => {
  let payload;
  const context = fullSceneFixture(async (url, opts) => {
    payload = JSON.parse(opts.body);
    return response({ ok: true, results: [], schemes: {}, modeConfig: {}, activeSchemes: {} });
  }, [bulb('tapo:a'), { ...bulb('tapo:b'), tapo_room_power: false },
    { deviceID: 'outlet', clientRole: 'TAPO', provisioned: true, tapo_kind: 'outlet',
      tapo_supports_power: true, tapo_room_power: false,
      tapo_parent_device_id: 'tapo:strip', tapo_child_id: 'socket-2' }]);
  context.applyDashboardTapoLightingState({ schemes: {}, activeSchemes: {},
    modeConfig: { day: { 'room:Studio': { power: 'on', preset: 'day' },
      'device:tapo:b': { power: 'on', preset: 'evening' }, 'device:outlet': 'on' } } });
  await context.setDashboardHomeLightMode('day');
  assert.deepEqual([...new Set(payload.commands.map(c => c.deviceID))], ['tapo:a', 'tapo:b', 'tapo:strip']);
  assert.equal(payload.commands.at(-1).action, 'child_on');
  assert.equal(payload.commands.at(-1).value.child_id, 'socket-2');
});

test('non-home preset batches leave home selection and configuration intact', async () => {
  let payload;
  const context = fullSceneFixture(async (url, opts) => {
    payload = JSON.parse(opts.body);
    return response({ ok: true, results: [], activeSchemes: {}, modeConfig: {}, schemes: {} });
  }, [bulb('tapo:a')]);
  context.applyDashboardTapoLightingState({ activeSchemes: { home: 'night' }, modeConfig: { night: { 'room:Studio': 'off' } } });
  await context.dashboardHomeApplyLightingModeToClients(context.appState.currentClients, 'day');
  assert.equal(payload.activeHomeMode, undefined);
  assert.equal(payload.sceneSession, undefined);
  assert.equal(payload.commands.length, 2);
  assert.equal(context.TAPO_LIGHTING_STATE.activeSchemes.home, 'night');
});

test('preset powerOn joins every device setting in one request instead of a second power round', async () => {
  const payloads = [];
  const clients = Array.from({ length: 12 }, (_, n) => bulb(`tapo:${n}`));
  const context = fullSceneFixture(async (url, opts) => {
    payloads.push(JSON.parse(opts.body));
    return response({ ok: true, results: clients.map(client => ({ deviceID: client.deviceID, ok: true })) });
  }, clients);
  context.tapoResolveDashboardDeviceTarget = deviceID => ({ deviceID });
  vm.runInContext(tapoSource.slice(tapoSource.indexOf('async function sendTapoLightingPresetToDevice('),
    tapoSource.indexOf('function handleTapoLightingPresetResults')), context);
  const results = await context.sendTapoLightingPresetsToDevices(clients.map(c => c.deviceID),
    () => ({ brightness: 31, hue: 210, saturation: 80 }), 'evening', { powerOn: true });
  assert.equal(payloads.length, 1);
  assert.equal(payloads[0].commands.length, 36);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 12);
  for (const client of clients) {
    assert.deepEqual(payloads[0].commands.filter(c => c.deviceID === client.deviceID).map(c => c.action),
      ['on', 'brightness_no_power', 'color_no_power']);
  }
});

test('late non-home reply cannot overwrite a newer device result and metadata is released', async () => {
  const releases = [], applied = [];
  const context = fullSceneFixture(async () => new Promise(resolve => releases.push(resolve)), [bulb('tapo:a')]);
  context.updateTapoCardState = state => applied.push(state);
  const commands = [{ deviceID: 'tapo:a', action: 'on' }];
  const older = context.dashboardHomeSendLightingCommandBatch(commands);
  const newer = context.dashboardHomeSendLightingCommandBatch(commands);
  releases[1](response({ ok: true, results: [{ deviceID: 'tapo:a', ok: true, client: { tapo_brightness: 70 } }] }));
  await newer;
  releases[0](response({ ok: true, results: [{ deviceID: 'tapo:a', ok: true, client: { tapo_brightness: 30 } }] }));
  await older;
  assert.deepEqual(applied, [{ tapo_brightness: 70 }]);
  assert.equal(vm.runInContext('dashboardHomeTapoPendingBatches.size', context), 0);
});
