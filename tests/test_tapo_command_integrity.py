import asyncio
import importlib.util
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import AsyncMock, patch


SOURCE_ROOT = Path(__file__).resolve().parents[1]
TAPO_ROOT = SOURCE_ROOT / "subsystems" / "client-tapo"


def load_tapo_control():
    package_name = "_kotibot_tapo_command_integrity"
    module_name = f"{package_name}.tapo_control"

    for loaded_name in list(sys.modules):
        if loaded_name == package_name or loaded_name.startswith(f"{package_name}."):
            sys.modules.pop(loaded_name, None)

    package = types.ModuleType(package_name)
    package.__path__ = [str(TAPO_ROOT)]
    sys.modules[package_name] = package

    tapo_stub = types.ModuleType("tapo")
    tapo_stub.ApiClient = object

    spec = importlib.util.spec_from_file_location(
        module_name,
        TAPO_ROOT / "tapo_control.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    with (
        patch.dict(sys.modules, {"tapo": tapo_stub}),
        patch(
            "server_core.credentials.read_text_credential",
            return_value="fixture-credential",
        ),
    ):
        spec.loader.exec_module(module)

    return module


class TapoCommandIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control = load_tapo_control()

    def setUp(self):
        self.control._tapo_devices.clear()
        self.control._tapo_handles.clear()

    def test_cold_device_connections_are_serialized_across_request_loops(self):
        active = 0
        max_active = 0
        counter_lock = threading.Lock()
        start = threading.Barrier(4)

        async def reachable(_host):
            return True

        async def connect(item, verify_cached=True):
            nonlocal active, max_active

            with counter_lock:
                active += 1
                max_active = max(max_active, active)

            await asyncio.sleep(0.04)
            handle = object()
            self.control._tapo_handles[item["id"]] = handle

            with counter_lock:
                active -= 1

            return handle

        def worker(index):
            start.wait()
            return asyncio.run(self.control._get_tapo_device(
                {
                    "id": f"device-{index}",
                    "ip": f"192.0.2.{index + 1}",
                },
                verify_cached=False,
            ))

        results = []
        threads = []

        with (
            patch.object(self.control, "_tapo_host_reachable", side_effect=reachable),
            patch.object(self.control, "_connect_tapo_device", side_effect=connect),
        ):
            for index in range(3):
                thread = threading.Thread(
                    target=lambda current=index: results.append(worker(current)),
                )
                threads.append(thread)
                thread.start()

            start.wait()

            for thread in threads:
                thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 3)
        self.assertEqual(max_active, 1)

    def test_extender_child_command_uses_kasa_path_without_parent_handle(self):
        item = {
            "id": "extender",
            "ip": "192.0.2.10",
            "model": "P306",
            "device_type": "SMART.TAPOPLUG",
            "kind": "outlet_extender",
            "children": [{
                "id": "child-4",
                "position": 4,
                "cli_index": 3,
                "is_on": False,
            }],
        }
        verified = {
            **item,
            "control_ready": True,
            "control_error": "",
            "children": [{
                "id": "child-4",
                "position": 4,
                "cli_index": 3,
                "is_on": True,
            }],
            "is_on": True,
        }
        self.control._tapo_devices[item["id"]] = item

        with (
            patch.object(
                self.control,
                "_get_tapo_device",
                new=AsyncMock(side_effect=AssertionError("parent handle must not be used")),
            ) as get_device,
            patch.object(
                self.control,
                "_set_tapo_child_power_with_kasa_cli",
                new=AsyncMock(return_value="ok"),
            ) as set_child,
            patch.object(
                self.control,
                "_refresh_tapo_outlet_extender_state_with_kasa_cli",
                new=AsyncMock(return_value=verified),
            ) as refresh_child,
        ):
            result = asyncio.run(self.control.set_tapo_device(
                item["id"],
                "child_on",
                {
                    "child_id": "child-4",
                    "position": 4,
                    "child_index": 3,
                },
            ))

        get_device.assert_not_awaited()
        set_child.assert_awaited_once_with(item, "child-4", True)
        refresh_child.assert_awaited_once_with(item)
        self.assertTrue(result["device"]["children"][0]["is_on"])

    def test_extender_kasa_power_command_targets_stable_child_id(self):
        completed = types.SimpleNamespace(returncode=0, stdout="ok")

        with patch.object(
            self.control.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = asyncio.run(
                self.control._set_tapo_child_power_with_kasa_cli(
                    {"ip": "192.0.2.10"},
                    "child-4",
                    False,
                )
            )

        command = run.call_args.args[0]
        self.assertEqual(result, "ok")
        self.assertIn("--child", command)
        self.assertEqual(command[command.index("--child") + 1], "child-4")
        self.assertIn("off", command)
        self.assertNotIn("feature", command)
        self.assertNotIn("state", command)
        self.assertNotIn("--child-index", command)
        self.assertNotIn(self.control.TAPO_USERNAME, command)
        self.assertNotIn(self.control.TAPO_PASSWORD, command)
        self.assertEqual(
            self.control._redact_command_for_log(command)[
                command.index("--child") + 1
            ],
            "***",
        )

    def test_power_command_does_not_reconfigure_native_fade(self):
        item = {
            "id": "bulb",
            "ip": "192.0.2.20",
            "model": "L530",
            "device_type": "SMART.TAPOBULB",
            "kind": "bulb",
            "is_on": True,
        }
        confirmed = {
            **item,
            "control_ready": True,
            "control_error": "",
            "is_on": False,
        }
        handle = object()
        self.control._tapo_devices[item["id"]] = item

        with (
            patch.object(
                self.control,
                "_get_tapo_device",
                new=AsyncMock(return_value=handle),
            ),
            patch.object(
                self.control,
                "_set_tapo_power",
                new=AsyncMock(return_value=None),
            ) as set_power,
            patch.object(
                self.control,
                "_ensure_tapo_native_fade",
                new=AsyncMock(side_effect=AssertionError("fade setup must not run")),
            ) as ensure_fade,
            patch.object(
                self.control,
                "_enrich_control_state",
                new=AsyncMock(return_value=confirmed),
            ),
        ):
            result = asyncio.run(
                self.control.set_tapo_device(item["id"], "off")
            )

        ensure_fade.assert_not_awaited()
        set_power.assert_awaited_once_with(handle, False)
        self.assertFalse(result["device"]["is_on"])

    def test_extender_kasa_refresh_merges_metadata_and_live_power(self):
        item = {
            "id": "extender",
            "ip": "192.0.2.10",
            "model": "P306",
            "device_type": "SMART.TAPOPLUG",
            "kind": "outlet_extender",
            "children": [{
                "id": "child-4",
                "position": 4,
                "cli_index": 3,
                "alias": "Saved outlet name",
                "zone_name": "Kitchen",
                "is_on": False,
            }],
        }
        payload = {
            "child_device_list": [{
                "device_id": "child-4",
                "position": 4,
                "nickname": "Vendor outlet name",
                "device_on": True,
            }],
        }

        with patch.object(
            self.control,
            "_read_tapo_children_with_kasa_cli",
            new=AsyncMock(return_value=payload),
        ):
            refreshed = asyncio.run(
                self.control._refresh_tapo_outlet_extender_state_with_kasa_cli(item)
            )

        self.assertTrue(refreshed["control_ready"])
        self.assertTrue(refreshed["is_on"])
        self.assertEqual(refreshed["children"][0]["zone_name"], "Kitchen")
        self.assertTrue(refreshed["children"][0]["is_on"])

    def test_extender_child_command_rejects_unconfirmed_power_state(self):
        item = {
            "id": "extender",
            "ip": "192.0.2.10",
            "model": "P306",
            "device_type": "SMART.TAPOPLUG",
            "kind": "outlet_extender",
            "children": [{
                "id": "child-4",
                "position": 4,
                "cli_index": 3,
                "is_on": False,
            }],
        }
        self.control._tapo_devices[item["id"]] = item

        with (
            patch.object(
                self.control,
                "_set_tapo_child_power_with_kasa_cli",
                new=AsyncMock(return_value="ok"),
            ),
            patch.object(
                self.control,
                "_refresh_tapo_outlet_extender_state_with_kasa_cli",
                new=AsyncMock(return_value=item),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "did not change power state to on",
            ):
                asyncio.run(self.control.set_tapo_device(
                    item["id"],
                    "child_on",
                    {
                        "child_id": "child-4",
                        "position": 4,
                        "child_index": 3,
                    },
                ))

        self.assertFalse(item["children"][0]["is_on"])

    def test_routes_do_not_report_failed_commands_as_deferred_success(self):
        source = (TAPO_ROOT / "tapo_routes.py").read_text(encoding="utf-8")

        self.assertNotIn("tapo_defer_failed_state_command", source)
        self.assertNotIn("'deferred': True", source)
        self.assertNotIn("tapo_pending_power_commands", source)
        self.assertIn("'ok': failed_count == 0", source)

    def test_zone_and_scheme_batches_reject_any_partial_failure(self):
        source = (
            TAPO_ROOT / "static" / "js" / "tapo-actions.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const successfulTargets = results", source)
        self.assertIn(
            "throw failures[0]?.result?.reason || new Error(\"Tapo room command failed\")",
            source,
        )
        self.assertNotIn("if (failures.length >= targets.length)", source)
        self.assertNotIn("if (failedIDs.size >= results.length)", source)
        self.assertIn('alert(err?.message || "Tapo command failed.")', source)


if __name__ == "__main__":
    unittest.main()
