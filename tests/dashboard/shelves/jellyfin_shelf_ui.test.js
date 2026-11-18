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
  }
  appendChild(child) { child.parent = this; this.children.push(child); return child; }
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

function fixture(replies) {
  const section = new FakeNode('section');
  const home = { querySelector: () => section };
  const calls = [];
  const clock = { now: 1_000_000 };
  const context = {
    window: {},
    document: { createElement: tag => new FakeNode(tag), querySelector: () => section },
    Date: { now: () => clock.now },
    fetch: async url => {
      calls.push(url);
      const next = replies.length > 1 ? replies.shift() : replies[0];
      if (next instanceof Error) throw next;
      return { ok: next.ok !== false, json: async () => next.body };
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  const sync = async () => {
    context.window.syncDashboardHomeMediaShelf(home);
    await new Promise(resolve => setImmediate(resolve));
  };
  return { section, calls, clock, sync };
}

const item = (extra = {}) => ({
  id: 'a'.repeat(32), title: 'Nosferatu', subtitle: '1922', percent: 25,
  minutes_left: 75, image: '/api/shelves/jellyfin/image/' + 'a'.repeat(32) + '?tag=t', ...extra,
});

test('renders a card per item with progress, time left and poster', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item(), item({ title: 'Metropolis', subtitle: '', minutes_left: 20, image: '' })] } }]);
  await sync();
  assert.equal(section.hidden, false);
  assert.equal(findAll(section, 'dashboard-home-media-card').length, 2);
  const [bar] = findAll(section, 'dashboard-home-media-progress');
  assert.equal(bar.attrs['aria-valuenow'], '25');
  assert.equal(bar.children[0].style.width, '25%');
  const metas = findAll(section, 'dashboard-home-media-meta').map(n => n.textContent);
  assert.equal(metas[0], '1922 · 1h 15m left');
  assert.equal(metas[1], '20m left');
  assert.equal(findAll(section, 'dashboard-home-media-image').length, 1);
});

test('titles are inserted as text, never as markup', async () => {
  const hostile = '<img src=x onerror=alert(1)>';
  const { section, sync } = fixture([{ body: { available: true, items: [item({ title: hostile })] } }]);
  await sync();
  const [title] = findAll(section, 'dashboard-home-media-title');
  assert.equal(title.textContent, hostile);
  assert.equal(title.children.length, 0);
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

test('an unchanged list is not rebuilt, and a changed one is', async () => {
  const { section, clock, sync } = fixture([
    { body: { available: true, items: [item()] } },
    { body: { available: true, items: [item({ percent: 60 })] } },
  ]);
  await sync();
  const first = section.children[1];
  await sync();
  assert.equal(section.children[1], first);
  clock.now += 31_000;
  await sync();
  assert.notEqual(section.children[1], first);
  assert.equal(findAll(section, 'dashboard-home-media-progress')[0].attrs['aria-valuenow'], '60');
});

test('a poster that fails to load falls back to the initial', async () => {
  const { section, sync } = fixture([{ body: { available: true, items: [item()] } }]);
  await sync();
  const [image] = findAll(section, 'dashboard-home-media-image');
  image.listeners.error();
  assert.equal(findAll(section, 'dashboard-home-media-image').length, 0);
  assert.equal(findAll(section, 'dashboard-home-media-initial')[0].textContent, 'N');
});
