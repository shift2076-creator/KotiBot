import unittest
from unittest.mock import MagicMock, patch

from subsystems.bluetooth import bluetooth_routes as routes


class ScanCommandTests(unittest.TestCase):
    """A bare `bluetoothctl scan on` exits at once in BlueZ 5.82 and stops discovery."""

    def test_pairing_scan_runs_with_a_timeout_so_it_stays_alive(self):
        proc = MagicMock()
        proc.poll.return_value = None
        routes.BLUETOOTH_PAIR_SCAN_PROC = None
        with patch.object(routes.shutil, "which", return_value="/usr/bin/bluetoothctl"), \
                patch.object(routes.subprocess, "Popen", return_value=proc) as popen, \
                patch.object(routes.time, "sleep"):
            result = routes._start_bluetooth_pairing_scan()
        routes.BLUETOOTH_PAIR_SCAN_PROC = None
        self.assertTrue(result["ok"])
        self.assertEqual(
            popen.call_args.args[0],
            ["bluetoothctl", "--timeout", str(routes.BLUETOOTH_PAIR_SCAN_SECONDS), "scan", "on"],
        )

    def test_timed_scan_runs_longer_than_the_wait_so_it_is_stopped_by_us(self):
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = -15
        with patch.object(routes.shutil, "which", return_value="/usr/bin/bluetoothctl"), \
                patch.object(routes.subprocess, "Popen", return_value=proc) as popen, \
                patch.object(routes.time, "sleep") as sleep:
            routes._scan_bluetoothctl(8)
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], ["bluetoothctl", "--timeout"])
        self.assertEqual(command[-2:], ["scan", "on"])
        self.assertGreater(int(command[2]), 8)
        sleep.assert_called_once_with(8)
        proc.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
