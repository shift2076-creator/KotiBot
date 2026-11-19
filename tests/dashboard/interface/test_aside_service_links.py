import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class AsideServiceLinksTests(unittest.TestCase):
    def setUp(self):
        self.render = (ROOT / "static/js/dashboard-render.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/css/kotibot-icons.css").read_text(encoding="utf-8")

    def _list(self, name):
        start = self.render.index(f"const {name} = [")
        return self.render[start:self.render.index("];", start)]

    def test_services_and_their_targets(self):
        top = self._list("DASHBOARD_ASIDE_SERVICES_TOP")
        ent = self._list("DASHBOARD_ASIDE_SERVICES_ENTERTAINMENT")
        self.assertEqual(re.findall(r'label: "([^"]+)"', top), ["Documents", "Photos"])
        wiki = self._list("DASHBOARD_ASIDE_SERVICES_WIKI")
        self.assertEqual(re.findall(r'label: "([^"]+)"', ent), ["Arcade", "Library", "Jukebox", "Theater"])
        self.assertEqual(re.findall(r'label: "([^"]+)"', wiki), ["Wiki"])
        self.assertIn("port: 8084", wiki)
        self.assertIn("port: 8085", top)
        self.assertIn("port: 8446", top)
        for target in ("port: 8083", "port: 8000", 'path: "/music/"', "port: 8096"):
            self.assertIn(target, ent)

    def test_nav_order_and_spacing(self):
        nav = self.render[self.render.index('<nav class="aside-nav">'):]
        nav = nav[:nav.index("</nav>")]
        order = [
            nav.index('id="asideRenderSensorsToggle"'),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_TOP)"),
            nav.index('class="aside-double-space"'),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_ENTERTAINMENT)"),
            nav.index('class="aside-double-space"', nav.index("DASHBOARD_ASIDE_SERVICES_ENTERTAINMENT")),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_WIKI)"),
            nav.rindex('class="aside-double-space"'),
            nav.index('id="asideSettingsToggle"'),
        ]
        self.assertEqual(order, sorted(order))
        self.assertEqual(nav.count('class="aside-double-space"'), 3)

    def test_links_are_https_on_this_host_and_open_safely(self):
        self.assertIn("`https://${dashboardServiceHost()}${port}${service.path || \"/\"}`", self.render)
        helper = self.render[self.render.index("function dashboardAsideServiceLinksHtml"):]
        helper = helper[:helper.index("window.renderDashboardAside")]
        self.assertIn('target="_blank"', helper)
        self.assertIn('rel="noopener noreferrer"', helper)

    def test_lan_names_use_the_pivault_ip(self):
        # kotibot.lan reaches KotiBot only; the app ports exist on the IP address.
        self.assertIn('const DASHBOARD_PIVAULT_HOST = "192.168.4.90";', self.render)
        self.assertIn('location.hostname.endsWith(".lan") ? DASHBOARD_PIVAULT_HOST : location.hostname', self.render)

    def test_new_icons_exist_and_are_registered(self):
        for name in ("file-lines", "image", "book", "calendar-days", "globe"):
            self.assertTrue((ROOT / f"static/img/dashboard-icons/fas__{name}.svg").is_file(), name)
            self.assertIn(f'.koti-fa-{name} {{ --koti-icon-url: url("../img/dashboard-icons/fas__{name}.svg"); }}', self.css)


if __name__ == "__main__":
    unittest.main()
