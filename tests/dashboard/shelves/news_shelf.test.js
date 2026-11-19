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
    this.attributes = {};
    this.className = '';
    this.textContent = '';
    this.hidden = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...kids) { this.children = kids; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

const walk = n => [n, ...n.children.flatMap(walk)];
const has = (n, name) => n.className.split(' ').includes(name);

async function run(items) {
  const window = {};
  const section = new Node('section');
  const home = { querySelector: () => section };
  const ctx = {
    window,
    document: { createElement: tag => new Node(tag), querySelector: () => null },
    fetch: async () => ({ ok: true, json: async () => ({ items }) }),
    Date, URL, JSON, Number, Math, Promise, String, Array, Set, Boolean,
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  window.syncDashboardHomeNewsShelf(home);
  await new Promise(resolve => setTimeout(resolve, 20));
  ctx.document.querySelector = () => section;
  window.syncDashboardHomeNewsShelf(home);
  return { section, window };
}

const now = new Date().toISOString();
const item = (title, over = {}) => ({ title, link: 'https://e.test/1', feed: 'Feed', feed_id: 'a', kind: 'article', minutes: 0, published: now, ...over });
const rows = section => section.children.filter(n => n.tag === 'div' && n.className === '');
const subtitles = section => walk(section).filter(n => has(n, 'dashboard-home-subtitle')).map(n => n.textContent);

test('feed text is shown as text and never as markup', async () => {
  const { section } = await run([item('<script>alert(1)</script>', { feed: '<img src=x onerror=alert(1)>' })]);
  const all = walk(section);
  assert.ok(all.some(n => n.textContent === '<script>alert(1)</script>'));
  assert.ok(all.some(n => n.textContent.startsWith('<img src=x onerror=alert(1)>')));
  assert.ok(all.every(n => !('innerHTML' in n)));
});

test('only http(s) headlines become links and they open safely', async () => {
  const { section } = await run([
    item('good'), item('bad', { link: 'javascript:alert(1)' }), item('none', { link: '' })]);
  const heads = rows(section).map(r => r.children[0]);
  assert.equal(heads[0].tag, 'a');
  assert.equal(heads[0].href, 'https://e.test/1');
  assert.equal(heads[0].rel, 'noopener noreferrer');
  assert.equal(heads[1].tag, 'span');
  assert.equal(heads[1].href, undefined);
  assert.equal(heads[2].tag, 'span');
});

test('the card hides itself when there is nothing to show', async () => {
  const { section } = await run([]);
  assert.equal(section.hidden, true);
});

test('subtitle names the feed, the kind, the length and the age', async () => {
  const ago = ms => new Date(Date.now() - ms).toISOString();
  const { section } = await run([
    item('a', { feed: 'The Latest', published: ago(5 * 60000) }),
    item('b', { feed: 'Full Show', kind: 'audio', minutes: 53, published: ago(3 * 3600000) }),
    item('c', { feed: 'Clips', kind: 'video', published: ago(2 * 86400000) })]);
  assert.deepEqual(subtitles(section), [
    'The Latest · 5m', 'Full Show · Audio · 53 min · 3h', 'Clips · Video · 2d']);
});

test('filter buttons appear only for kinds present and narrow the stream', async () => {
  const { section, window } = await run([
    item('a'), item('b', { kind: 'audio', link: 'https://e.test/2' }), item('c', { kind: 'audio', link: 'https://e.test/3' })]);
  const buttons = () => walk(section).filter(n => n.tag === 'button');
  assert.deepEqual(buttons().map(b => b.dataset.newsKind), ['all', 'article', 'audio']);
  assert.ok(buttons().every(b => has(b, 'dashboard-activity-filter')));
  assert.equal(rows(section).length, 3);
  window.setDashboardNewsKind('audio');
  assert.equal(rows(section).length, 2);
  assert.equal(buttons().find(b => b.dataset.newsKind === 'audio').attributes['aria-pressed'], 'true');
  assert.ok(has(buttons().find(b => b.dataset.newsKind === 'audio'), 'active'));
  window.setDashboardNewsKind('nonsense');
  assert.equal(rows(section).length, 3);
});

test('no filter buttons when every item is the same kind, and rows are capped', async () => {
  const many = Array.from({ length: 30 }, (_, i) => item(`n${i}`, { link: `https://e.test/${i}` }));
  const { section } = await run(many);
  assert.equal(walk(section).filter(n => n.tag === 'button').length, 0);
  assert.equal(rows(section).length, 12);
});
