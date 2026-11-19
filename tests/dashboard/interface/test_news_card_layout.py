import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def rule(css, selector):
    start = css.index(selector + " {")

    return css[start:css.index("}", start)]


class NewsCardLayoutTests(unittest.TestCase):
    def setUp(self):
        self.css = read("static/css/style.css")
        self.js = read("static/js/dashboard-news-shelf.js")
        self.icons = read("static/css/kotibot-icons.css")

    def test_entries_are_separate_rows_one_outer_space_apart(self):
        listing = rule(self.css, ".dashboard-home-news-list")
        self.assertIn("flex-direction: column;", listing)
        self.assertIn("gap: var(--outer-space);", listing)
        row = rule(self.css, ".dashboard-home-news-row")
        self.assertIn("flex: 0 0 var(--news-row-size);", row)
        self.assertIn("border: 1px solid var(--border);", row)

    def test_the_list_window_is_five_rows_and_four_gaps_tall_and_scrolls(self):
        listing = rule(self.css, ".dashboard-home-news-list")
        self.assertIn("block-size: calc((var(--news-row-size) * 5) + (var(--outer-space) * 4));", listing)
        self.assertIn("overflow-y: auto;", listing)

    def test_a_row_holds_exactly_two_title_lines_and_one_subtitle_line(self):
        self.assertIn("--news-row-size: calc(4.1em + 1rem);", self.css)
        title = rule(self.css, ".dashboard-home-news-row .dashboard-home-news-title")
        self.assertIn("-webkit-line-clamp: 2;", title)
        self.assertIn("line-height: 1.3;", title)
        # 2 title lines + 1 subtitle line at 1.3 each, plus a small gap, is under the 4.1em row content.
        self.assertLessEqual(3 * 1.3, 4.1 - 0.1)

    def test_home_sections_have_no_outer_border(self):
        start = self.css.index(".dashboard-home :is(.dashboard-home-matter-found-section")
        block = self.css[start:self.css.index("}", start)]
        self.assertIn("border: 0;", block)
        self.assertNotIn("1px solid", block)
        for name in ("environment", "light", "arm", "media", "matter-found"):
            self.assertIn(f".dashboard-home-{name}-section", block)

    def test_the_news_card_has_no_watermark(self):
        self.assertNotIn("dashboard-home-watermark", self.js)
        self.assertNotIn("dashboard-home-news-section > .dashboard-home-watermark", self.css)

    def test_card_order_is_list_then_message_then_search_bar_at_the_bottom(self):
        built = self.js[self.js.index("section.replaceChildren("):]
        self.assertTrue(built.startswith("section.replaceChildren(list, toast, bar);"))
        self.assertIn('"dashboard-home-news-search-input"', self.js)
        self.assertIn('input.placeholder = "Search feed";', self.js)

    def test_row_actions_are_always_reachable_on_touch_screens(self):
        self.assertIn("@media (hover: none) {\n  .dashboard-home-news-actions {\n    opacity: 1;", self.css)
        self.assertIn(".dashboard-home-news-row:focus-within .dashboard-home-news-actions", self.css)

    def test_every_icon_the_card_uses_is_registered_and_attributed(self):
        used = set(re.findall(r'icon\("([a-z-]+)"\)', self.js)) | set(re.findall(r'actionButton\("([a-z-]+)"', self.js))
        self.assertTrue({"folder", "folder-plus", "folder-minus", "eye", "eye-slash", "xmark", "magnifying-glass"} <= used)
        for name in used | {"rss", "file-lines", "circle-play", "music", "globe"}:
            self.assertIn(f".koti-fa-{name} {{", self.icons, name)
            svg = ROOT / f"static/img/dashboard-icons/fas__{name}.svg"
            self.assertTrue(svg.is_file(), name)
            self.assertIn("Font Awesome Free Solid", svg.read_text(encoding="utf-8").splitlines()[0])

    def test_the_card_loads_in_batches_and_never_writes_markup(self):
        self.assertIn("const BATCH = 10;", self.js)
        self.assertIn("if (nearEnd()) loadMore();", self.js)
        self.assertNotIn("ROW_LIMIT", self.js)
        self.assertNotIn("innerHTML", self.js)


if __name__ == "__main__":
    unittest.main()
