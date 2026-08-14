from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardUserAccountsUiTests(unittest.TestCase):
    def setUp(self):
        self.render = (
            ROOT / "static/js/dashboard-render.js"
        ).read_text(encoding="utf-8")
        self.api = (
            ROOT / "static/js/dashboard-api.js"
        ).read_text(encoding="utf-8")
        self.actions = (
            ROOT / "static/js/dashboard-actions.js"
        ).read_text(encoding="utf-8")
        self.events = (
            ROOT / "static/js/dashboard-events.js"
        ).read_text(encoding="utf-8")
        self.css = (
            ROOT / "static/css/modals.css"
        ).read_text(encoding="utf-8")

    @staticmethod
    def _between(source, start, end):
        start_index = source.index(start)
        end_index = source.index(end, start_index)
        return source[start_index:end_index]

    def test_user_accounts_modal_keeps_only_title_icon(self):
        modal = self._between(
            self.render,
            '<div id="dashboardUsersSettingsModal"',
            '<div id="dashboardBluetoothSettingsModal"',
        )
        self.assertEqual(modal.count("window.dashboardIconHtml("), 1)
        self.assertIn(
            'window.dashboardIconHtml("manage_accounts")',
            modal,
        )

        user_rows = self._between(
            self.render,
            "function renderDashboardUserRows",
            "window.renderDashboardUsers",
        )
        self.assertNotIn("dashboardIconHtml(", user_rows)

        session_rows = self._between(
            self.render,
            "function renderDashboardSessionRows",
            "window.renderDashboardSessions",
        )
        self.assertNotIn("dashboardIconHtml(", session_rows)

    def test_user_accounts_contains_user_and_session_lists(self):
        self.assertIn('id="dashboardUserList"', self.render)
        self.assertIn('id="dashboardSessionList"', self.render)
        self.assertIn(
            'data-dashboard-action="refresh-dashboard-sessions"',
            self.render,
        )
        self.assertIn(
            'data-dashboard-action="revoke-other-dashboard-sessions"',
            self.render,
        )
        self.assertIn(
            'data-dashboard-action="revoke-dashboard-session"',
            self.render,
        )

    def test_session_api_and_events_are_wired(self):
        self.assertIn(
            'window.listDashboardSecuritySessions = async function',
            self.api,
        )
        self.assertIn(
            'window.revokeDashboardSecuritySession = async function',
            self.api,
        )
        self.assertIn(
            'window.revokeOtherDashboardSecuritySessions = async function',
            self.api,
        )
        self.assertIn(
            '"/api/security/dashboard-sessions"',
            self.api,
        )
        self.assertIn('method: "DELETE"', self.api)

        for action in (
            '"refresh-dashboard-sessions"',
            '"revoke-dashboard-session"',
            '"revoke-other-dashboard-sessions"',
        ):
            self.assertIn(action, self.events)

    def test_session_refresh_is_view_or_action_driven_without_polling(self):
        sync_block = self._between(
            self.actions,
            "window.syncDashboardSecurityControls = async function",
            "function dashboardPasswordRequirementError",
        )
        self.assertIn("renderDashboardSessions", sync_block)
        self.assertNotIn("setInterval", sync_block)

        session_actions = self._between(
            self.actions,
            "window.refreshDashboardSessionsFromSettings = async function",
            "window.toggleCardDebugInfo = function",
        )
        self.assertNotIn("setInterval", session_actions)

    def test_session_rows_have_layout_support(self):
        self.assertIn(".settings-dashboard-session-list", self.css)
        self.assertIn(".settings-dashboard-session-row", self.css)
        self.assertIn(".settings-dashboard-session-meta", self.css)


if __name__ == "__main__":
    unittest.main()
