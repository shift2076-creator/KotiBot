import os
import shutil
import subprocess
import sys


def restart_service(base_dir, flush):
    """Restart KotiBot after flushing pending writes.

    Windows relaunches itself. Where systemd exists the service is restarted.
    Without systemd (the PiVault container) the process exits and the
    container's restart policy brings it back.
    """
    flush()

    if os.name == 'nt':
        subprocess.Popen([sys.executable] + sys.argv, cwd=str(base_dir))
        os._exit(0)

    if shutil.which('systemctl') is None:
        os._exit(0)

    subprocess.Popen(
        ['sudo', 'systemctl', 'restart', 'kotibot'],
        cwd=str(base_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
