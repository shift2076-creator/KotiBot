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
            "Add User": '/users/add',
            "Password Manager": 'port: 8448',
            "Portainer": 'port: 9443',
            "Android devices": '/devices',
            "Radicale": 'port: 5232',
        }
        found = re.findall(r'label: "([^"]+)"', self.tools)
        self.assertEqual(sorted(found), sorted(expected))
        for label, target in expected.items():
            line = next(l for l in self.tools.splitlines() if f'"{label}"' in l)
            self.assertIn(target, line, label)

    def test_kotibot_has_no_entry_of_its_own(self):
        self.assertNotIn('label: "KotiBot"', self.tools)

    def test_links_are_https_on_this_host_and_open_safely(self):
        self.assertIn("`https://${dashboardServiceHost()}${port}${tool.path || \"/\"}`", self.render)
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


if __name__ == "__main__":
    unittest.main()
