// Run with: node --test tests/dashboard/interface/zone_menu_without_room_power.test.js
// Executes the real renderTapoRoomActions: the zone menu stays when no device takes part in room power.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '../../..');
const render = fs.readFileSync(path.join(root, 'subsystems/client-tapo/static/js/tapo-render.js'), 'utf8');
const actions = fs.readFileSync(path.join(root, 'subsystems/client-tapo/static/js/tapo-actions.js'), 'utf8');
const source = render.slice(render.indexOf('window.renderTapoRoomActions = function'), render.indexOf('// Every Tapo title icon'));

function roomActions(bulbs, controls) {
  const context = {
    window: { dashboardIconHtml: name => `<i data-icon="${name}"></i>` },
    S: {},
    tapoRenderBool: value => (value === true || value === false ? value : null),
    tapoEsc: value => String(value ?? ''),
    getTapoRenderRoomSchemeMatch: () => ({ key: '', schemes: [] }),
    renderTapoFavoriteSchemeButton: () => '',
    tapoRenderSchemeIsActive: () => false,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.window.renderTapoRoomActions('Kitchen', bulbs, controls);
}

const bulb = (id, extra = {}) => ({ deviceID: id, tapo_kind: 'bulb', tapo_is_bulb: true, ...extra });
const plug = (id, extra = {}) => ({ deviceID: id, tapo_kind: 'plug', tapo_is_bulb: false, ...extra });

test('kitchen: every device opted out of room power keeps the zone menu and hides the power button', () => {
  const html = roomActions(
    [bulb('tapo:nightlight', { tapo_room_power: false }), bulb('tapo:stovetop', { tapo_room_power: false })],
    [plug('tapo:coffee', { tapo_room_power: false })],
  );
  assert.match(html, /room-light-settings/);
  assert.match(html, /data-tapo-room-settings="1"/);
  assert.match(html, /data-tapo-room="Kitchen"/);
  assert.doesNotMatch(html, /room-light-power/);
});

test('a room with a room-power light shows the power button and the zone menu', () => {
  const html = roomActions([bulb('tapo:a', { tapo_room_power: true, tapo_is_on: true })], []);
  assert.match(html, /room-light-power/);
  assert.match(html, /room-light-settings/);
  assert.match(html, /data-tapo-device-ids="tapo:a"/);
});

test('a room with no Tapo devices renders nothing', () => {
  assert.equal(roomActions([], []), '');
});

test('the lights modal opens in zone mode from the menu even with no room-power lights', () => {
  assert.ok(actions.includes('const isRoom = Boolean(data.tapoDeviceIds) || data.tapoRoomSettings === "1";'));
  assert.ok(actions.includes('schemesSection.hidden = nonLight || (isRoom && !roomHasLights);'));
});
