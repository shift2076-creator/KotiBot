import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class JobsWindowTests(unittest.TestCase):
    def setUp(self):
        self.render = read("static/js/dashboard-render.js")
        self.actions = read("static/js/dashboard-actions.js")
        self.events = read("static/js/dashboard-events.js")
        self.css = read("static/css/modals.css")
        start = self.render.index('<div id="dashboardJobsModal"')
        self.modal = self.render[start:self.render.index('<div id="dashboardDevicesModal"')]

    def test_jobs_is_a_settings_row_opening_a_sub_modal(self):
        self.assertIn('data-dashboard-action="show-dashboard-jobs"', self.render)
        self.assertIn('id="settingsJobsSummary"', self.render)
        self.assertIn('<h1 id="dashboardJobsModalTitle" class="modal-title">Jobs</h1>', self.modal)
        self.assertIn('data-dashboard-action="hide-dashboard-jobs"', self.modal)
        for action in ("show-dashboard-jobs", "hide-dashboard-jobs"):
            self.assertIn(f'"{action}"', self.events)
        self.assertIn('["dashboardJobsModal", "hideDashboardJobsModal"]', self.events)

    def test_the_list_reserves_three_rows_before_the_data_arrives(self):
        self.assertEqual(self.modal.count("dashboard-jobs-row is-pending"), 1)
        self.assertIn(".repeat(3)", self.modal)
        self.assertIn('aria-busy="true"', self.modal)
        self.assertIn(".dashboard-jobs-row.is-pending", self.css)

    def test_loaded_content_uses_the_one_standard_fade_in(self):
        render = self.actions[self.actions.index("function dashboardJobsRender"):]
        render = render[:render.index("window.showDashboardJobsModal")]
        self.assertIn("window.dashboardFadeIn?.(list)", render)
        self.assertIn("window.dashboardFadeIn?.(internet)", render)

    def test_icons_use_the_standard_circle_and_no_size_of_their_own(self):
        self.assertIn('dashboardIconHtml(icon, "ui-icon-circle")', self.actions)
        block = self.css[self.css.index(".dashboard-jobs-row {"):]
        block = block[:block.index("}")]
        self.assertIn("var(--control-size)", block)

    def test_job_text_is_escaped_and_ids_do_not_reach_attributes(self):
        row = self.actions[self.actions.index("function dashboardJobsRowHtml"):]
        row = row[:row.index("function dashboardJobsRender")]
        for field in ("job.name", "job.schedule", "note", "label", "when"):
            self.assertIn(f"esc({field})", row)
        self.assertNotIn("job.id}", row)

    def test_unknown_results_show_as_not_run_yet(self):
        self.assertIn('"Not run yet"', self.actions)
        self.assertIn("Jobs are not set up on this machine yet", self.actions)

    def test_the_window_only_reads_the_jobs_list(self):
        load = self.actions[self.actions.index("window.showDashboardJobsModal"):]
        load = load[:load.index("window.hideDashboardJobsModal")]
        self.assertIn('dashboardPivaultJson("/api/jobs")', load)
        self.assertNotIn("method", load)


if __name__ == "__main__":
    unittest.main()
