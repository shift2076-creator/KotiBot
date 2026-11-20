// Run with: node --test tests/dashboard/shelves/jellyfin_shelf_ui.test.js
// Executes the real shelf script against a minimal DOM and a controlled fetch.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'static/js/dashboard-media-shelf.js'),
  'utf8'
);
const links = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'static/js/dashboard-service-links.js'), 'utf8');

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.style = {};
    this.listeners = {};
    this.hidden = false;
    this.className = '';
    this.textContent = '';
    this.classList = { add: name => { this.className = `${this.className} ${name}`.trim(); } };
  }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
  append(...nodes) { nodes.forEach(n => this.appendChild(n)); }
  replaceChildren(...nodes) { this.children = []; nodes.forEach(n => this.appendChild(n)); }
  setAttribute(name, value) { this.attrs[name] = value; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); }
}

function findAll(node, className, found = []) {
  if (String(node.className).split(' ').includes(className)) found.push(node);
  node.children.forEach(child => findAll(child, className, found));
  return found;
}

const text = node => [node.textContent, ...node.children.map(text)].join('');
const control = (section, label) =>
  findAll(section, 'dashboard-home-light-btn').find(node => text(node) === label);

function fixture(replies, hostname = '192.168.4.90') {
  const section = new FakeNode('section');
  const home = { querySelector: () => section };
  const calls = [];
  const opened = [];
  const clock = { now: 1_000_000 };
  const context = {
    window: { open: (...args) => opened.push(args) },
    location: { protocol: 'https:', hostname },
    document: { createElement: tag => new FakeNode(tag), querySelector: () => section },
    Date: { now: () => clock.now },
    fetch: async (url, options = {}) => {
      calls.push(options.method ? `${options.method} ${url}` : url);
      if (options.method === 'POST') return { ok: context.postOk !== false, json: async () => ({}) };
      const next = replies.length > 1 ? replies.shift() : replies[0];
      if (next instanceof Error) throw next;
      return { ok: next.ok !== false, json: async () => next.body };
    },
    postOk: true,
  };
  vm.createContext(context);
  vm.runInContext(links, context);
  vm.runInContext(source, context);
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const sync = async () => {
    context.window.syncDashboardHomeMediaShelf(home);
    await settle();
  };
  return { section, calls, opened, clock, sync, settle, context };
}

const id = ch => ch.repeat(32);
const item = (extra = {}) => ({
  id: id('a'), title: 'Nosferatu', subtitle: '1922', year: 1922,
  overview: 'A vampire comes to town.', percent: 25, minutes_left: 75,
  runtime_minutes: 100, image: '/api/shelves/jellyfin/image/' + id('a') + '?tag=t', ...extra,
});
const two = () => ({ body: { available: true, items: [item(), item({ id: id('b'), title: 'Metropolis', year: 1927, percent: 60, minutes_left: 20, runtime_minutes: 150, image: '' })] } });

test('shows one title: year after it, overview, length and time left, poster', async () => {
  const { section, sync } = fixture([two()]);
  await sync();
  assert.equal(section.hidden, false);
  assert.equal(findAll(section, 'dashboard-home-nowplaying').length, 1);
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Nosferatu');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-year')[0].textContent, '1922');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-overview')[0].textContent, 'A vampire comes to town.');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-meta')[0].textContent, '1h 40m · 1h 15m left');
  assert.equal(findAll(section, 'dashboard-home-media-image').length, 1);
  const [bar] = findAll(section, 'dashboard-home-media-progress');
  assert.equal(bar.attrs['aria-valuenow'], '25');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-brand').length, 1);
});

test('controls reuse the Scenes circle component', async () => {
  const { section, sync } = fixture([two()]);
  await sync();
  const labels = findAll(section, 'dashboard-home-light-btn').map(text);
  assert.deepEqual(labels, ['Resume', 'Restart', 'Remove']);
  for (const button of findAll(section, 'dashboard-home-light-btn')) {
    assert.equal(findAll(button, 'ui-icon-circle').length, 1);
  }
});

test('the bottom bar cycles titles, wraps, and marks the current one', async () => {
  const { section, sync } = fixture([two()]);
  await sync();
  const [prev, next] = findAll(section, 'dashboard-home-nowplaying-step');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-segment').length, 2);
  next.listeners.click();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Metropolis');
  assert.equal(findAll(section, 'dashboard-home-nowplaying-year')[0].textContent, '1927');
  const [first, second] = findAll(section, 'dashboard-home-nowplaying-segment');
  assert.equal(second.attrs['aria-current'], 'true');
  assert.equal(first.attrs['aria-current'], undefined);
  findAll(section, 'dashboard-home-nowplaying-step')[1].listeners.click();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Nosferatu');
  findAll(section, 'dashboard-home-nowplaying-step')[0].listeners.click();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Metropolis');
  findAll(section, 'dashboard-home-nowplaying-segment')[0].listeners.click();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Nosferatu');
  assert.ok(prev);
});

test('a single title has no bottom bar', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item()] } }]);
  await sync();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-nav').length, 0);
});

