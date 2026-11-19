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
    this.value = '';
    this.listeners = {};
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...kids) { this.children = kids; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  replaceWith(other) { this.replacedBy = other; }
  focus() { this.focused = true; }
}

const walk = n => [n, ...n.children.flatMap(walk)];
const has = (n, name) => n.className.split(' ').includes(name);
const flush = (ms = 20) => new Promise(resolve => setTimeout(resolve, ms));

// routes: (url, options) => { ok?, body } ; the default serves the feed.
async function run(items, { routes, extra = {} } = {}) {
  const window = {};
  const section = new Node('section');
  const home = { querySelector: () => section };
  section.closest = () => home;
  const calls = [];
  // Answers /api/rss/items the way the server does: filter by q, then slice a page.
  const feedPage = url => {
    const arg = name => (url.match(new RegExp(`[?&]${name}=([^&]*)`)) || [])[1];
    const needle = decodeURIComponent(arg('q') || '').toLowerCase();
    const found = items.filter(i => !needle || `${i.title} ${i.feed}`.toLowerCase().includes(needle));
    const offset = Number(arg('offset') || 0);
    const limit = Number(arg('limit') || 10);
    return { ok: true, items: found.slice(offset, offset + limit), has_more: offset + limit < found.length,
      hidden_count: 0, saved_count: 0, folders: ['Read later'], ...extra };
  };
  const ctx = {
    window,
    document: { createElement: tag => new Node(tag), querySelector: () => null },
    fetch: async (url, options = {}) => {
      calls.push({ url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined });
      const answer = (routes && routes(url, options))
        || (url.startsWith('/api/rss/items?limit') ? { body: feedPage(url) } : { body: { ok: true } });
      return { ok: answer.ok !== false, json: async () => answer.body };
    },
    Date, URL, JSON, Number, Math, Promise, String, Array, Set, Boolean, RegExp, encodeURIComponent, setTimeout, clearTimeout,
  };
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  window.syncDashboardHomeNewsShelf(home);
  await flush();
  ctx.document.querySelector = () => section;
  window.syncDashboardHomeNewsShelf(home);
  return { section, window, calls };
}

let counter = 0;
const now = new Date().toISOString();
const item = (title, over = {}) => ({ id: `${(++counter).toString(16).padStart(16, '0')}`, title, link: 'https://e.test/1', feed: 'Feed', feed_id: 'a', kind: 'article', minutes: 0, published: now, folder: '', ...over });
const rows = section => walk(section).filter(n => has(n, 'dashboard-home-news-row'));
const titles = section => rows(section).map(r => r.children[1].children[0].textContent);
const subtitles = section => walk(section).filter(n => has(n, 'dashboard-home-subtitle')).map(n => n.textContent);
const button = (root, label) => walk(root).find(n => n.tag === 'button' && n.attributes['aria-label'] === label);
const chip = (root, text) => walk(root).find(n => n.tag === 'button' && has(n, 'dashboard-home-news-chip') && n.textContent === text);
const searchBox = section => walk(section).find(n => n.tag === 'input' && has(n, 'dashboard-home-news-search-input'));
const toast = section => walk(section).find(n => has(n, 'dashboard-home-news-toast'));

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
  const heads = rows(section).map(r => r.children[1].children[0]);
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

test('each row ends with an icon for its kind and the subtitle names feed, length and age', async () => {
  const ago = ms => new Date(Date.now() - ms).toISOString();
  const { section } = await run([
    item('a', { feed: 'The Latest', published: ago(5 * 60000) }),
    item('b', { feed: 'Full Show', kind: 'video', minutes: 53, published: ago(3 * 3600000) }),
    item('c', { feed: 'Pod', kind: 'audio', minutes: 20, published: ago(2 * 86400000) })]);
  const lines = rows(section).map(r => r.children[1].children[1]);
  assert.deepEqual(lines.map(l => l.children[0].textContent.trim()), [
    'The Latest · 5m', 'Full Show · 53 min · 3h', 'Pod · 20 min · 2d']);
  assert.deepEqual(lines.map(l => l.children[1].className), [
    'koti-icon dashboard-home-news-kind koti-fa-file-lines', 'koti-icon dashboard-home-news-kind koti-fa-circle-play', 'koti-icon dashboard-home-news-kind koti-fa-music']);
  assert.deepEqual(lines.map(l => l.children[1].attributes['aria-label']), ['Article', 'Video', 'Audio']);
});

