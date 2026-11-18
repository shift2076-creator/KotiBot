// Run with: node --test tests/dashboard/interface/matter_sensor_grouping.test.js
// Executes the real Matter sensor grouping with the endpoints a Tapo H110 reports.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'subsystems/matter/static/js/matter-render.js'), 'utf8');
const kindsStart = source.indexOf('function matterKind(c)');
const code = [
  source.slice(kindsStart, source.indexOf('\nfunction ', source.indexOf('function matterKinds(c)') + 10)),
  source.slice(source.indexOf('function matterEndpointSortValue'), source.indexOf('function matterGroupedClientFromSerial')),
].join('\n');

function context() {
  const ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return ctx;
}

const sensor = (endpoint, kind, label, product) => ({
  deviceID: `matter:1:${endpoint}`,
  matter_node_id: '1',
  matter_endpoint: String(endpoint),
  matter_kind: kind,
  matter_kinds: [kind],
  matter_node_label: label,
  matter_product_name: product,
  matter_serial_number: '',
});

test('each T310 temperature and humidity pair is one device when no serial is reported', () => {
  const ctx = context();
  const clients = [
    sensor(3, 'temperature', 'Tapo T310 TempSensor', 'T310'),
    sensor(4, 'humidity', 'Tapo T310 HumiSensor', 'T310'),
    sensor(6, 'temperature', 'Tapo T310 TempSensor', 'T310'),
    sensor(7, 'humidity', 'Tapo T310 HumiSensor', 'T310'),
  ];

  const groups = JSON.parse(JSON.stringify(
    ctx.matterPhysicalClientGroups(clients).map(g => g.map(c => c.matter_endpoint))
  ));

  assert.deepEqual(groups.sort(), [['3', '4'], ['6', '7']]);
});

test('a contact or motion sensor next to a T310 is not merged into it', () => {
  const ctx = context();
  const clients = [
    sensor(3, 'temperature', 'Tapo T310 TempSensor', 'T310'),
    sensor(4, 'humidity', 'Tapo T310 HumiSensor', 'T310'),
    sensor(5, 'contact', 'Tapo T110', 'T110'),
  ];

  const groups = JSON.parse(JSON.stringify(
    ctx.matterPhysicalClientGroups(clients).map(g => g.map(c => c.matter_endpoint))
  ));

  assert.deepEqual(groups.sort(), [['3', '4'], ['5']]);
});
