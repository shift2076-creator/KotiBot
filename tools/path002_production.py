#!/usr/bin/env python3
"""Root-owned KotiBot releases. Run as root on KotiBot, never inside the agent."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from tools.agent_access.releases import command, copy_environment, export_source, freeze, root_owned
from tools.path003_cleanup_source_residue import _read_process_path_environment, runtime_paths_for_service
from tools.sec007_verify_virtualenv_credentials import audit_virtualenv

SERVICE = 'kotibot.service'
BASE = Path('/opt/kotibot')
DROPIN = Path('/etc/systemd/system/kotibot.service.d/zzz-path002-source.conf')


def prop(name):
    return command('systemctl', 'show', SERVICE, '--value', '--property', name).decode().strip()


def atomic(path, payload):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o644)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def configuration(release):
    return (f'[Service]\nWorkingDirectory={release}\nExecStart=\n'
            f'ExecStart={release}/.venv/bin/python -m waitress '
            '--listen=0.0.0.0:5000 --threads=12 wsgi:application\n'
            'Environment=PYTHONDONTWRITEBYTECODE=1\n').encode()


def service_paths(root, user):
    pid = int(prop('MainPID'))
    if pid <= 0 or prop('ActiveState') != 'active':
        raise ValueError('KotiBot service is not active')
    environment = _read_process_path_environment(pid)
    paths = runtime_paths_for_service(root, process_user_id=user.pw_uid, environment=environment)
    return {key: str(value) for key, value in paths.resolved_runtime_destinations().items()}


def validate_original():
    if Path(prop('WorkingDirectory')) != SOURCE:
        raise ValueError('Active service is not using the expected original checkout')
    user = pwd.getpwnam(prop('User'))
    if user.pw_uid == 0:
        raise ValueError('Production must use a non-root service identity')
    expected = f'{SOURCE}/.venv/bin/python'
    start = prop('ExecStart')
    if (f'path={expected} ;' not in start or f'argv[]={expected} -m waitress '
            '--listen=0.0.0.0:5000 --threads=12 wsgi:application ;' not in start):
        raise ValueError('Service command differs from the verified 12-worker deployment')
    return user, service_paths(SOURCE, user)


def verify(release, record):
    if DROPIN.read_bytes() != configuration(release):
        raise ValueError('Deployment drop-in differs')
    if Path(prop('WorkingDirectory')) != release:
        raise ValueError('Effective service source differs')
    user = pwd.getpwnam(record['user'])
    if prop('User') != user.pw_name:
        raise ValueError('Service identity changed')
    pid = int(prop('MainPID'))
    actual_command = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    expected_command = [str(release/'.venv/bin/python').encode(), b'-m', b'waitress',
                        b'--listen=0.0.0.0:5000', b'--threads=12', b'wsgi:application']
    if actual_command != expected_command:
        raise ValueError('Running service is not using the selected production interpreter')
    if Path(f'/proc/{pid}/cwd').resolve() != release:
        raise ValueError('Running service still executes from another checkout')
    if service_paths(release, user) != record['runtime_paths']:
        raise ValueError('Runtime destinations changed during deployment')
    root_owned(release)
    probe = ('import os,sys; from pathlib import Path; '
             'root=Path(sys.argv[1]); '
             'paths=[root]+list(root.rglob("*")); '
             'bad=[p for p in paths if os.access(p,os.W_OK)]; '
             'raise SystemExit(bool(bad))')
    command('runuser', '-u', user.pw_name, '--', '/usr/bin/python3', '-I', '-c', probe, str(release))
    print('PATH-002 PASS: separate production source; service writes denied; runtime paths unchanged.')


def install(head):
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise ValueError('An exact commit is required')
    if DROPIN.is_symlink():
        raise ValueError('Refusing a symbolic-link service drop-in')
    previous = None
    record_path = BASE / 'deployment.json'
    if DROPIN.exists():
        root_owned(record_path)
        previous = json.loads(record_path.read_text())
        verify(BASE / 'releases' / previous['head'], previous)
        user = pwd.getpwnam(previous['user'])
        runtime_paths = previous['runtime_paths']
    else:
        user, runtime_paths = validate_original()
        if record_path.exists():
            raise ValueError('Recovery record exists without its deployment; inspect before retrying')
    root_owned(DROPIN.parent)
    BASE.mkdir(mode=0o755, exist_ok=True)
    root_owned(BASE)
    releases = BASE / 'releases'
    releases.mkdir(mode=0o755, exist_ok=True)
    root_owned(releases)
    release = releases / head
    if release.exists() or release.is_symlink():
        raise ValueError('Release destination exists; it will not be overwritten')
    record = {'head': head, 'user': user.pw_name, 'source': str(SOURCE),
              'runtime_paths': runtime_paths, 'previous': previous}
    # Leave incomplete copies intact on failure for operator inspection, never replace them.
    release.mkdir(mode=0o700)
    export_source(SOURCE, head, release)
    environment_source = BASE / 'releases' / previous['head'] if previous else SOURCE
    if (release/'requirements.txt').read_bytes() != (environment_source/'requirements.txt').read_bytes():
        raise ValueError('Dependency requirements changed; a reviewed environment update is required')
    copy_environment(environment_source / '.venv', release / '.venv')
    freeze(release)
    audit = audit_virtualenv(release / '.venv', Path('/etc/kotibot/credentials.d'), expected_credential_uid=0)
    if audit.contaminated:
        raise ValueError('Copied Python environment failed the value-free credential audit')
    check = ('import sys; from pathlib import Path; root=Path(sys.argv[1]); '
             'assert Path(sys.prefix)==root/".venv"; '
             'assert not any(Path(p).is_relative_to(Path(sys.argv[2])) for p in sys.path if p); '
             'import flask,waitress; '
             'assert Path(flask.__file__).is_relative_to(root); '
             'assert Path(waitress.__file__).is_relative_to(root)')
    command('runuser', '-u', user.pw_name, '--', str(release / '.venv/bin/python'),
            '-I', '-c', check, str(release), str(SOURCE))
    previous_configuration = configuration(BASE/'releases'/previous['head']) if previous else None
    if record_path.is_symlink():
        raise ValueError('Recovery record cannot be a symbolic link')
    changed = False
    try:
        if previous:
            if DROPIN.read_bytes() != previous_configuration:
                raise ValueError('Deployment changed during preparation')
            atomic(DROPIN, configuration(release))
        else:
            with DROPIN.open('xb') as stream:
                stream.write(configuration(release))
            DROPIN.chmod(0o644)
        changed = True
        atomic(record_path, json.dumps(record, indent=2).encode())
        command('systemctl', 'daemon-reload')
        command('systemctl', 'restart', SERVICE)
        time.sleep(2)
        verify(release, record)
    except BaseException:
        if changed and DROPIN.exists() and DROPIN.read_bytes() == configuration(release):
            if previous_configuration:
                atomic(DROPIN, previous_configuration)
                atomic(record_path, json.dumps(previous).encode())
            else:
                DROPIN.unlink()
                record_path.unlink(missing_ok=True)
            command('systemctl', 'daemon-reload')
            command('systemctl', 'restart', SERVICE)
        raise
    print('Recovery: original checkout and Python environment retained; rollback is available.')


def rollback(record):
    release = BASE / 'releases' / record['head']
    if DROPIN.is_symlink() or DROPIN.read_bytes() != configuration(release):
        raise ValueError('Drop-in changed; refusing rollback')
    if Path(record['source']) != SOURCE:
        raise ValueError('Run rollback from the original operator checkout')
    previous = record.get('previous')
    if previous:
        atomic(DROPIN, configuration(BASE/'releases'/previous['head']))
    else:
        DROPIN.unlink()
    try:
        command('systemctl', 'daemon-reload')
        command('systemctl', 'restart', SERVICE)
        if previous:
            verify(BASE/'releases'/previous['head'], previous)
        else:
            user, paths = validate_original()
            if paths != record['runtime_paths'] or user.pw_name != record['user']:
                raise ValueError('Original service recovery verification failed')
    except BaseException:
        atomic(DROPIN, configuration(release))
        command('systemctl', 'daemon-reload')
        command('systemctl', 'restart', SERVICE)
        raise
    if previous:
        atomic(BASE/'deployment.json', json.dumps(previous).encode())
    else:
        (BASE/'deployment.json').unlink()
    print('Previous service restored. Release files remain available for recovery.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'verify', 'rollback'))
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Run this operator tool with sudo on KotiBot')
    if args.action == 'install':
        install(args.expected_head or '')
    else:
        root_owned(BASE / 'deployment.json')
        record = json.loads((BASE / 'deployment.json').read_text())
        if args.action == 'rollback':
            rollback(record)
        else:
            verify(BASE / 'releases' / record['head'], record)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'PATH-002 stopped: {type(error).__name__}. No credential values displayed.', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(f'Command failed: {error.cmd[0]} (exit {error.returncode})', file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        raise SystemExit(1)