test('there are no kind filters, only row actions and the bar buttons', async () => {
  const many = Array.from({ length: 9 }, (_, i) => item(`n${i}`, { link: `https://e.test/${i}`, kind: i % 2 ? 'video' : 'article' }));
  const { section } = await run(many);
  const buttons = walk(section).filter(n => n.tag === 'button');
  assert.ok(buttons.every(n => has(n, 'dashboard-home-news-act') || has(n, 'dashboard-home-news-toggle') || has(n, 'dashboard-home-news-chip')));
  assert.equal(rows(section).length, 9);
});

const manyItems = count => Array.from({ length: count }, (_, i) => item(`story ${i}`, { link: `https://e.test/s${i}`, feed: i % 2 ? 'Odd' : 'Even' }));
const scrollTo = (section, { top, height = 1000, view = 100 }) => {
  const list = section.children[0];
  Object.assign(list, { scrollTop: top, scrollHeight: height, clientHeight: view });
  list.listeners.scroll();
};
const feedCalls = calls => calls.filter(c => c.url.startsWith('/api/rss/items?limit'));

test('the first batch is small and the next ones load as the list is scrolled to its end', async () => {
  const { section, calls } = await run(manyItems(25));
  assert.equal(feedCalls(calls)[0].url, '/api/rss/items?limit=10&offset=0');
  assert.equal(rows(section).length, 10);
  scrollTo(section, { top: 100 });
  await flush();
  assert.equal(feedCalls(calls).length, 1, 'far from the end: nothing is requested');
  scrollTo(section, { top: 850 });
  await flush();
  assert.equal(feedCalls(calls)[1].url, '/api/rss/items?limit=10&offset=10');
  assert.equal(rows(section).length, 20);
  scrollTo(section, { top: 850 });
  await flush();
  assert.equal(feedCalls(calls)[2].url, '/api/rss/items?limit=10&offset=20');
  assert.deepEqual(titles(section).slice(-2), ['story 23', 'story 24']);
  assert.equal(rows(section).length, 25);
  scrollTo(section, { top: 850 });
  await flush();
  assert.equal(feedCalls(calls).length, 3, 'the end of the stream: nothing more is requested');
});

test('scrolling again while a batch is loading does not ask twice', async () => {
  const { section, calls } = await run(manyItems(25));
  scrollTo(section, { top: 850 });
  scrollTo(section, { top: 860 });
  scrollTo(section, { top: 870 });
  await flush();
  assert.equal(feedCalls(calls).filter(c => c.url.includes('offset=10')).length, 1);
});

test('a batch that repeats rows already shown does not duplicate them', async () => {
  const list = manyItems(12);
  const { section } = await run(list, { routes: url => (url.includes('offset=10')
    ? { body: { ok: true, items: [list[9], list[10], list[11]], has_more: false } } : null) });
  scrollTo(section, { top: 850 });
  await flush();
  assert.equal(rows(section).length, 12);
});

test('hiding a row keeps the next batch starting at the right place', async () => {
  const { section, calls } = await run(manyItems(25));
  button(rows(section)[0], 'Hide from feed').listeners.click();
  await flush();
  scrollTo(section, { top: 850 });
  await flush();
  assert.equal(feedCalls(calls).at(-1).url, '/api/rss/items?limit=10&offset=9');
});

test('searching asks the server, which searches the whole stream, and starts again from the top', async () => {
  const { section, calls } = await run(manyItems(40));
  const box = searchBox(section);
  box.value = 'story 3';
  box.listeners.input();
  box.value = 'story 39';
  box.listeners.input();
  await flush(320);
  const searches = feedCalls(calls).filter(c => c.url.includes('q='));
  assert.equal(searches.length, 1, 'typing is debounced into one request');
  assert.equal(searches[0].url, '/api/rss/items?limit=10&offset=0&q=story%2039');
  assert.deepEqual(titles(section), ['story 39']);
  box.value = 'zzz';
  box.listeners.input();
  await flush(320);
  assert.equal(section.hidden, false);
  assert.equal(walk(section).find(n => has(n, 'dashboard-home-news-empty')).textContent, 'No matches');
  box.value = '';
  box.listeners.input();
  await flush(320);
  assert.equal(rows(section).length, 10);
});

