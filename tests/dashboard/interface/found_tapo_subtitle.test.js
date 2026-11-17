// Run with: node --test tests/dashboard/interface/found_tapo_subtitle.test.js
// Executes the real New Device Found title/subtitle functions with controlled fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'subsystems/matter/static/js/matter-render.js'), 'utf8');
const code = source.slice(
  source.indexOf('function matterFoundTapoKindLabel'), source.indexOf('function matterFoundTapoIcon'));

function context() {
  const ctx = {
    window: { dashboardDeviceTypeName: c => `Tapo ${c.tapo_model} ${c.tapo_kind === 'plug' ? 'Plug' : 'Bulb'}` },
    matterConnectedHubSubtitle: (c, fallback) => fallback,
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return ctx;
}

test('your Tapo name is the title and the device model is the subtitle', () => {
  const ctx = context();
  const bulb = { deviceID: 'tapo:a', clientName: 'Hallway', tapo_model: 'L530E(US)', tapo_kind: 'bulb' };

  assert.equal(ctx.matterFoundTapoTitle(bulb), 'Hallway');
  assert.equal(ctx.matterFoundTapoSubtitle(bulb), 'Tapo L530E(US) Bulb');
});

test('a device still carrying the generated name shows its type, not a repeat', () => {
  const ctx = context();
  const plug = { deviceID: 'tapo:b', clientName: 'Tapo P115 Plug', tapo_model: 'P115', tapo_kind: 'plug' };

  assert.equal(ctx.matterFoundTapoTitle(plug), 'Tapo P115 Plug');
  assert.equal(ctx.matterFoundTapoSubtitle(plug), 'Plug');
});
