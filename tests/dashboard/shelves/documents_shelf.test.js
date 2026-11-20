// Run with: node --test tests/dashboard/shelves/documents_shelf.test.js
// Executes the real Documents card code against a minimal DOM with hostile text.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'static/js/dashboard-documents-shelf.js'), 'utf8');

class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.className = '';
    this.textContent = '';
    this.hidden = false;
    this.value = '';
    this.listeners = {};
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...kids) { this.children = kids; }
  removeChild(child) { this.children = this.children.filter(c => c !== child); }
  insertBefore(node, ref) {
    this.children = this.children.filter(c => c !== node);
    this.children.splice(ref ? this.children.indexOf(ref) : this.children.length, 0, node);
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  focus() { this.focused = true; }
}

const walk = n => [n, ...n.children.flatMap(walk)];
const has = (n, name) => n.className.split(' ').includes(name);
const flush = (ms = 20) => new Promise(resolve => setTimeout(resolve, ms));

let counter = 0;
const now = new Date().toISOString();
const doc = (title, over = {}) => ({ id: ++counter, title, correspondent: 'Utility Co', type: 'Bill', added: now, modified: now, favorite: false, ...over });
const page = (items, over = {}) => ({ ok: true, available: true, items, has_more: false, inbox_count: 0, ...over });
const rows = section => walk(section).filter(n => has(n, 'dashboard-home-news-row'));
const titles = section => rows(section).map(r => r.children[1].children[0].textContent);
const tabButton = (section, label) => walk(section).find(n => n.tag === 'button' && n.textContent === label);
const bar = section => walk(section).find(n => has(n, 'dashboard-home-news-bar'));

// answer: (url) => page object; the default serves `items` for the added tab.
async function run(items, { bootstrap, answer, early } = {}) {
  const faded = [];
  const calls = [];
  const window = { dashboardFadeIn: node => faded.push(node), location: { hostname: 'kotibot.lan' } };

  if (bootstrap !== undefined) window.KOTIBOT_DOCS_BOOTSTRAP = bootstrap;

  const section = new Node('section');
  const home = { querySelector: () => section };
  const ctx = {
    window,
    document: { createElement: tag => new Node(tag), querySelector: () => section },
    fetch: async url => {
      calls.push(url);
      const body = answer ? answer(url) : page(items);

      return { ok: body !== null, json: async () => body };
    },
    Date, JSON, Number, Math, Promise, String, Array, Set, Map, Boolean, RegExp, encodeURIComponent, clearTimeout, setTimeout,
  };

  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  window.syncDashboardHomeDocumentsShelf(home);
  if (early) early(section);
  await flush();

  return { section, window, calls, faded, home };
}

test('the first page that came with the HTML is drawn at once, with no request and no fade', async () => {
  const list = [doc('Electric bill'), doc('Lease', { favorite: true })];
  let early;
  const { section, calls, faded } = await run(list, { bootstrap: { ready: true, ...page(list, { inbox_count: 3 }) }, early: s => { early = titles(s); } });

  assert.deepEqual(early, ['Electric bill', 'Lease'], 'rows exist on the first frame');
  assert.deepEqual(calls, []);
  assert.deepEqual(faded.filter(n => rows(section).includes(n)), []);
  assert.equal(walk(section).find(n => has(n, 'dashboard-home-news-toggle')).hidden, false);
});

test('someone with no Paperless access never gets a card or a request', async () => {
  let early;
  const { calls } = await run([], { bootstrap: { ready: true, available: false }, early: s => { early = s.hidden; } });

  assert.equal(early, true);
  assert.deepEqual(calls, []);
});

