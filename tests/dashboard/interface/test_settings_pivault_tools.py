import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class SettingsPivaultToolsTests(unittest.TestCase):
    def setUp(self):
        self.render = (ROOT / "static/js/dashboard-render.js").read_text(encoding="utf-8")
        start = self.render.index("const DASHBOARD_PIVAULT_TOOLS = [")
        self.tools = self.render[start:self.render.index("];", start)]

    def test_the_launcher_tools_are_listed_with_their_targets(self):
        expected = {
            "Add User": 'service: "addUser"',
            "Password Manager": 'service: "passwords"',
            "Portainer": 'service: "portainer"',
            "Radicale": 'service: "calendar"',
        }
        found = re.findall(r'label: "([^"]+)"', self.tools)
        self.assertEqual(sorted(found), sorted(expected))
        for label, target in expected.items():
            line = next(l for l in self.tools.splitlines() if f'"{label}"' in l)
            self.assertIn(target, line, label)

    def test_kotibot_has_no_entry_of_its_own(self):
        self.assertNotIn('label: "KotiBot"', self.tools)

    def test_links_come_from_the_shared_resolver_and_open_safely(self):
        self.assertIn("window.dashboardServiceUrl(tool.service)", self.render)
        item = self.render[self.render.index("function dashboardPivaultToolItemsHtml"):]
        item = item[:item.index("window.syncSettingsApkDownloads")]
        self.assertIn('target="_blank" rel="noopener noreferrer"', item)

    def test_settings_modal_shows_the_tools_section(self):
        modal = self.render[self.render.index('<div id="settingsModal"'):]
        self.assertIn('<h2 class="modal-section-title">Tools</h2>', modal)
        self.assertIn('id="settingsPivaultTools"', modal)
        self.assertIn("${dashboardPivaultToolItemsHtml()}", modal)

    def test_certificate_is_a_settings_row_opening_a_sub_modal(self):
        self.assertNotIn('"PiVault Certificate"', self.tools)
        self.assertIn('data-dashboard-action="show-pivault-certificate"', self.render)
        modal = self.render[self.render.index('<div id="dashboardCertificateModal"'):]
        modal = modal[:modal.index('<div id="dashboardUsersSettingsModal"')]
        # Same shell as the other sub-modals: one h1 title, h2 section titles, settings notes. No new classes.
        self.assertIn('<h1 id="dashboardCertificateModalTitle" class="modal-title">PiVault Certificate</h1>', modal)
        self.assertIn('class="modal-section-title">Trust on this device</h2>', modal)
        self.assertIn('href="/api/pivault/certificate/ca.crt"', modal)
        self.assertIn("${dashboardCertificateStepsHtml()}", modal)
        self.assertNotIn("<details", self.render)
        events = (ROOT / "static/js/dashboard-events.js").read_text(encoding="utf-8")
        self.assertIn('"show-pivault-certificate"', events)
        self.assertIn('["dashboardCertificateModal", "hideDashboardCertificateModal"]', events)

    def test_network_is_a_settings_row_opening_a_sub_modal(self):
        self.assertNotIn('"Network"', self.tools)
        self.assertIn('data-dashboard-action="show-pivault-network"', self.render)
        modal = self.render[self.render.index('<div id="dashboardNetworkModal"'):]
        modal = modal[:modal.index('<div id="dashboardUsersSettingsModal"')]
        self.assertIn('<h1 id="dashboardNetworkModalTitle" class="modal-title">Network</h1>', modal)
        self.assertIn('class="modal-section-title">Ports</h2>', modal)
        self.assertIn('class="modal-section-title">Internet jobs</h2>', modal)
        self.assertIn('data-dashboard-action="pivault-network-save"', modal)
        events = (ROOT / "static/js/dashboard-events.js").read_text(encoding="utf-8")
        for action in ("show-pivault-network", "hide-pivault-network", "pivault-network-cycle", "pivault-network-save"):
            self.assertIn(f'"{action}"', events)
        self.assertIn('["dashboardNetworkModal", "hideDashboardNetworkModal"]', events)

    def test_notifications_and_devices_are_settings_rows_opening_sub_modals(self):
        self.assertNotIn('"Android devices"', self.tools)
        events = (ROOT / "static/js/dashboard-events.js").read_text(encoding="utf-8")
        actions = (ROOT / "static/js/dashboard-actions.js").read_text(encoding="utf-8")
        for key, title in (("notifications", "Admin notifications"), ("devices", "Android devices")):
            self.assertIn(f'data-dashboard-action="show-pivault-{key}"', self.render)
            name = key.capitalize()
            modal = self.render[self.render.index(f'<div id="dashboard{name}Modal"'):]
            modal = modal[:modal.index('<div id="dashboardUsersSettingsModal"')]
            self.assertIn(f'<h1 id="dashboard{name}ModalTitle" class="modal-title">{title}</h1>', modal)
            self.assertIn('class="modal-section-title">', modal)
            for action in (f"show-pivault-{key}", f"hide-pivault-{key}"):
                self.assertIn(f'"{action}"', events)
            self.assertIn(f'["dashboard{name}Modal", "hideDashboard{name}Modal"]', events)
            self.assertIn(f"window.showDashboard{name}Modal", actions)
            self.assertIn(f"window.hideDashboard{name}Modal", actions)

    def test_every_new_action_has_a_handler_and_a_template_user(self):
        events = (ROOT / "static/js/dashboard-events.js").read_text(encoding="utf-8")
        actions = (ROOT / "static/js/dashboard-actions.js").read_text(encoding="utf-8")
        for action in ("pivault-notification-resolve", "pivault-notifications-clear", "pivault-device-rename",
                       "pivault-device-toggle", "pivault-device-version", "pivault-device-sync"):
            self.assertIn(f'"{action}"', events)
            used = f'data-dashboard-action="{action}"' in self.render + actions or f'"{action}"' in actions
            self.assertTrue(used, action)

    def test_helper_and_certificate_links_are_same_origin_api_routes(self):
        self.assertIn('href="/api/pivault/devices/sync.py" download', self.render)
        self.assertIn('href="/api/pivault/certificate/ca.crt" download', self.render)

    def test_certificate_steps_are_collapsed_one_platform_at_a_time(self):
        modal = self.render[self.render.index('<div id="dashboardCertificateModal"'):]
        modal = modal[:modal.index('<div id="dashboardUsersSettingsModal"')]
        self.assertIn("${dashboardCertificateStepsHtml()}", modal)
        steps = self.render[self.render.index("function dashboardCertificateStepsHtml"):]
        steps = steps[:steps.index("window.syncSettingsCertificate")]
        self.assertIn('data-dashboard-action="pivault-certificate-platform"', steps)
        self.assertIn("data-certificate-steps", steps)
        self.assertIn(" hidden>", steps)
        self.assertNotIn("<details", steps)
        actions = (ROOT / "static/js/dashboard-actions.js").read_text(encoding="utf-8")
        self.assertIn("window.toggleDashboardCertificatePlatform", actions)
        events = (ROOT / "static/js/dashboard-events.js").read_text(encoding="utf-8")
        self.assertIn('"pivault-certificate-platform"', events)

    def test_body_text_is_plain_and_settings_note_is_only_for_status(self):
        # settings-note is the warning colour: only status messages may use it.
        for name in ("Certificate", "Network", "Notifications", "Devices"):
            modal = self.render[self.render.index(f'<div id="dashboard{name}Modal"'):]
            modal = modal[:modal.index('<div id="dashboardUsersSettingsModal"')] if name != "Devices" else modal[:modal.index('<div id="dashboardUsersSettingsModal"')]
            for tag in re.findall(r'<div id="([^"]+)" class="settings-note"', modal):
                self.assertTrue(tag.endswith("Status"), tag)
            self.assertNotRegex(modal, r'<div class="settings-note"')
        actions = (ROOT / "static/js/dashboard-actions.js").read_text(encoding="utf-8")
        self.assertIn("settings-bluetooth-device-meta", actions)
        self.assertIn("settings-bluetooth-device-row", actions)


if __name__ == "__main__":
    unittest.main()