test('a refresh reloads as many rows as are showing, not just the first batch', async () => {
  const { section, window, calls } = await run(manyItems(25));
  scrollTo(section, { top: 850 });
  await flush();
  window.refreshDashboardHomeNewsShelf();
  await flush();
  assert.equal(feedCalls(calls).at(-1).url, '/api/rss/items?limit=20&offset=0');
  assert.equal(rows(section).length, 20);
});

test('the list, the search box and the two buttons are all in the card, with no watermark', async () => {
  const { section } = await run([item('a')]);
  assert.ok(has(section.children[0], 'dashboard-home-news-list'));
  assert.ok(!walk(section).some(n => has(n, 'dashboard-home-watermark')));
  assert.equal(searchBox(section).attributes['aria-label'], 'Search feed');
  assert.ok(button(section, 'Saved articles'));
  assert.ok(button(section, 'Hidden articles'));
});

test('each row starts with the site favicon from KotiBot only, with a globe fallback', async () => {
  const { section } = await run([
    item('a', { icon: '/api/rss/icon/www.pbs.org' }),
    item('b', { icon: 'https://evil.test/x.png' }),
    item('c', { icon: 'javascript:alert(1)' }),
    item('d', { icon: '' }),
    item('e')]);
  const first = rows(section).map(r => r.children[0]);
  assert.equal(first[0].tag, 'img');
  assert.equal(first[0].src, '/api/rss/icon/www.pbs.org');
  assert.equal(first[0].alt, '');
  for (const node of first.slice(1)) {
    assert.equal(node.tag, 'span');
    assert.ok(has(node, 'is-fallback'));
  }
  first[0].listeners.error();
  assert.ok(has(first[0].replacedBy, 'is-fallback'));
});

test('hiding removes the row at once, tells the server, and Undo puts it back in place', async () => {
  const list = [item('a'), item('b'), item('c')];
  const ids = list.map(i => i.id);
  const { section, calls } = await run(list);
  button(rows(section)[1], 'Hide from feed').listeners.click();
  assert.deepEqual(titles(section), ['a', 'c']);
  assert.equal(toast(section).hidden, false);
  await flush();
  assert.ok(calls.some(c => c.method === 'POST' && c.url === `/api/rss/items/${ids[1]}/hide`));
  const undo = chip(toast(section), 'Undo');
  undo.listeners.click();
  await flush();
  assert.ok(calls.some(c => c.url === `/api/rss/items/${ids[1]}/unhide`));
  assert.deepEqual(titles(section), ['a', 'b', 'c']);
  assert.equal(toast(section).hidden, true);
});

test('a hide the server refuses puts the row back and says so', async () => {
  const list = [item('a'), item('b')];
  const { section } = await run(list, { routes: url => (url.endsWith('/hide') ? { ok: false, body: { ok: false, error: 'Nope.' } } : null) });
  button(rows(section)[0], 'Hide from feed').listeners.click();
  await flush();
  assert.deepEqual(titles(section), ['a', 'b']);
  assert.equal(toast(section).children[0].textContent, 'Nope.');
});

