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


if __name__ == "__main__":
    unittest.main()