test('an episode shows its season marker after the series title', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item({ title: 'Some Series', year: null, subtitle: 'S2E5 · The Pilot' })] } }]);
  await sync();
  assert.equal(findAll(section, 'dashboard-home-nowplaying-year')[0].textContent, 'S2E5 · The Pilot');
});

test('text is inserted as text, never as markup', async () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const { section, sync } = fixture([{ body: { available: true, items: [item({ title: hostile, overview: hostile })] } }]);
  await sync();
  for (const name of ['dashboard-home-nowplaying-title', 'dashboard-home-nowplaying-overview']) {
    const [node] = findAll(section, name);
    assert.equal(node.textContent, hostile);
    assert.equal(node.children.length, 0);
  }
});

test('unavailable, empty or failing replies hide the shelf', async () => {
  for (const reply of [
    { body: { available: false, reason: 'unavailable', items: [] } },
    { body: { available: true, items: [] } },
    { ok: false, body: null },
    new Error('network down'),
  ]) {
    const { section, sync } = fixture([reply]);
    await sync();
    assert.equal(section.hidden, true);
    assert.equal(section.children.length, 0);
  }
});

test('refreshes at most once every thirty seconds', async () => {
  const { calls, clock, sync } = fixture([{ body: { available: true, items: [item()] } }]);
  await sync();
  clock.now += 29_000;
  await sync();
  assert.equal(calls.length, 1);
  clock.now += 2_000;
  await sync();
  assert.equal(calls.length, 2);
});

test('an unchanged list is not rebuilt, a changed one is, and the shown title is kept', async () => {
  const changed = two();
  changed.body = { available: true, items: [item({ id: id('c'), title: 'New' }), ...changed.body.items.map(i => ({ ...i, percent: 70 }))] };
  const { section, clock, sync } = fixture([two(), changed]);
  await sync();
  findAll(section, 'dashboard-home-nowplaying-step')[1].listeners.click();
  const shown = section.children[0];
  await sync();
  assert.equal(section.children[0], shown);
  clock.now += 31_000;
  await sync();
  assert.notEqual(section.children[0], shown);
  // The list gained a title in front; the viewer stays on Metropolis.
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Metropolis');
  assert.equal(findAll(section, 'dashboard-home-media-progress')[0].attrs['aria-valuenow'], '70');
});

test('a poster that fails to load falls back to the initial', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item()] } }]);
  await sync();
  const [image] = findAll(section, 'dashboard-home-media-image');
  image.listeners.error();
  assert.equal(findAll(section, 'dashboard-home-media-image').length, 0);
  assert.equal(findAll(section, 'dashboard-home-media-initial')[0].textContent, 'N');
});

test('Resume links to the title in Jellyfin on the same host', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item()] } }]);
  await sync();
  const resume = control(section, 'Resume');
  assert.equal(resume.tagName, 'a');
  assert.equal(resume.href, 'https://192.168.4.90:8096/web/#/details?id=' + id('a'));
  assert.equal(resume.target, '_blank');
  assert.equal(resume.rel, 'noopener noreferrer');
});

test('Resume follows the domain the page was opened on', async () => {
  for (const domain of ['kotibot.lan', 'kotibot.app']) {
    const { section, sync } = fixture([{ body: { available: true, items: [item()] } }], domain);
    await sync();
    assert.equal(control(section, 'Resume').href, `https://jellyfin.${domain}/web/#/details?id=` + id('a'));
  }
});

test('a bad id leaves Resume disabled rather than linking anywhere', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item({ id: 'not-an-id' })] } }]);
  await sync();
  const resume = control(section, 'Resume');
  assert.equal(resume.tagName, 'button');
  assert.equal(resume.disabled, true);
  assert.equal(resume.href, undefined);
});

test('Remove posts a reset for that title and reloads the list', async () => {
  const { section, calls, sync, settle } = fixture([two(), { body: { available: true, items: [item({ id: id('b'), title: 'Metropolis' })] } }]);
  await sync();
  control(section, 'Remove').listeners.click();
  await settle(); await settle(); await settle();
  assert.ok(calls.includes('POST /api/shelves/jellyfin/progress/' + id('a') + '/reset'));
  assert.equal(calls.filter(call => call === '/api/shelves/jellyfin/continue').length, 2);
  assert.equal(findAll(section, 'dashboard-home-nowplaying-title')[0].textContent, 'Metropolis');
});

test('Restart posts a reset, then opens the title in Jellyfin', async () => {
  const { section, calls, opened, sync, settle } = fixture([two()]);
  await sync();
  control(section, 'Restart').listeners.click();
  await settle(); await settle();
  assert.ok(calls.includes('POST /api/shelves/jellyfin/progress/' + id('a') + '/reset'));
  assert.equal(opened.length, 1);
  assert.equal(opened[0][0], 'https://192.168.4.90:8096/web/#/details?id=' + id('a'));
});

test('Restart does not open Jellyfin when the reset fails', async () => {
  const { section, opened, sync, settle, context } = fixture([two()]);
  await sync();
  context.postOk = false;
  control(section, 'Restart').listeners.click();
  await settle(); await settle();
  assert.equal(opened.length, 0);
});