test('saving opens a folder picker, posts the chosen folder and tags the row', async () => {
  const list = [item('a'), item('b')];
  const { section, calls } = await run(list, { extra: { folders: ['Read later', 'Climate'] } });
  button(rows(section)[0], 'Save to folder').listeners.click();
  const picker = walk(section).find(n => has(n, 'dashboard-home-news-picker'));
  assert.deepEqual(picker.children.map(c => c.textContent), ['Read later', 'Climate', 'New folder']);
  assert.ok(button(rows(section)[0], 'Cancel'));
  chip(section, 'Climate').listeners.click();
  await flush();
  const post = calls.find(c => c.method === 'POST' && c.url === `/api/rss/saved/${list[0].id}`);
  assert.deepEqual(post.body, { folder: 'Climate' });
  assert.equal(walk(section).find(n => has(n, 'dashboard-home-news-picker')), undefined);
  const tag = walk(rows(section)[0]).find(n => has(n, 'dashboard-home-news-folder-tag'));
  assert.equal(tag.children[1].textContent, 'Climate');
  assert.equal(walk(section).find(n => has(n, 'dashboard-home-news-toggle') && n.attributes['aria-label'] === 'Saved articles').children[1].textContent, '1');
});

test('a new folder takes its name from a text box and Escape cancels the picker box', async () => {
  const list = [item('a')];
  const { section, calls } = await run(list);
  button(rows(section)[0], 'Save to folder').listeners.click();
  chip(section, 'New folder').listeners.click();
  const field = walk(section).find(n => n.tag === 'input' && has(n, 'dashboard-home-news-folder-input'));
  assert.equal(field.maxLength, 40);
  field.listeners.keydown({ key: 'Escape' });
  assert.ok(chip(section, 'New folder'));
  chip(section, 'New folder').listeners.click();
  const again = walk(section).find(n => n.tag === 'input' && has(n, 'dashboard-home-news-folder-input'));
  again.value = '  <b>Recipes</b>  ';
  again.listeners.keydown({ key: 'Enter' });
  await flush();
  assert.deepEqual(calls.find(c => c.url === `/api/rss/saved/${list[0].id}`).body, { folder: '<b>Recipes</b>' });
  assert.equal(walk(rows(section)[0]).find(n => has(n, 'dashboard-home-news-folder-tag')).children[1].textContent, '<b>Recipes</b>');
});

test('the Hidden button lists hidden items and each can be shown again', async () => {
  const hiddenOne = item('was hidden');
  const { section, calls } = await run([item('a')], {
    extra: { hidden_count: 1 },
    routes: url => (url === '/api/rss/items?view=hidden' ? { body: { ok: true, items: [hiddenOne] } } : null),
  });
  const toggle = button(section, 'Hidden articles');
  assert.equal(toggle.children[1].textContent, '1');
  toggle.listeners.click();
  await flush();
  assert.deepEqual(titles(section), ['was hidden']);
  assert.equal(toggle.attributes['aria-pressed'], 'true');
  button(rows(section)[0], 'Show in feed again').listeners.click();
  await flush();
  assert.ok(calls.some(c => c.method === 'POST' && c.url === `/api/rss/items/${hiddenOne.id}/unhide`));
  assert.deepEqual(rows(section), []);
  assert.equal(toggle.children[1].textContent, '0');
  toggle.listeners.click();
  assert.equal(toggle.attributes['aria-pressed'], 'false');
});

test('the Saved button lists saved articles with their folder and each can be removed', async () => {
  const kept = { id: 'ab'.repeat(8), title: 'Keep me', link: 'https://e.test/k', feed: 'Feed', kind: 'article', folder: 'Climate', saved_at: now };
  const { section, calls } = await run([item('a')], {
    extra: { saved_count: 1 },
    routes: url => (url === '/api/rss/saved' ? { body: { ok: true, items: [kept], folders: ['Read later', 'Climate'] } } : null),
  });
  button(section, 'Saved articles').listeners.click();
  await flush();
  assert.deepEqual(titles(section), ['Keep me']);
  assert.deepEqual(subtitles(section), ['Feed · Climate']);
  button(rows(section)[0], 'Remove from folder').listeners.click();
  await flush();
  assert.ok(calls.some(c => c.method === 'POST' && c.url === `/api/rss/saved/${kept.id}/remove`));
  assert.deepEqual(rows(section), []);
});

test('the card stays when every article is hidden, so they can be brought back', async () => {
  const { section } = await run([], { extra: { hidden_count: 3 } });
  assert.equal(section.hidden, false);
  assert.equal(walk(section).find(n => has(n, 'dashboard-home-news-empty')).textContent, 'Nothing left in the feed');
});
