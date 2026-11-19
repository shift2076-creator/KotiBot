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
        for icon in ("sun", "palette", "shield-halved"):
            self.assertIn(f'<span class="koti-icon koti-fa-{icon} {marker}" aria-hidden="true"></span>', self.render)
        self.assertIn(f'el("span", "koti-icon koti-fa-rss {marker}")', self.news)
        self.assertIn('watermark.setAttribute("aria-hidden", "true")', self.news)
        # Every icon used is a registered mask.
        for icon in ("sun", "palette", "shield-halved", "rss"):
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
        for section in ("environment", "news", "light", "arm"):
            rule = self.css[self.css.index(f".dashboard-home-{section}-section > .dashboard-home-watermark"):]
            corners.append(rule[:rule.index("}")])
        self.assertIn("inset-inline-end", corners[0])
        self.assertIn("inset-inline-start", corners[1])
        self.assertIn("inset-block-end", corners[2])
        self.assertIn("inset-block-start", corners[3])


if __name__ == "__main__":
    unittest.main()
