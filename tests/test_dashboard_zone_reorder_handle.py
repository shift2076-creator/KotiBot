import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DashboardZoneReorderHandleTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_zone_header_renders_an_accessible_handle_before_the_title(self):
        render_source = self.source("static/js/dashboard-render.js")
        room_group_source = self.source_block(
            render_source,
            "window.ensureRoomGroup = function",
            "window.ensureRoomLanes = function",
        )

        handle_index = room_group_source.index(
            'class="icon-btn dashboard-zone-drag-handle"'
        )
        title_index = room_group_source.index(
            'class="modal-section-title room-title"'
        )

        self.assertLess(handle_index, title_index)
        self.assertIn('type="button"', room_group_source)
        self.assertIn('aria-label="Reorder ${esc(roomTitle)} zone"', room_group_source)
        self.assertIn("data-dashboard-zone-drag-handle", room_group_source)
        self.assertIn('dashboardIconHtml("koti-fa-grip")', room_group_source)

    def test_drag_ownership_is_limited_to_the_handle(self):
        actions_source = self.source("static/js/dashboard-actions.js")
        drag_source = self.source_block(
            actions_source,
            "window.handleControlsZoneDragPointerDown = function",
            "const DASHBOARD_BLUETOOTH_PAIRING_REFRESH_MS",
        )

        self.assertIn(
            '"#clientCards.room-dashboard [data-dashboard-zone-drag-handle]"',
            drag_source,
        )
        self.assertNotIn(
            'event.target.closest("#clientCards.room-dashboard .room-head")',
            drag_source,
        )
        self.assertIn("event.preventDefault();", drag_source)
        self.assertIn("handle.setPointerCapture?.(event.pointerId);", drag_source)
        self.assertIn("handle.releasePointerCapture?.(event.pointerId);", drag_source)

    def test_only_the_handle_disables_native_touch_panning(self):
        style_source = self.source("static/css/style.css")
        room_header_rule = re.search(
            r"\.room-head\s*\{(?P<body>.*?)\n\}",
            style_source,
            re.DOTALL,
        )
        handle_rule = re.search(
            r"\.dashboard-zone-drag-handle\s*\{(?P<body>.*?)\n\}",
            style_source,
            re.DOTALL,
        )

        self.assertIsNotNone(room_header_rule)
        self.assertNotIn("touch-action: none;", room_header_rule.group("body"))
        self.assertNotIn("cursor: grab;", room_header_rule.group("body"))
        self.assertIsNotNone(handle_rule)
        self.assertIn("touch-action: none;", handle_rule.group("body"))
        self.assertIn("cursor: grab;", handle_rule.group("body"))

    def test_pointer_completion_and_cancellation_preserve_existing_lifecycle(self):
        actions_source = self.source("static/js/dashboard-actions.js")
        drag_source = self.source_block(
            actions_source,
            "window.handleControlsZoneDragPointerDown = function",
            "const DASHBOARD_BLUETOOTH_PAIRING_REFRESH_MS",
        )

        for event_name in ("pointermove", "pointerup", "pointercancel"):
            self.assertIn(
                f'document.addEventListener("{event_name}"',
                drag_source,
            )
            self.assertIn(
                f'document.removeEventListener("{event_name}"',
                drag_source,
            )

        self.assertIn("dashboardZoneClearDragUi();", drag_source)
        self.assertIn("dashboardZoneSaveRoomOrder(nextRooms, dragMode);", drag_source)


if __name__ == "__main__":
    unittest.main()