test('without the first page the card is blocked out at full size, then the rows fade in', async () => {
  const list = [doc('A'), doc('B')];
  let early;
  const { section, faded } = await run(list, { early: s => { early = { hidden: s.hidden, rows: rows(s).length, pending: has(bar(s), 'is-pending') }; } });

  assert.deepEqual(early, { hidden: false, rows: 0, pending: true });
  assert.deepEqual(titles(section), ['A', 'B']);
  assert.ok(!has(bar(section), 'is-pending'));
  assert.ok(rows(section).every(r => faded.includes(r)));
  assert.ok(faded.includes(bar(section)));
});

test('a card that turns out to have no access hides itself', async () => {
  const { section } = await run([], { answer: () => ({ ok: true, available: false }) });

  assert.equal(section.hidden, true);
});

test('a row links to the document in Paperless by its number and shows the details line', async () => {
  const d = doc('<img src=x onerror=alert(1)>', { favorite: true });
  const { section } = await run([d], { bootstrap: { ready: true, ...page([d]) } });
  const row = rows(section)[0];
  const headline = row.children[1].children[0];
  const line = row.children[1].children[1];

  assert.equal(headline.textContent, '<img src=x onerror=alert(1)>');
  assert.equal(headline.href, `https://kotibot.lan:8085/documents/${d.id}/details`);
  assert.equal(headline.rel, 'noopener noreferrer');
  assert.match(line.children[0].textContent, /^Utility Co · Bill · /);
  assert.ok(walk(line).some(n => has(n, 'koti-fa-star')), 'a favorite shows its star');
});

test('the tabs ask for their own list and the Edited tab says edited', async () => {
  const seen = [];
  const { section, calls } = await run([], {
    bootstrap: { ready: true, ...page([doc('Added one')]) },
    answer: url => {
      seen.push(url);

      return page([doc(url.includes('tab=edited') ? 'Edited one' : 'Favorite one')]);
    },
  });

  tabButton(section, 'Edited').listeners.click();
  await flush();

  assert.ok(calls.some(u => u.includes('tab=edited')));
  assert.deepEqual(titles(section), ['Edited one']);
  assert.match(walk(rows(section)[0]).find(n => has(n, 'dashboard-home-subtitle')).textContent, /edited just now$/);
  assert.equal(tabButton(section, 'Edited').attributes['aria-pressed'], 'true');
  assert.equal(tabButton(section, 'Added').attributes['aria-pressed'], 'false');

  tabButton(section, 'Favs').listeners.click();
  await flush();
  assert.deepEqual(titles(section), ['Favorite one']);
});

test('searching asks the server after a short pause', async () => {
  const { section, calls } = await run([doc('A')], { bootstrap: { ready: true, ...page([doc('A')]) } });
  const input = walk(section).find(n => n.tag === 'input');

  input.value = 'lease';
  input.listeners.input();
  await flush(350);

  assert.ok(calls.some(u => u.includes('q=lease') && u.includes('tab=added')));
});

test('an empty list says so, and a failed refresh keeps what is showing', async () => {
  const list = [doc('Keep me')];
  const { section, window, home } = await run(list, { bootstrap: { ready: true, ...page(list) }, answer: () => null });

  window.syncDashboardHomeDocumentsShelf(home);
  await flush();
  assert.deepEqual(titles(section), ['Keep me']);

  const empty = await run([], { answer: () => page([]) });

  assert.equal(walk(empty.section).find(n => has(n, 'dashboard-home-news-empty')).textContent, 'No documents yet');
});

test('the inbox count shows only when something is waiting', async () => {
  const none = await run([], { bootstrap: { ready: true, ...page([doc('A')], { inbox_count: 0 }) } });
  const some = await run([], { bootstrap: { ready: true, ...page([doc('A')], { inbox_count: 7 }) } });
  const link = s => walk(s).find(n => has(n, 'dashboard-home-news-toggle'));

  assert.equal(link(none.section).hidden, true);
  assert.equal(link(some.section).hidden, false);
  assert.equal(link(some.section).children[1].textContent, '7');
});

test('the card never builds its page with innerHTML', () => {
  assert.ok(!source.includes('innerHTML'));
});
