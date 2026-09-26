"""Install/remove the A06 stream limit on the verified 12-worker Linux service.

Run on the KotiBot server with sudo. Never prints service environment values.
An existing different drop-in is refused; existing service files are untouched.
"""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


SERVICE = 'kotibot.service'
NAME = 'zz-status-stream-capacity.conf'
CONTENTS = (
    '# Requires the verified Waitress --threads=12 service command.\n'
    '# Eight status streams leave four request workers for controls and telemetry.\n'
    '[Service]\n'
    'Environment=KOTIBOT_STATUS_STREAM_LIMIT=8\n'
).encode()


def property_value(name):
    return subprocess.run(
        ['systemctl', 'show', SERVICE, '--value', '--property', name],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def validate_command(command):
    if ' -m waitress ' not in command:
        raise ValueError('Expected the verified python -m waitress service command')
    values = re.findall(r'(?:^|\s)--threads(?:=|\s+)(\d+)(?=\s|;|$)', command)
    if values != ['12']:
        raise ValueError('Expected exactly one Waitress --threads=12 setting')


def install_dropin(directory):
    target = directory / NAME
    if directory.is_symlink() or target.is_symlink():
        raise ValueError('Refusing a symlink service drop-in path')
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or target.read_bytes() != CONTENTS:
            raise ValueError('Existing capacity drop-in differs; no configuration changed')
        return False
    # Publish atomically and refuse an unexpected file created concurrently.
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(CONTENTS)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o644)
            os.link(temporary, target)
        finally:
            temporary.unlink()
    return True


def remove_dropin(directory):
    target = directory / NAME
    if directory.is_symlink() or target.is_symlink():
        raise ValueError('Refusing a symlink service drop-in path')
    if not target.exists():
        return
    if target.read_bytes() != CONTENTS:
        raise ValueError('Capacity drop-in changed; refusing to remove it')
    target.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove', action='store_true', help='Restore the prior absence of this drop-in')
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Run this deployment helper with sudo on the KotiBot Linux server')
    directory = Path('/etc/systemd/system/kotibot.service.d')
    if args.remove:
        remove_dropin(directory)
    else:
        root = Path(__file__).resolve().parents[1]
        if Path(property_value('WorkingDirectory')).resolve() != root:
            raise ValueError('Service working directory differs from this source checkout')
        validate_command(property_value('ExecStart'))
        source = root / 'deploy/systemd/kotibot.service.d' / NAME
        if source.read_bytes() != CONTENTS:
            raise ValueError('Packaged capacity configuration differs')
        created = install_dropin(directory)
        try:
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            settings = [item for item in shlex.split(property_value('Environment'))
                        if item.startswith('KOTIBOT_STATUS_STREAM_LIMIT=')]
            if settings != ['KOTIBOT_STATUS_STREAM_LIMIT=8']:
                raise ValueError('Another service setting overrides the stream limit')
        except BaseException:
            if created:
                remove_dropin(directory)
                subprocess.run(['systemctl', 'daemon-reload'], check=True)
            raise
        print('Verified: 12 request workers; 8 status stream slots. Restart KotiBot to activate.')
        return
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Capacity drop-in removed. Restart KotiBot to activate the source default.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Capacity configuration stopped: {error}') from None
