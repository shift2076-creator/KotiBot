import unittest
from unittest import mock

from server_core import restart


class RestartServiceTests(unittest.TestCase):
    def test_container_without_systemd_exits_so_docker_restarts_it(self):
        flushed = []

        with mock.patch.object(restart.os, "name", "posix"), \
                mock.patch.object(restart.shutil, "which", return_value=None), \
                mock.patch.object(restart.subprocess, "Popen") as popen, \
                mock.patch.object(restart.os, "_exit", side_effect=SystemExit) as exit_:
            with self.assertRaises(SystemExit):
                restart.restart_service("/app", lambda: flushed.append(True))

        self.assertEqual(flushed, [True])
        exit_.assert_called_once_with(0)
        popen.assert_not_called()

    def test_host_with_systemd_restarts_the_unit(self):
        with mock.patch.object(restart.os, "name", "posix"), \
                mock.patch.object(restart.shutil, "which", return_value="/bin/systemctl"), \
                mock.patch.object(restart.subprocess, "Popen") as popen, \
                mock.patch.object(restart.os, "_exit") as exit_:
            restart.restart_service("/app", lambda: None)

        self.assertEqual(
            popen.call_args.args[0],
            ["sudo", "systemctl", "restart", "kotibot"],
        )
        exit_.assert_not_called()


if __name__ == "__main__":
    unittest.main()
