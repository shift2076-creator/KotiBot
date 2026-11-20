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


class HomeTitlesAndControlsTests(unittest.TestCase):
    def setUp(self):
        self.render = (ROOT / "static/js/dashboard-render.js").read_text(encoding="utf-8")
        self.media = (ROOT / "static/js/dashboard-media-shelf.js").read_text(encoding="utf-8")
        self.news = (ROOT / "static/js/dashboard-news-shelf.js").read_text(encoding="utf-8")
        self.envjs = (ROOT / "subsystems/environment/static/js/environment-render.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

    def test_only_scenes_and_security_carry_a_watermark(self):
        for source in (self.media, self.news, self.envjs):
            self.assertNotIn("dashboard-home-watermark", source)
        self.assertEqual(self.render.count('class="dashboard-home-watermark '), 2)
        self.assertIn('dashboardIconHtml("emoji_objects")', self.render)
        self.assertIn('dashboardIconHtml("security")', self.render)

    def test_both_watermarks_share_one_size_and_offset(self):
        mark = self.css[self.css.index(".dashboard-home-watermark {"):]
        mark = mark[:mark.index("}")]
        self.assertIn("inset-block-end: calc(var(--outer-space) * -1);", mark)
        self.assertIn("inset-inline-end: calc(var(--outer-space) * -1);", mark)
        icon = self.css[self.css.index(".dashboard-home-watermark .koti-icon {"):]
        self.assertIn("--icon-size: 8rem;", icon[:icon.index("}")])
        self.assertEqual(self.css.count("--icon-size: 8rem;"), 1)

    def test_each_card_sits_under_a_title_outside_the_card(self):
        markup = self.render[self.render.index("const homeControlsMarkup = `"):]
        markup = markup[:markup.index("`;")]
        for title in ("Weather", "News", "Scenes", "Security", "Continue watching"):
            block = f'<div class="dashboard-home-block">\n    <h2 class="dashboard-home-block-title">{title}</h2>'
            self.assertIn(block, markup)
        # The title is a sibling of the card, never inside it.
        self.assertNotIn("dashboard-home-section-title", self.envjs)
        self.assertNotIn("dashboard-home-section-head", self.envjs)

    def test_a_hidden_card_takes_its_title_with_it(self):
        self.assertIn(".dashboard-home-block:has(> .dashboard-home-card[hidden]) {\n  display: none;", self.css)

    def test_title_is_top_left_above_the_card(self):
        title = self.css[self.css.index(".dashboard-home-block-title {"):]
        title = title[:title.index("}")]
        self.assertIn("margin: 0 0 ", title)
        block = self.css[self.css.index(".dashboard-home-block {"):]
        self.assertIn("flex-direction: column;", block[:block.index("}")])

    def test_now_playing_tile_has_no_watermark(self):
        self.assertNotIn("koti-fa-film", self.media)

    def test_sections_keep_an_accessible_name(self):
        for label in ("Scenes", "Security", "News", "Continue watching"):
            self.assertIn(f'aria-label="{label}"', self.render)
        self.assertIn('aria-label="Open weather and conditions"', self.render)

    def test_scenes_and_security_sit_side_by_side_when_the_column_is_wide_enough(self):
        self.assertIn("container: home-column / inline-size;", self.css)
        wide = self.css[self.css.index("@container home-column (min-width: 31.25rem) {"):]
        wide = wide[:wide.index("\n}\n")]
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", wide)
        # The middle Home column is the widest so the pair fits there.
        self.assertIn("minmax(23.25rem, 1fr) minmax(31.25rem, 1.35fr) minmax(17rem, 1fr);", self.css)

    def test_scenes_and_security_each_a_two_column_grid_icon_on_top_label_under(self):
        self.assertIn('<div class="dashboard-home-pair">', self.render)
        pair = self.render[self.render.index('<div class="dashboard-home-pair">'):]
        pair = pair[:pair.index('data-home-media-shelf')]
        self.assertLess(pair.index('aria-label="Scenes"'), pair.index('aria-label="Security"'))
        stack = self.css[self.css.index(".dashboard-home-pair {"):]
        self.assertIn("grid-template-columns: minmax(0, 1fr);", stack[:stack.index("}")])
        grid = self.css[self.css.index(".dashboard-home-pair :is(.dashboard-home-arm-row, .dashboard-home-light-row) {"):]
        grid = grid[:grid.index("}")]
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", grid)
        # Icon on top, label under: the pair adds no row-direction override to the shared button rule.
        self.assertNotIn(".dashboard-home-pair :is(.dashboard-home-arm-btn, .dashboard-home-light-btn)", self.css)
        # Security's third button sits under the first, not centred across both columns.
        third = self.css[self.css.index(".dashboard-home-pair .dashboard-home-arm-row > :last-child:nth-child(odd) {"):]
        self.assertIn("grid-column: auto;", third[:third.index("}")])
        self.assertEqual(self.render.count('data-dashboard-action="set-home-light-mode"'), 4)
        self.assertEqual(self.render.count('data-dashboard-action="set-home-arm-mode"'), 3)

    def test_large_box_starts_the_second_column_one_outer_space_after_the_first(self):
        self.assertIn("container: home-pair-card / inline-size;", self.css)
        wide = self.css[self.css.index("@container home-pair-card (min-width: 15rem) {"):]
        wide = wide[:wide.index("\n}\n")]
        self.assertIn("grid-template-columns: repeat(2, var(--dashboard-home-mode-button-width));", wide)
        self.assertIn("column-gap: var(--outer-space);", wide)

    def test_modal_mode_selectors_keep_their_own_layout(self):
        # The pair rules are scoped to the Home pair; the shared button rules stay column based.
        shared = self.css[self.css.index(".dashboard-home-arm-btn,\n.dashboard-home-light-btn {\n  flex: 0 0"):]
        self.assertIn("flex-direction: column;", shared[:shared.index("}")])

    def test_one_spacing_value_between_sections_and_at_the_screen_edge(self):
        home = self.css[self.css.index("\n.dashboard-home {"):]
        home = home[:home.index("}")]
        self.assertIn("gap: var(--outer-space);", home)
        self.assertIn("padding: 0 var(--outer-space) var(--outer-space);", home)
        self.assertIn("column-gap: var(--outer-space);\n    max-inline-size: none;", self.css)
        pair = self.css[self.css.index(".dashboard-home-pair {"):]
        self.assertIn("gap: var(--outer-space);", pair[:pair.index("}")])


if __name__ == "__main__":
    unittest.main()
