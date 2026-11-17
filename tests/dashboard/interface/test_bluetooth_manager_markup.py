import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class BluetoothManagerMarkupTests(unittest.TestCase):
    def setUp(self):
        self.render = (ROOT / "static/js/dashboard-render.js").read_text(encoding="utf-8")

    def test_every_element_the_manager_looks_up_is_in_the_modal(self):
        # renderDashboardBluetoothManager returns early when the device list
        # element is missing, which left the window on its default "Power: Off".
        start = self.render.index('<div id="dashboardBluetoothSettingsModal"')
        modal = self.render[start:self.render.index("function ", start)]
        code_start = self.render.index("function dashboardBluetoothRender")
        code = self.render[code_start:]
        looked_up = set(re.findall(r'getElementById\("(dashboardBluetooth\w+)"\)', code))
        self.assertIn("dashboardBluetoothDeviceList", looked_up)
        for element_id in looked_up:
            self.assertIn(f'id="{element_id}"', modal, element_id)


if __name__ == "__main__":
    unittest.main()
