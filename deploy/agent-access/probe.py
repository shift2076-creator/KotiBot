"""Value-free denial checks, run inside the actual development container."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def check(condition, label):
    if not condition:
        raise SystemExit('AGENT boundary BLOCKED: ' + label)
    print('PASS: ' + label)


def denied(path):
    for flags in (os.O_RDONLY, os.O_WRONLY):
        try:
            fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
        else:
            os.close(fd)
            return False
    return True


def proc_mount_denied(stderr):
    return ("Can't mount proc" in stderr
            and ('/newroot/proc' in stderr or 'on /proc:' in stderr)
            and any(reason in stderr for reason in
                    ('Permission denied', 'Operation not permitted', 'Invalid argument')))


def nested_sandbox(root):
    args = ['bwrap', '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-net',
         '--cap-drop', 'ALL',
         '--die-with-parent', '--ro-bind', '/', '/', '--proc', '/proc',
         '--dev', '/dev', '--tmpfs', '/tmp', '--bind', str(root), str(root),
         '--chdir', str(root), '/opt/tests/bin/python', '-c',
         'import os; from pathlib import Path; '
         'p=Path(".sandbox-write-probe-"+str(os.getpid())); '
         'p.open("x").close(); p.unlink(); '
         'assert not os.access("/etc", os.W_OK); '
         'assert not os.access(Path.home(), os.W_OK)']
    sandbox = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if sandbox.returncode and proc_mount_denied(sandbox.stderr):
        index = args.index('--proc')
        del args[index:index + 2]
        sandbox = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if sandbox.returncode == 0:
            print('PASS: nested sandbox retains container procfs; namespaces/capability limits preserved')
    if sandbox.returncode:
        raise SystemExit('AGENT boundary BLOCKED: nested bubblewrap sandbox failed. '
                         'This check does not change production. '
                         'Keep protections enabled; report: ' + sandbox.stderr.strip())
    print('PASS: nested Linux sandbox starts and permits workspace writes')


def main():
    check(os.getuid() == 1000 and os.getgroups() in ([1000], []), 'separate non-service container identity')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    check(all(int(status[key].strip(), 16) == 0 for key in ('CapEff', 'CapPrm', 'CapBnd')),
          'all Linux capabilities dropped')
    check(status['NoNewPrivs'].strip() == '1', 'privilege escalation disabled')
    for label, path in {
        'production source share': '/var/mnt/kotibot/kotibot_server.py',
        'production install': '/opt/kotibot/deployment.json',
        'operator SSH credentials': '/var/home/snx/.ssh',
        'operator home': '/home/snx',
        'server identity': '/home/shift2076',
        'credentials': '/etc/kotibot/credentials.d',
        'authentication and Matter state': '/home/shift2076/.local/share/kotibot/protected',
        'private history and media': '/home/shift2076/.local/share/kotibot',
        'recovery copies': '/var/home/snx/kotibot-backups',
        'system service bus': '/run/dbus/system_bus_socket',
        'host container control': '/run/user/1000/podman/podman.sock',
    }.items():
        check(denied(path), label + ' read/write denied')
    check(not os.environ.get('SSH_AUTH_SOCK'), 'no forwarded SSH agent')
    for process in Path('/proc').glob('[0-9]*/environ'):
        try:
            entries = process.read_bytes().split(b'\0')
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
        check(not any(entry.startswith(b'SSH_AUTH_SOCK=') and entry != b'SSH_AUTH_SOCK='
                      for entry in entries), 'no SSH forwarding in running editor processes')
    check(not any(k.startswith(('KOTIBOT_', 'TAPO_')) or k == 'CREDENTIALS_DIRECTORY'
                  for k in os.environ), 'no inherited production environment')
    for path in (Path.home()/'.ssh', Path.home()/'.git-credentials'):
        check(not path.exists(), 'no developer copy of host authentication')
    helpers = subprocess.run(['git', 'config', '--get-all', 'credential.helper'],
                             capture_output=True, text=True)
    check(helpers.returncode in (0, 1) and not helpers.stdout.strip(), 'no forwarded Git credential helper')
    for host, port in [('192.168.4.45', 22), ('192.168.4.45', 5000), ('1.1.1.1', 443)]:
        try:
            connection = socket.create_connection((host, port), timeout=1)
        except OSError:
            pass
        else:
            connection.close()
            raise SystemExit('AGENT boundary BLOCKED: direct network access')
    print('PASS: direct LAN and Internet connections denied')
    for destination in ('kotibot.app', 'github.com', '192.168.4.45'):
        with socket.create_connection(('kotibot-dev-proxy', 3128), timeout=5) as proxy:
            proxy.sendall(f'CONNECT {destination}:443 HTTP/1.1\r\nHost: {destination}:443\r\n\r\n'.encode())
            check(b' 403 ' in proxy.recv(256).split(b'\r\n')[0], 'production/publication proxy route denied')
    root = Path('/workspace/kotibot')
    marker = root / ('.agent-write-probe-' + str(os.getpid()))
    with marker.open('x') as stream:
        stream.write('source permission check')
    check(marker.read_text() == 'source permission check', 'actual source read/write succeeds')
    marker.unlink()
    check(Path('/opt/tests/bin/python').is_file(), 'isolated test Python available')
    nested_sandbox(root)
    if '--codex' in sys.argv:
        check(bool(list((Path.home()/'.vscode-server/extensions').glob('openai.chatgpt-*/package.json'))),
              'Codex extension installed inside the container')
    print('AGENT DENIAL MATRIX: PASS')


if __name__ == '__main__':
    main()
