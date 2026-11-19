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
            "PiVault Certificate": '/certificate',
            "Network": '/network',
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
        self.assertIn("`https://${location.hostname}${port}${tool.path || \"/\"}`", self.render)
        item = self.render[self.render.index("function dashboardPivaultToolItemsHtml"):]
        item = item[:item.index("window.syncSettingsApkDownloads")]
        self.assertIn('target="_blank" rel="noopener noreferrer"', item)

    def test_settings_modal_shows_the_tools_section(self):
        modal = self.render[self.render.index('<div id="settingsModal"'):]
        self.assertIn('<h2 class="modal-section-title">Tools</h2>', modal)
        self.assertIn('id="settingsPivaultTools"', modal)
        self.assertIn("${dashboardPivaultToolItemsHtml()}", modal)


if __name__ == "__main__":
    unittest.main()
