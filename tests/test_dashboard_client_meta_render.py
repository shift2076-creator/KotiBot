import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DashboardClientMetaRenderTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_shared_device_metadata_save_renders_accepted_state_immediately(self):
        actions_source = self.source("static/js/dashboard-actions.js")
        immediate_render_source = self.source_block(
            actions_source,
            "function renderDashboardDataNow(data)",
            "function renderDashboardNavigationNow()",
        )
        save_source = self.source_block(
            actions_source,
            "window.saveClientMenuMeta = async function",
            "window.cameraVideoModalRefreshTimer =",
        )

        self.assertIn('typeof window.dashboardRenderNow === "function"', immediate_render_source)
        self.assertIn("return window.dashboardRenderNow(data);", immediate_render_source)
        self.assertIn("patchClientByDeviceId(", save_source)
        self.assertIn("syncDashboardClientMetadataCards?.(", save_source)
        self.assertIn("renderDashboardDataNow(data);", save_source)
        self.assertNotIn("requestDashboardRenderSafe(data);", save_source)
        self.assertIn(
            "targeted handoff above owns immediate visible metadata",
            save_source,
        )
        self.assertIn("do not turn it into a second status request", save_source)

    def test_tapo_metadata_save_uses_the_same_immediate_render_boundary(self):
        tapo_source = self.source(
            "subsystems/client-tapo/static/js/tapo-actions.js"
        )
        render_source = self.source_block(
            tapo_source,
            "function renderDashboardAfterTapoMetaSave(data = null)",
            "window.setTapoLightEditMode =",
        )
        save_source = self.source_block(
            tapo_source,
            "async function saveTapoLightMeta(values = {})",
            "function handleTapoBrightnessPreview",
        )

        self.assertIn("patchTapoLightMetaInCurrentData(target, fields);", save_source)
        self.assertIn(
            "patchTapoLightMetaInCurrentData(target, fields, refreshedData);",
            save_source,
        )
        self.assertEqual(save_source.count("renderDashboardAfterTapoMetaSave("), 2)
        self.assertIn('typeof window.dashboardRenderNow === "function"', render_source)
        self.assertIn("window.dashboardRenderNow(renderData);", render_source)
        self.assertIn("interaction-settle window", render_source)
        self.assertIn("Do not route", render_source)


if __name__ == "__main__":
    unittest.main()
