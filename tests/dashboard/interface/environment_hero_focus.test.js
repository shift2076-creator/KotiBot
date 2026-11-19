// Run with: node --test tests/dashboard/interface/environment_hero_focus.test.js
// Which outdoor reading takes the second hero slot on the Home weather tile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(root, 'static/js/dashboard-render.js'), 'utf8');
const code = source.slice(
  source.indexOf('const DASHBOARD_HOME_ENVIRONMENT_FOCUS = ['),
  source.indexOf('function dashboardHomeEnvironmentLoadingSection()'));

function fresh() {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(code + ';this.focus = dashboardHomeEnvironmentFocusId;', ctx);
  return ctx.focus;
}

const snap = (aqi, o = {}) => ({ air_quality: { aqi }, outdoor: { humidity_percent: 50, wind_mph: 5, precip_chance_percent: 10, condition: 'Clear', ...o } });

test('air quality is the default when nothing is pressing', () => {
  assert.equal(fresh()(snap(40)), 'air_quality');
});

test('bad air stays on the hero row', () => {
  assert.equal(fresh()(snap(138)), 'air_quality');
});

test('a rainy day promotes the chance of rain', () => {
  assert.equal(fresh()(snap(30, { precip_chance_percent: 80, condition: 'Light Rain' })), 'precip');
});

test('current rain promotes precip even when the chance is missing', () => {
  assert.equal(fresh()(snap(30, { precip_chance_percent: null, condition: 'Heavy Rain' })), 'precip');
});

test('wind and humidity are promoted at their lines', () => {
  assert.equal(fresh()(snap(30, { wind_mph: 25 })), 'wind');
  assert.equal(fresh()(snap(30, { humidity_percent: 95 })), 'outdoor_humidity');
});

test('the reading furthest past its line wins', () => {
  // wind 40/20 = 2.0 beats precip 60/50 = 1.2
  assert.equal(fresh()(snap(30, { wind_mph: 40, precip_chance_percent: 60 })), 'wind');
});

test('missing readings never promote', () => {
  assert.equal(fresh()({ air_quality: {}, outdoor: {} }), 'air_quality');
  assert.equal(fresh()({}), 'air_quality');
});

test('a promoted reading is held until it drops well below its line', () => {
  const focus = fresh();
  assert.equal(focus(snap(30, { precip_chance_percent: 60 })), 'precip');
  assert.equal(focus(snap(30, { precip_chance_percent: 47 })), 'precip');   // 0.94, held
  assert.equal(focus(snap(30, { precip_chance_percent: 40 })), 'air_quality'); // 0.8, released
});

test('a different reading crossing its line takes over from a held one', () => {
  const focus = fresh();
  assert.equal(focus(snap(30, { precip_chance_percent: 60 })), 'precip');
  assert.equal(focus(snap(30, { precip_chance_percent: 47, wind_mph: 22 })), 'wind');
});
