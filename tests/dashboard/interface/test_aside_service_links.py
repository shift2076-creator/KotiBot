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
        self.assertIn('service: "wiki"', wiki)
        self.assertIn('service: "documents"', top)
        self.assertIn('service: "photos"', top)
        for target in ('service: "library"', 'service: "arcade"', 'service: "jukebox"', 'service: "theater"'):
            self.assertIn(target, ent)

    def test_nav_groups_and_order(self):
        nav = self.render[self.render.index('<nav class="aside-nav">'):]
        nav = nav[:nav.index("</nav>")]
        order = [
            nav.index("aside-brand"),
            nav.index("aside-group-home"),
            nav.index('id="asideHomeLogoToggle"'),
            nav.index('id="asideRenderSensorsToggle"'),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_TOP)"),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_ENTERTAINMENT)"),
            nav.index("dashboardAsideServiceLinksHtml(DASHBOARD_ASIDE_SERVICES_WIKI)"),
            nav.index('id="asideSettingsToggle"'),
        ]
        self.assertEqual(order, sorted(order))
        self.assertEqual(nav.count('class="aside-group '), 6)
        self.assertNotIn("aside-double-space", self.render)

    def test_footer_layout_uses_the_spacing_tokens_and_leaves_portrait_alone(self):
        css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        block = css[css.index("Navigation footer (landscape)"):]
        # Outside the landscape query the groups are transparent and the brand is hidden.
        base = block[:block.index("@media (min-aspect-ratio: 2/3)")]
        self.assertIn(".aside-group {\n  display: contents;", base)
        self.assertIn(".aside-brand {\n  display: none;", base)
        landscape = block[block.index("@media (min-aspect-ratio: 2/3)"):]
        self.assertIn("position: static;", landscape)
        # The aside comes first in the markup, so order puts it after the page.
        self.assertIn("order: 1;", landscape)
        self.assertIn("order: 2;", landscape)
        self.assertIn("flex-direction: column;", landscape)
        self.assertIn(".dashboard-home-hero {\n    display: none;", landscape)
        self.assertEqual(landscape.count("--aside-columns: 2;"), 1)
        for token in ("--outer-space", "--inner-space", "--control-size"):
            self.assertIn(token, landscape)
        # Only the 1px hairlines are fixed sizes; every other size comes from the tokens.
        self.assertNotRegex(landscape, r"(?<![\d.])(?!1px)\d+(?:\.\d+)?px")

    def test_links_come_from_the_shared_resolver_and_open_safely(self):
        self.assertIn("window.dashboardServiceUrl(service.service)", self.render)
        helper = self.render[self.render.index("function dashboardAsideServiceLinksHtml"):]
        helper = helper[:helper.index("window.renderDashboardAside")]
        self.assertIn('target="_blank"', helper)
        self.assertIn('rel="noopener noreferrer"', helper)

    def test_no_link_is_built_from_a_hardcoded_host_or_port(self):
        # Every service link follows the domain the page was opened on (static/js/dashboard-service-links.js).
        self.assertNotIn("192.168.", self.render)
        self.assertNotIn("dashboardServiceHost", self.render)
        self.assertNotRegex(self.render, r"service\.port|tool\.port")
        links = (ROOT / "static/js/dashboard-service-links.js").read_text(encoding="utf-8")
        self.assertIn("kotibot\\.(?:lan|app)", links)
        self.assertIn("dashboard-service-links.js", (ROOT / "templates/index.html").read_text(encoding="utf-8"))

    def test_new_icons_exist_and_are_registered(self):
        for name in ("file-lines", "image", "book", "calendar-days", "globe"):
            self.assertTrue((ROOT / f"static/img/dashboard-icons/fas__{name}.svg").is_file(), name)
            self.assertIn(f'.koti-fa-{name} {{ --koti-icon-url: url("../img/dashboard-icons/fas__{name}.svg"); }}', self.css)


if __name__ == "__main__":
    unittest.main()
