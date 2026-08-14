import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DashboardNewDeviceModalNavigationTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding='utf-8')

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_every_new_device_card_uses_modal_aware_settings_action(self):
        source = self.source(
            'subsystems/matter/static/js/matter-render.js'
        )
        matter_card = self.source_block(
            source,
            'window.renderMatterClientCard = function',
            'window.syncMatterCardEnvironment = function',
        )
        tapo_card = self.source_block(
            source,
            'function matterFoundTapoCard(c)',
            'function matterFoundAndroidClientTitle(c)',
        )
        android_card = self.source_block(
            source,
            'function matterFoundAndroidClientCard(c)',
            'window.dashboardHomeFoundClients = function',
        )

        for label, card_source in (
            ('Matter', matter_card),
            ('Tapo', tapo_card),
            ('Android', android_card),
        ):
            with self.subTest(card=label):
                self.assertIn(
                    'data-dashboard-action="open-dashboard-client-settings"',
                    card_source,
                )
                self.assertNotIn(
                    'data-dashboard-action="open-client-menu"',
                    card_source,
                )

    def test_modal_aware_action_hides_devices_before_opening_child(self):
        source = self.source('static/js/dashboard-actions.js')
        open_helper = self.source_block(
            source,
            'function dashboardOpenClientMenuFromRegistry(',
            'window.openDashboardClientSettings = async function',
        )
        open_action = self.source_block(
            source,
            'window.openDashboardClientSettings = async function',
            'window.dashboardActivityViewportLimit = function',
        )

        hide_call = open_helper.index(
            'dashboardHideParentModalForSubmodal('
        )
        open_call = open_helper.index('window.openClientMenuNow?.(')

        self.assertLess(hide_call, open_call)
        self.assertIn('"dashboardClientsModal"', open_helper)
        self.assertIn(
            'dashboardOpenClientMenuFromRegistry(event, deviceID, "matter")',
            open_action,
        )
        self.assertIn(
            'dashboardOpenClientMenuFromRegistry(event, deviceID, "client")',
            open_action,
        )
        self.assertNotIn('setTimeout', open_helper)
        self.assertNotIn('setInterval', open_helper)

    def test_delegated_action_and_close_restore_the_devices_modal(self):
        events = self.source('static/js/dashboard-events.js')
        actions = self.source('static/js/dashboard-actions.js')
        delegated = self.source_block(
            events,
            '    "open-dashboard-client-settings": async (el, event) => {',
            '    "hide-client-menu": () => {',
        )
        hide_client = self.source_block(
            actions,
            'window.hideClientMenuModal = function',
            'window.showDashboardClientMenu = function',
        )

        self.assertIn(
            'await window.openDashboardClientSettings?.(event, deviceID);',
            delegated,
        )
        self.assertIn(
            'dashboardRestoreParentModalFromSubmodal(modal)',
            hide_client,
        )


if __name__ == '__main__':
    unittest.main()
