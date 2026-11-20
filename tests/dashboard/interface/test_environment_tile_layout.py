"""Home weather tile: five columns, house on the right planted in the ground, borderless groups."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CSS = (ROOT / "static/css/style.css").read_text()
JS = (ROOT / "static/js/dashboard-render.js").read_text()


def rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, selector
    return match.group(1)


class EnvironmentTileLayout(unittest.TestCase):
    def test_groups_have_no_border_or_fill_on_the_home_tile(self):
        body = rule(".dashboard-home-environment-section .dashboard-home-environment-group")
        self.assertRegex(body, r"border:\s*0")
        self.assertRegex(body, r"background:\s*transparent")

    def test_house_is_a_solid_clipped_shape_behind_the_indoor_readings(self):
        body = rule(".dashboard-home-environment-section .dashboard-home-environment-house")
        self.assertIn("clip-path: polygon(", body)
        self.assertRegex(body, r"background:\s*color-mix")
        self.assertIn("grid-column: 4 / 6;", body)

    def test_five_readings_are_columns_of_one_bottom_row(self):
        grid = rule(".dashboard-home-environment-section .dashboard-home-environment-grid")
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr));", grid)
        self.assertRegex(grid, r"align-items:\s*end")
        metric = rule(".dashboard-home-environment-section .dashboard-home-environment-metric:not(.dashboard-home-environment-metric-hero)")
        self.assertIn("grid-row: 2;", metric)
        # Outdoor readings fill the first columns; the two home readings sit on the right over the house.
        self.assertIn("grid-column: 4;", rule(".dashboard-home-environment-section .dashboard-home-environment-metric-indoor_temp"))
        self.assertIn("grid-column: 5;", rule(".dashboard-home-environment-section .dashboard-home-environment-metric-humidity"))

    def test_the_house_is_planted_in_the_ground(self):
        body = rule(".dashboard-home .dashboard-home-environment-section")
        self.assertIn("padding-block-end: 0;", body)

    def test_hero_spans_three_columns_and_stops_one_outer_space_short_of_the_house(self):
        hero = rule(".dashboard-home-environment-section .dashboard-home-environment-hero")
        self.assertIn("grid-column: 1 / 4;", hero)
        self.assertIn("justify-content: space-between;", hero)
        self.assertIn("padding-inline-end: var(--outer-space);", hero)

    def test_markup_puts_outdoor_first_then_the_house_then_the_indoor_readings(self):
        outdoor = JS.index("dashboard-home-environment-group-outdoor")
        house = JS.index('class="dashboard-home-environment-house"')
        indoor = JS.index("dashboard-home-environment-group-indoor")
        self.assertLess(outdoor, house)
        self.assertLess(house, indoor)

    def test_the_environment_window_keeps_its_bordered_groups(self):
        body = rule(".dashboard-home-environment-group")
        self.assertIn("border: 1px solid var(--border);", body)
        self.assertIn("background: var(--background-preview);", body)
        self.assertIn("repeat(2, minmax(0, 1fr))", rule(".dashboard-home-environment-grid"))

    def test_the_live_home_card_uses_the_tile(self):
        live = (ROOT / "subsystems/environment/static/js/environment-render.js").read_text()
        self.assertIn("return window.dashboardHomeEnvironmentTileHtml();", live)
        self.assertIn("window.dashboardHomeEnvironmentTileHtml = dashboardHomeEnvironmentLoadingSection;", JS)

    def test_the_five_bottom_readings_have_no_labels(self):
        self.assertEqual(JS.count("noLabel: true"), 3)  # two indoor tiles + the lower-row spread below
        self.assertIn("{ ...readings[id], noLabel: true }", JS)

    def test_renderer_puts_temperature_and_one_promoted_reading_in_the_hero(self):
        self.assertIn("dashboard-home-environment-hero", JS)
        self.assertIn("dashboardHomeEnvironmentFocusId(snapshot)", JS)
        self.assertIn('filter((id) => id !== focusId)', JS)


if __name__ == "__main__":
    unittest.main()
