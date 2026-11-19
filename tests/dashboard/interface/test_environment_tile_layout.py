"""Home weather tile: borderless groups, solid house, and one-line icon alignment."""
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
        body = rule(".dashboard-home-environment-section .dashboard-home-environment-group-indoor::before")
        self.assertIn("clip-path: polygon(", body)
        self.assertRegex(body, r"background:\s*color-mix")

    def test_columns_share_the_bottom_edge_so_five_icons_align(self):
        self.assertRegex(rule(".dashboard-home-environment-section .dashboard-home-environment-grid"), r"align-items:\s*end")

    def test_lower_row_holds_three_tiles_and_hero_two(self):
        self.assertRegex(rule(".dashboard-home-environment-section .dashboard-home-environment-lower"), r"repeat\(3,")
        self.assertRegex(rule(".dashboard-home-environment-section .dashboard-home-environment-hero"), r"repeat\(2,")

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
