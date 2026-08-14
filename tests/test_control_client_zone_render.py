import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ControlClientZoneRenderTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding='utf-8')

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_control_class_or_key_capability_identifies_control_setup(self):
        source = self.source('static/js/dashboard-actions.js')
        menu = self.source_block(
            source,
            'window.renderDashboardClientMenu = function',
            'window.hideAudioModal = function',
        )
        control_classification = self.source_block(
            menu,
            '  const isControlProvisionClient = (',
            '  const isMonitorProvisionClient = (',
        )

        self.assertIn(
            'androidProfile.clientClass === "control"',
            control_classification,
        )
        self.assertIn(
            'provisionRoles.has("KEY")',
            control_classification,
        )

    def test_zone_markup_is_impossible_for_control_or_key_setup(self):
        source = self.source('static/js/dashboard-actions.js')
        menu = self.source_block(
            source,
            'window.renderDashboardClientMenu = function',
            'window.hideAudioModal = function',
        )
        zone_rule = self.source_block(
            menu,
            '  const provisionClientUsesZone = (',
            '  const provisionRoleValue =',
        )
        setup_form = self.source_block(
            menu,
            '    ${!isProvisioned ? `',
            '    ${needsSecureReenrollment ? `',
        )

        self.assertIn('!isControlProvisionClient', zone_rule)
        self.assertIn('!provisionRoles.has("KEY")', zone_rule)
        self.assertIn('${provisionClientUsesZone ? `', setup_form)
        self.assertEqual(
            setup_form.count(
                '<span class="client-menu-label">Zone</span>'
            ),
            1,
        )

    def test_key_provisioning_never_submits_or_persists_a_zone(self):
        actions = self.source('static/js/dashboard-actions.js')
        server = self.source('kotibot_server.py')
        client_provision = self.source_block(
            actions,
            'window.provisionClient = async function',
            'window.unlockDashboardSecurity = async function',
        )
        server_provision = self.source_block(
            server,
            "@app.route('/provision', methods=['POST'])",
            "@app.post('/api/re-enroll-client')",
        )

        self.assertIn(
            'if (!clientRole.includes("KEY")) {',
            client_provision,
        )
        self.assertIn('payload.zoneName = zoneName;', client_provision)
        self.assertIn(
            "c['zone_name'] = '' if CLIENT_ROLE_KEY in roles else zone_name",
            server_provision,
        )


if __name__ == '__main__':
    unittest.main()
