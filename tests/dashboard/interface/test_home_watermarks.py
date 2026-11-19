import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class HomeWatermarkIconTests(unittest.TestCase):
    def test_rss_icon_exists_and_is_registered(self):
        css = (ROOT / "static/css/kotibot-icons.css").read_text(encoding="utf-8")
        svg = ROOT / "static/img/dashboard-icons/fas__rss.svg"
        self.assertTrue(svg.is_file())
        self.assertIn("Font Awesome Free Solid", svg.read_text(encoding="utf-8"))
        self.assertIn('.koti-fa-rss { --koti-icon-url: url("../img/dashboard-icons/fas__rss.svg"); }', css)


class HomeBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.style = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        self.dark = (ROOT / "static/css/theme-dark.css").read_text(encoding="utf-8")
        self.light = (ROOT / "static/css/theme-light.css").read_text(encoding="utf-8")

    def test_dark_theme_sets_black_page_and_card_tokens(self):
        self.assertIn("--dashboard-home-bg: #000;", self.dark)
        self.assertIn("--dashboard-home-card-bg: #0c0c0d;", self.dark)

    def test_light_theme_is_untouched(self):
        self.assertNotIn("--dashboard-home-bg", self.light)
        self.assertNotIn("--dashboard-home-card-bg", self.light)

    def test_home_uses_the_tokens_with_fallbacks(self):
        self.assertIn("body:has(.dashboard-home) {\n  background: var(--dashboard-home-bg, var(--background));", self.style)
        self.assertIn("background: var(--dashboard-home-card-bg, var(--dashboard-aside-bg));", self.style)


class HomeWatermarkTests(unittest.TestCase):
    def setUp(self):
        self.render = (ROOT / "static/js/dashboard-render.js").read_text(encoding="utf-8")
        self.media = (ROOT / "static/js/dashboard-media-shelf.js").read_text(encoding="utf-8")
        self.news = (ROOT / "static/js/dashboard-news-shelf.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")
        self.icons = (ROOT / "static/css/kotibot-icons.css").read_text(encoding="utf-8")

    def test_home_section_titles_are_gone(self):
        for source in (self.render, self.media, self.news):
            self.assertNotIn("dashboard-home-section-title", source)

    def test_each_home_section_has_its_watermark(self):
        marker = "dashboard-home-watermark"
        for icon in ("sun", "lightbulb", "shield-halved"):
            self.assertIn(f'<span class="koti-icon koti-fa-{icon} {marker}" aria-hidden="true"></span>', self.render)
        self.assertIn(f'el("span", "koti-icon koti-fa-rss {marker}")', self.news)
        self.assertIn('watermark.setAttribute("aria-hidden", "true")', self.news)
        # Every icon used is a registered mask.
        for icon in ("sun", "lightbulb", "shield-halved", "rss"):
            self.assertIn(f".koti-fa-{icon} {{", self.icons)

    def test_now_playing_tile_has_no_watermark(self):
        self.assertNotIn("dashboard-home-watermark", self.media)
        self.assertNotIn("koti-fa-film", self.media)
        self.assertNotIn(".dashboard-home-media-section:not(.dashboard-home-news-section) > .dashboard-home-watermark", self.css)

    def test_sections_keep_an_accessible_name(self):
        for label in ("Scenes", "Security", "News", "Continue watching"):
            self.assertIn(f'aria-label="{label}"', self.render)
        self.assertIn('aria-label="Open environment and conditions"', self.render)

    def test_environment_groups_are_transparent_so_the_sun_shows(self):
        self.assertIn(
            ".dashboard-home-environment-section .dashboard-home-environment-group {\n  background: transparent;",
            self.css,
        )

    def test_watermarks_are_clipped_behind_content_and_staggered(self):
        self.assertIn("overflow: hidden;\n  isolation: isolate;", self.css)
        block = self.css[self.css.index(".dashboard-home .dashboard-home-watermark {"):]
        block = block[:block.index("}")]
        for token in ("position: absolute;", "z-index: -1;", "pointer-events: none;"):
            self.assertIn(token, block)
        corners = []
        for section in ("environment", "news"):
            rule = self.css[self.css.index(f".dashboard-home-{section}-section > .dashboard-home-watermark"):]
            corners.append(rule[:rule.index("}")])
        self.assertIn("inset-inline-end", corners[0])
        self.assertIn("inset-inline-start", corners[1])

    def test_scenes_and_security_are_side_by_side_with_identical_watermarks(self):
        self.assertIn('<div class="dashboard-home-pair">', self.render)
        pair = self.render[self.render.index('<div class="dashboard-home-pair">'):]
        pair = pair[:pair.index('data-home-media-shelf')]
        self.assertLess(pair.index('aria-label="Scenes"'), pair.index('aria-label="Security"'))
        self.assertIn("koti-fa-lightbulb", pair)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", self.css)
        rule = self.css[self.css.index(".dashboard-home-pair > .dashboard-home-card > .dashboard-home-watermark"):]
        rule = rule[:rule.index("}")]
        for token in ("--icon-size: 8rem;", "inset-block-end: -.75rem;", "inset-inline-end: -.75rem;"):
            self.assertIn(token, rule)
        # The two sections add no size or offset of their own, only a colour.
        for section in ("light", "arm"):
            own = self.css[self.css.index(f".dashboard-home-{section}-section > .dashboard-home-watermark"):]
            own = own[:own.index("}")]
            self.assertNotIn("inset", own)
            self.assertNotIn("--icon-size", own)

    def test_scenes_is_a_two_by_two_grid_and_security_an_upside_down_triangle(self):
        base = self.css[self.css.index(".dashboard-home-arm-row,\n.dashboard-home-light-row {"):]
        base = base[:base.index("}")]
        for token in ("display: grid;", "grid-template-columns: repeat(2, minmax(0, var(--dashboard-home-mode-button-width)));", "justify-content: center;"):
            self.assertIn(token, base)
        triangle = self.css[self.css.index(".dashboard-home-arm-row > :last-child:nth-child(odd) {"):]
        triangle = triangle[:triangle.index("}")]
        self.assertIn("grid-column: 1 / -1;", triangle)
        self.assertIn("justify-self: center;", triangle)
        # Four Scenes buttons fill the grid; three Security buttons leave the last one centred below.
        self.assertEqual(self.render.count('data-dashboard-action="set-home-light-mode"'), 4)
        self.assertEqual(self.render.count('data-dashboard-action="set-home-arm-mode"'), 3)

    def test_one_spacing_value_between_sections_and_at_the_screen_edge(self):
        home = self.css[self.css.index("\n.dashboard-home {"):]
        home = home[:home.index("}")]
        self.assertIn("gap: var(--outer-space);", home)
        self.assertIn("padding: 0 var(--outer-space) var(--outer-space);", home)
        self.assertIn("padding: 0 var(--outer-space) var(--outer-space);", self.css[self.css.index("  .dashboard-home {\n    min-block-size"):])
        self.assertNotIn("padding: 0 calc(var(--outer-space) * .5) var(--outer-space);", self.css)
        self.assertIn("column-gap: var(--outer-space);\n    max-inline-size: none;", self.css)
        cards = self.css[self.css.index(".dashboard-home :is(.dashboard-home-matter-found-section"):]
        self.assertIn("margin-inline: 0;", cards[:cards.index("}")])
        self.assertNotIn(".dashboard-home,\nbody[data-dashboard-page=\"activity\"]", self.css)
        pair = self.css[self.css.index(".dashboard-home-pair {"):]
        self.assertIn("gap: var(--outer-space);", pair[:pair.index("}")])


if __name__ == "__main__":
    unittest.main()
