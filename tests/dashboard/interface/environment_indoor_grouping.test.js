// Run with: node --test tests/dashboard/interface/environment_indoor_grouping.test.js
// The Environment window lists one entry per physical sensor, not one per endpoint.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '../../..');
const matterSource = fs.readFileSync(path.join(root, 'subsystems/matter/static/js/matter-render.js'), 'utf8');
const envSource = fs.readFileSync(path.join(root, 'subsystems/environment/static/js/environment-render.js'), 'utf8');

const matterCode = [
  matterSource.slice(matterSource.indexOf('function matterKind(c)'),
    matterSource.indexOf('\nfunction ', matterSource.indexOf('function matterKinds(c)') + 10)),
  matterSource.slice(matterSource.indexOf('function matterEndpointSortValue'),
    matterSource.indexOf('function matterGroupedClientFromSerial')),
].join('\n');
const envCode = envSource.slice(
  envSource.indexOf('function envNumber'), envSource.indexOf('function envTempTextF'))
  + envSource.slice(
    envSource.indexOf('function environmentIndoorDevices'),
    envSource.indexOf('function environmentIndoorDeviceHtml'));

function context(clients) {
  const ctx = {
    window: { dashboardClientIsMatterEnvironment: () => true },
    S: { currentClients: clients },
    envSnapshot: () => ({}),
  };
  vm.createContext(ctx);
  vm.runInContext(matterCode, ctx);
  vm.runInContext(envCode, ctx);
  return ctx;
}

const sensor = (endpoint, kind, label, room, extra) => ({
  deviceID: `matter:1:${endpoint}`,
  matter_node_id: '1',
  matter_endpoint: String(endpoint),
  matter_kind: kind,
  matter_kinds: [kind],
  matter_node_label: label,
  matter_product_name: 'T310',
  matter_serial_number: '',
  zone_name: room,
  ...extra,
});

test('a T310 with no serial shows one entry holding both temperature and humidity', () => {
  const ctx = context([
    sensor(3, 'temperature', 'Tapo T310 TempSensor', 'Living Room', { temperature_c: 25 }),
    sensor(4, 'humidity', 'Tapo T310 HumiSensor', 'Living Room', { humidity_percent: 94 }),
    sensor(6, 'temperature', 'Tapo T310 TempSensor', 'Master Bedroom', { temperature_c: 21 }),
    sensor(7, 'humidity', 'Tapo T310 HumiSensor', 'Master Bedroom', { humidity_percent: 70 }),
  ]);
  ctx.window.dashboardMatterRelatedDeviceIDs = (id, clients) =>
    JSON.parse(JSON.stringify(ctx.matterPhysicalClientGroups(clients)
      .find(g => g.some(c => c.deviceID === id)).map(c => c.deviceID)));

  const devices = JSON.parse(JSON.stringify(ctx.environmentIndoorDevices()));

  assert.equal(devices.length, 2);
  assert.deepEqual(devices.map(d => [d.zone_name, Math.round(d.temperature_f), d.humidity_percent]),
    [['Living Room', 77, 94], ['Master Bedroom', 70, 70]]);
});

test('without the Matter helper each endpoint stays its own entry', () => {
  const ctx = context([
    sensor(3, 'temperature', 'Tapo T310 TempSensor', 'Living Room', { temperature_c: 25 }),
    sensor(4, 'humidity', 'Tapo T310 HumiSensor', 'Living Room', { humidity_percent: 94 }),
  ]);

  assert.equal(ctx.environmentIndoorDevices().length, 2);
});
