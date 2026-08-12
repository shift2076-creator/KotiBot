import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class AndroidCameraTalkDashboardVisibilityTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (
            REPOSITORY_ROOT / relative_path
        ).read_text(encoding="utf-8")

    def test_android_camera_renderer_keeps_the_talk_control_contract(self):
        renderer = self.source(
            "subsystems/client-android-home/static/js/"
            "client-android-home-render.js"
        )

        self.assertIn(
            "window.shouldRenderAndroidCameraTalkButton(c)",
            renderer,
        )
        self.assertIn(
            'class="icon-btn camera-talk-btn',
            renderer,
        )
        self.assertIn(
            'data-camera-talk-button="1"',
            renderer,
        )

    def test_normal_dashboard_viewer_is_not_rejected_by_talk_policy(self):
        actions = self.source(
            "subsystems/voice/static/js/voice-actions.js"
        )

        self.assertNotIn(
            "dashboardCameraTalkViewerIsAndroidKeyClientApp",
            actions,
        )
        self.assertIn(
            "Camera talk is an authenticated dashboard capability",
            actions,
        )

    def test_talk_policy_still_rejects_ineligible_camera_targets(self):
        actions = self.source(
            "subsystems/voice/static/js/voice-actions.js"
        )

        self.assertIn(
            "if (!c?.provisioned || c?.stale) return false;",
            actions,
        )
        self.assertIn(
            'if (!dashboardCameraTalkClientHasRole(c, "CAM")) '
            "return false;",
            actions,
        )
        self.assertIn(
            'dashboardCameraTalkClientHasRole(c, "TAPO")',
            actions,
        )
        self.assertIn(
            'c.tapo_kind === "camera"',
            actions,
        )

    def test_sec005_candidate_history_boundary_remains_ephemeral(self):
        voice_routes = self.source(
            "subsystems/voice/voice_routes.py"
        )

        self.assertIn(
            "persist_history = "
            "clean_event_type != 'camera_talk_candidate'",
            voice_routes,
        )
        self.assertIn(
            "persist_history=persist_history,",
            voice_routes,
        )

    def test_camera_talk_device_endpoints_remain_signed(self):
        security_routes = self.source(
            "subsystems/security/security_routes.py"
        )

        self.assertIn(
            "'/api/camera-talk/client/',",
            security_routes,
        )
        self.assertIn(
            "'/api/voice/client/',",
            security_routes,
        )


if __name__ == "__main__":
    unittest.main()
