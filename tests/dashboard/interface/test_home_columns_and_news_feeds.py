import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class HomeColumnsAndNewsFeedsTests(unittest.TestCase):
    def setUp(self):
        self.render = read("static/js/dashboard-render.js")
        self.events = read("static/js/dashboard-events.js")
        self.actions = read("static/js/dashboard-actions.js")
        self.css = read("static/css/style.css")

    def test_home_cards_are_in_three_columns_in_the_requested_order(self):
        markup = self.render[self.render.index("const homeControlsMarkup = `"):]
        markup = markup[:markup.index("`;")]
        columns = markup.split('<div class="dashboard-home-column">')[1:]
        self.assertEqual(len(columns), 3)
        self.assertIn("renderDashboardHomeEnvironmentSection", columns[0])
        self.assertIn("data-home-news-shelf", columns[0])
        self.assertLess(columns[0].index("renderDashboardHomeEnvironmentSection"), columns[0].index("data-home-news-shelf"))
        self.assertIn("dashboard-home-light-section", columns[1])
        self.assertIn("dashboard-home-arm-section", columns[1])
        self.assertIn("data-home-media-shelf", columns[2])
        self.assertLess(markup.index("data-home-matter-found-slot"), markup.index('dashboard-home-column'))

    def test_columns_only_apply_on_wide_landscape_screens(self):
        block = self.css[self.css.index("@media (min-width: 1180px)"):]
        block = block[:block.index("\n}\n\n") + 3]
        self.assertIn("repeat(3, minmax(0, 1fr))", block)
        self.assertIn("orientation: landscape", block)
        self.assertIn("grid-column: 1 / -1", block)

    def test_found_device_animation_selectors_follow_the_columns(self):
        self.assertNotIn(".dashboard-home-arm-section\n)", self.css)
        self.assertEqual(len(re.findall(r"dashboard-home-matter-found-slot[^{]*~ \.dashboard-home-column", self.css)), 3)

    def test_news_card_is_synced_after_home_renders_and_script_is_loaded(self):
        self.assertIn("window.syncDashboardHomeNewsShelf?.(home);", self.render)
        self.assertIn("js/dashboard-news-shelf.js", read("templates/index.html"))
        self.assertNotIn("innerHTML", read("static/js/dashboard-news-shelf.js"))

    def test_news_rows_end_with_a_kind_icon_and_there_is_no_filter(self):
        shelf = read("static/js/dashboard-news-shelf.js")
        for icon in ("koti-fa-file-lines", "koti-fa-circle-play", "koti-fa-music"):
            self.assertIn(icon, shelf)
        self.assertNotIn("dashboard-activity-filter", shelf)
        self.assertNotIn("news-filter", self.events)
        self.assertNotIn("setDashboardNewsKind", shelf)

    def test_each_feed_has_a_type_button_that_cycles_through_the_kinds(self):
        self.assertIn('"rss-feed-kind"', self.events)
        self.assertIn('"rss-feed-kind"', self.actions)
        self.assertIn('["auto", "video", "audio", "article"]', self.actions)

    def test_settings_has_a_news_feeds_window_with_working_actions(self):
        self.assertIn('data-dashboard-action="show-rss-feeds"', self.render)
        modal = self.render[self.render.index('<div id="dashboardRssModal"'):]
        modal = modal[:modal.index('<div id="dashboardNotificationsModal"')]
        self.assertEqual(modal.count("<h1"), 1)
        self.assertEqual(modal.count('class="modal-section-title"'), 2)
        self.assertNotIn("settings-note\"></", modal.replace('id="dashboardRssStatus" class="settings-note" hidden', ""))
        for action in ("show-rss-feeds", "hide-rss-feeds", "rss-feed-add", "rss-feed-toggle", "rss-feed-kind", "rss-feed-remove"):
            self.assertIn(f'"{action}"', self.events, action)
        for fn in ("showDashboardRssModal", "hideDashboardRssModal", "addDashboardRssFeed",
                   "updateDashboardRssFeed", "removeDashboardRssFeed"):
            self.assertIn(f"window.{fn} = ", self.actions, fn)
        self.assertIn('["dashboardRssModal", "hideDashboardRssModal"]', self.events)

    def test_new_window_stays_before_the_users_modal_for_the_icon_count_test(self):
        self.assertLess(self.render.index('<div id="dashboardRssModal"'),
                        self.render.index('<div id="dashboardUsersSettingsModal"'))


if __name__ == "__main__":
    unittest.main()
