import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class MatterFirstConnectionTests(unittest.TestCase):
    """A fresh controller has no Matter device, so the page has no node number to reuse."""

    def setUp(self):
        self.actions = (ROOT / "static/js/dashboard-actions.js").read_text(encoding="utf-8")

    def test_first_connection_has_a_default_node_number(self):
        match = re.search(r'const DASHBOARD_MATTER_FIRST_NODE_ID = "(\w+)";', self.actions)
        self.assertIsNotNone(match)
        self.assertTrue(match.group(1).isdigit())

    def test_recommission_handler_falls_back_to_the_default(self):
        start = self.actions.index('"/api/matter/recommission"')
        handler = self.actions[self.actions.rindex("const nodeID = String(", 0, start):start]
        self.assertIn("modal?.dataset?.nodeId", handler)
        self.assertIn("dashboardMatterNodeID", handler)
        self.assertIn("DASHBOARD_MATTER_FIRST_NODE_ID", handler)
        self.assertNotIn('|| ""', handler)


if __name__ == "__main__":
    unittest.main()
