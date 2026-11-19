// Run with: node --test tests/dashboard/shelves/news_shelf.test.js
// Executes the real News card code against a minimal DOM with hostile feed text.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'static/js/dashboard-news-shelf.js'), 'utf8');

class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.className = '';
    this.textContent = '';
    this.hidden = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...kids) { this.children = kids; }
}

function run(groups) {
  const window = {};
  const ctx = {
    window,
    document: { createElement: tag => new Node(tag), querySelector: () => null },
    fetch: async () => ({ ok: true, json: async () => ({ groups }) }),
    Date, URL, JSON, Number, Math, Promise, String, Array,
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  const section = new Node('section');
  const home = { querySelector: () => section };
  window.syncDashboardHomeNewsShelf(home);
  return new Promise(resolve => setTimeout(() => {
    ctx.document.querySelector = () => section;
    window.syncDashboardHomeNewsShelf(home);
    resolve(section);
  }, 20));
}

const now = new Date().toISOString();

test('feed text is shown as text and never as markup', async () => {
  const section = await run([{ id: 'a', title: '<img src=x onerror=alert(1)>', items: [
    { title: '<script>alert(1)</script>', link: 'https://e.test/1', published: now }] }]);
  const walk = n => [n, ...n.children.flatMap(walk)];
  const all = walk(section);
  assert.ok(all.some(n => n.textContent === '<script>alert(1)</script>'));
  assert.ok(all.every(n => !('innerHTML' in n)));
});

test('only http(s) headlines become links and they open safely', async () => {
  const section = await run([{ id: 'a', title: 'Feed', items: [
    { title: 'good', link: 'https://e.test/1', published: now },
    { title: 'bad', link: 'javascript:alert(1)', published: now },
    { title: 'none', link: '', published: now }] }]);
  const walk = n => [n, ...n.children.flatMap(walk)];
  const heads = walk(section).filter(n => /(^| )dashboard-activity-event( |$)/.test(n.className));
  assert.equal(heads.length, 3);
  assert.equal(heads[0].tag, 'a');
  assert.equal(heads[0].href, 'https://e.test/1');
  assert.equal(heads[0].rel, 'noopener noreferrer');
  assert.equal(heads[1].tag, 'span');
  assert.equal(heads[1].href, undefined);
  assert.equal(heads[2].tag, 'span');
  const names = walk(section).filter(n => n.className === 'dashboard-activity-name').map(n => n.textContent);
  assert.deepEqual(names, ['e.test', 'Feed', 'Feed']);
});

test('the card hides itself when there is nothing to show', async () => {
  const section = await run([]);
  assert.equal(section.hidden, true);
});

test('ages read as minutes, hours and days', async () => {
  const ago = ms => new Date(Date.now() - ms).toISOString();
  const section = await run([{ id: 'a', title: 'F', items: [
    { title: 'm', link: '', published: ago(5 * 60000) },
    { title: 'h', link: '', published: ago(3 * 3600000) },
    { title: 'd', link: '', published: ago(2 * 86400000) }] }]);
  const walk = n => [n, ...n.children.flatMap(walk)];
  const times = walk(section).filter(n => n.className === 'dashboard-activity-time').map(n => n.textContent);
  assert.deepEqual(times, ['5m', '3h', '2d']);
});
