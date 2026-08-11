import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CameraRecordingIndicatorTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    def test_android_and_tapo_cards_share_the_recording_indicator(self):
        renderers = (
            "subsystems/client-android-home/static/js/client-android-home-render.js",
            "subsystems/client-tapo/static/js/tapo-render.js",
        )

        for relative_path in renderers:
            with self.subTest(relative_path=relative_path):
                source = self.source(relative_path)
                self.assertIn('class="camera-record-btn', source)
                self.assertIn("camera-record-dot", source)
                self.assertIn("camera-record-label", source)
                self.assertIn("aria-pressed", source)

    def test_live_state_updates_preserve_the_shared_active_contract(self):
        dashboard_render = self.source("static/js/dashboard-render.js")
        android_actions = self.source("static/js/dashboard-actions.js")
        tapo_actions = self.source(
            "subsystems/client-tapo/static/js/tapo-actions.js"
        )

        self.assertIn(
            'recordBtn.classList.toggle("active", isRecording);',
            dashboard_render,
        )
        self.assertIn(
            'btn.classList.toggle("active", !!nextVal);',
            android_actions,
        )
        self.assertIn(
            'button.classList.toggle("active", isRecording);',
            tapo_actions,
        )

    def test_indicator_is_subdued_inactive_and_glows_red_active(self):
        style = self.source("static/css/style.css")

        inactive_rule = re.search(
            r"\.camera-record-dot\s*\{(?P<body>.*?)\n\}",
            style,
            re.DOTALL,
        )
        active_rule = re.search(
            r"\.camera-record-btn\.active\s+\.camera-record-dot\s*"
            r"\{(?P<body>.*?)\n\}",
            style,
            re.DOTALL,
        )
        pulse_rule = re.search(
            r"\.camera-record-btn\.active\s+\.camera-record-dot::after\s*"
            r"\{(?P<body>.*?)\n\}",
            style,
            re.DOTALL,
        )

        self.assertIsNotNone(inactive_rule)
        self.assertIn(
            "background: var(--camera-record-inactive-color);",
            inactive_rule.group("body"),
        )
        self.assertIn(
            "--camera-record-inactive-color: color-mix(",
            style,
        )
        self.assertIsNotNone(active_rule)
        self.assertIn(
            "background: var(--camera-record-active-color);",
            active_rule.group("body"),
        )
        self.assertIn("#ff2038", style)
        self.assertIn("box-shadow:", active_rule.group("body"))
        self.assertIsNotNone(pulse_rule)
        self.assertIn(
            "animation: camera-record-pulse",
            pulse_rule.group("body"),
        )
        self.assertIn("@keyframes camera-record-pulse", style)

    def test_reduced_motion_keeps_an_unmistakable_static_active_glow(self):
        style = self.source("static/css/style.css")
        reduced_motion = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*"
            r"\.camera-record-btn\.active\s+\.camera-record-dot::after\s*"
            r"\{(?P<body>.*?)\n\s*\}\s*\}",
            style,
            re.DOTALL,
        )

        self.assertIsNotNone(reduced_motion)
        self.assertIn("animation: none;", reduced_motion.group("body"))
        self.assertIn("opacity: .92;", reduced_motion.group("body"))
        self.assertIn("transform: scale(1.08);", reduced_motion.group("body"))


if __name__ == "__main__":
    unittest.main()
