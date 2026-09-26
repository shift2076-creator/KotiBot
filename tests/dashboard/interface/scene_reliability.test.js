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
