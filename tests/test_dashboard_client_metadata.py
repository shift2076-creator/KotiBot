import unittest
from pathlib import Path
from threading import RLock

from flask import Flask

from server_core.routes import register_server_routes


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DashboardClientMetadataRouteTests(unittest.TestCase):
    def build_client(self, clients):
        saves = []
        broadcasts = []
        app = Flask(__name__)

        def has_role(client, role):
            roles = client.get("clientRole", [])
            if not isinstance(roles, list):
                roles = [roles]
            return role in roles

        def status_payload():
            return {
                "clients": [dict(client) for client in clients.values()],
                "used_zones": sorted({
                    client.get("zone_name", "")
                    for client in clients.values()
                    if client.get("zone_name")
                }),
            }

        register_server_routes(app, {
            "state_lock": RLock(),
            "sse_listeners": [],
            "clients": clients,
            "clean_zone_name": lambda value: str(value or "").strip(),
            "client_has_role": has_role,
            "client_role_tapo": "TAPO",
            "save_state": lambda: saves.append(True),
            "current_status_payload": status_payload,
            "broadcast_state": lambda: broadcasts.append(True),
        })

        return app.test_client(), saves, broadcasts

    def test_android_metadata_is_persisted_and_queued_for_client_convergence(self):
        clients = {
            "android-1": {
                "deviceID": "android-1",
                "clientName": "Old Android",
                "clientRole": ["CAM", "DSS"],
                "provisioned": True,
                "source": "android",
                "zone_name": "Old Zone",
            },
        }
        client, saves, broadcasts = self.build_client(clients)

        response = client.post("/api/client-metadata", json={
            "deviceIDs": ["android-1"],
            "clientName": "Front Monitor",
            "zoneName": "Entry",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["updatedDeviceIDs"], ["android-1"])
        self.assertEqual(clients["android-1"]["clientName"], "Front Monitor")
        self.assertEqual(clients["android-1"]["zone_name"], "Entry")
        self.assertEqual(clients["android-1"]["pending_command"], {
            "clientName": "Front Monitor",
            "zoneName": "Entry",
            "zone_name": "Entry",
        })
        self.assertEqual(len(saves), 1)
        self.assertEqual(len(broadcasts), 1)

    def test_matter_endpoint_group_is_saved_as_one_physical_identity(self):
        clients = {
            "matter:7:1": {
                "deviceID": "matter:7:1",
                "clientName": "Old Contact",
                "clientRole": ["DSS"],
                "provisioned": True,
                "source": "matter",
                "zone_name": "Hall",
            },
            "matter:7:2": {
                "deviceID": "matter:7:2",
                "clientName": "Old Temperature",
                "clientRole": ["DSS"],
                "provisioned": True,
                "source": "matter",
                "zone_name": "Hall",
            },
        }
        client, saves, broadcasts = self.build_client(clients)

        response = client.post("/api/client-metadata", json={
            "deviceIDs": ["matter:7:1", "matter:7:2", "matter:7:1"],
            "clientName": "Rear Door",
            "zone_name": "Kitchen",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["updatedDeviceIDs"],
            ["matter:7:1", "matter:7:2"],
        )
        for matter_client in clients.values():
            self.assertEqual(matter_client["clientName"], "Rear Door")
            self.assertEqual(matter_client["zone_name"], "Kitchen")
            self.assertNotIn("pending_command", matter_client)
        self.assertEqual(len(saves), 1)
        self.assertEqual(len(broadcasts), 1)

    def test_missing_group_member_rejects_the_whole_matter_rename(self):
        clients = {
            "matter:8:1": {
                "deviceID": "matter:8:1",
                "clientName": "Original",
                "clientRole": ["DSS"],
                "source": "matter",
                "zone_name": "Entry",
            },
        }
        client, saves, broadcasts = self.build_client(clients)

        response = client.post("/api/client-metadata", json={
            "deviceIDs": ["matter:8:1", "matter:8:2"],
            "clientName": "Partial Rename Must Not Persist",
            "zoneName": "Kitchen",
        })

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["missingDeviceIDs"], ["matter:8:2"])
        self.assertEqual(clients["matter:8:1"]["clientName"], "Original")
        self.assertEqual(clients["matter:8:1"]["zone_name"], "Entry")
        self.assertEqual(saves, [])
        self.assertEqual(broadcasts, [])


class DashboardClientMetadataFrontendContractTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_shared_editor_uses_server_owned_group_metadata_route(self):
        source = self.source("static/js/dashboard-actions.js")
        legacy_rename_source = self.source_block(
            source,
            "window.renameClient = async function",
            "let clientTransientHoldTimer =",
        )
        save_source = self.source_block(
            source,
            "window.saveClientMenuMeta = async function",
            "window.cameraVideoModalRefreshTimer =",
        )

        self.assertIn('postJson("/api/client-metadata"', save_source)
        self.assertIn("deviceIDs: targetDeviceIDs", save_source)
        self.assertNotIn('postJson("/api/client-command"', save_source)
        self.assertIn("server can validate and save", save_source)
        self.assertIn("syncDashboardClientMetadataCards?.(", save_source)
        self.assertIn("renderDashboardDataNow(data);", save_source)
        self.assertIn(
            "targeted handoff above owns immediate visible metadata",
            save_source,
        )
        self.assertIn("do not turn it into a second status request", save_source)
        self.assertIn('postJson("/api/client-metadata"', legacy_rename_source)
        self.assertIn("deviceIDs: targetDeviceIDs", legacy_rename_source)
        self.assertNotIn('postJson("/api/client-command"', legacy_rename_source)
        self.assertIn("same registry-owned mutation", legacy_rename_source)
        self.assertIn(
            "syncDashboardClientMetadataCards?.(",
            legacy_rename_source,
        )

    def test_reused_cards_reconcile_titles_and_tapo_modal_bootstrap_data(self):
        source = self.source("static/js/dashboard-render.js")
        metadata_source = self.source_block(
            source,
            "function syncDashboardCardMetadata(el, c)",
            "function dashboardBool(value)",
        )

        self.assertIn('el.querySelector(".card-title")', metadata_source)
        self.assertIn(
            "cardTitle.textContent = nextCardTitle",
            metadata_source,
        )
        self.assertIn(
            "window.syncDashboardClientMetadataCards = function",
            metadata_source,
        )
        self.assertIn(
            '"#clientCards [data-dashboard-device-card][data-device-id]"',
            metadata_source,
        )
        self.assertIn(
            "syncDashboardCardMetadata(card,",
            metadata_source,
        )
        self.assertIn(
            "syncDashboardCardMetadata(el, c);",
            metadata_source,
        )
        self.assertIn(
            "whole-page render reaching the current",
            metadata_source,
        )
        self.assertIn(
            'el.querySelectorAll("[data-tapo-name]")',
            metadata_source,
        )
        self.assertIn(
            "control.dataset.tapoName = nextCardTitle",
            metadata_source,
        )


if __name__ == "__main__":
    unittest.main()
