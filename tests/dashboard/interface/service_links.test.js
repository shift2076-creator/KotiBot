// Run with: node --test tests/dashboard/interface/service_links.test.js
// Executes the real resolver: service links follow the domain the page was opened on.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.resolve(__dirname, '../../..', 'static/js/dashboard-service-links.js'), 'utf8');

function on(hostname) {
  const window = { location: { hostname } };
  vm.runInContext(source, vm.createContext({ window }));

  return window;
}

const EXPECTED = {
  documents: ['paperless', '/'],
  photos: ['photos', '/'],
  arcade: ['arcade', '/'],
  library: ['library', '/'],
  jukebox: ['music', '/music/'],
  theater: ['jellyfin', '/'],
  wiki: ['wiki', '/'],
  passwords: ['vault', '/'],
  portainer: ['portainer', '/'],
  calendar: ['calendar', '/'],
};

for (const domain of ['kotibot.lan', 'kotibot.app']) {
  test(`every service follows ${domain}`, () => {
    for (const host of [domain, `calendar.${domain}`]) {
      const w = on(host);

      for (const [key, [name, tail]] of Object.entries(EXPECTED)) {
        assert.equal(w.dashboardServiceUrl(key), `https://${name}.${domain}${tail}`, `${key} from ${host}`);
      }

      assert.equal(w.dashboardServiceOnKotibotDomain(), true);
    }
  });
}

test('a path is appended to the service address, never a port', () => {
  assert.equal(on('kotibot.app').dashboardServiceUrl('theater', '/web/#/details?id=ab'), 'https://jellyfin.kotibot.app/web/#/details?id=ab');
  assert.equal(on('kotibot.lan').dashboardServiceUrl('documents', '/documents/7/details'), 'https://paperless.kotibot.lan/documents/7/details');
});

test('an IP address keeps the host and port form', () => {
  const w = on('192.168.4.90');

  assert.equal(w.dashboardServiceUrl('documents'), 'https://192.168.4.90:8085/');
  assert.equal(w.dashboardServiceUrl('jukebox'), 'https://192.168.4.90/music/');
  assert.equal(w.dashboardServiceUrl('passwords'), 'https://192.168.4.90:8448/');
  assert.equal(w.dashboardServiceOnKotibotDomain(), false);
});

test('look-alike hosts are not treated as kotibot domains', () => {
  for (const host of ['evilkotibot.lan', 'kotibot.lan.example.com', 'kotibot.app.evil.test', 'other.lan']) {
    const w = on(host);

    assert.equal(w.dashboardServiceOnKotibotDomain(), false, host);
    assert.equal(w.dashboardServiceUrl('wiki'), `https://${host}:8084/`, host);
  }
});

test('Add User has no subdomain: the Pi address on .lan, this host on .app', () => {
  assert.equal(on('kotibot.lan').dashboardServiceUrl('addUser'), 'https://192.168.4.90/users/add');
  assert.equal(on('kotibot.app').dashboardServiceUrl('addUser'), 'https://kotibot.app/users/add');
});

test('an unknown service gives no link', () => {
  assert.equal(on('kotibot.lan').dashboardServiceUrl('nope'), '');
});
