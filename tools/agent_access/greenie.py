"""Operator-only rootless Podman setup. No production share enters the container."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from tools.agent_access.releases import export_source

STATE = Path.home() / '.local/share/kotibot-development'
WORKSPACE = Path.home() / 'Projects/kotibot-development'
NAME = 'kotibot-development'
NETWORK = 'kotibot-development-private'
OUTSIDE = 'kotibot-development-proxy-out'
PROXY = 'kotibot-dev-proxy'
SELINUX_TYPE = 'container_userns_t'
SELINUX_BACKUP = NAME + '-before-selinux'
SELINUX_CANDIDATE = NAME + '-selinux-candidate'


def run(*args, **kwargs):
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True, timeout=900, **kwargs).stdout
    except subprocess.CalledProcessError as error:
        print('Failed command: ' + ' '.join(map(str, args)), file=sys.stderr)
        print((error.stdout or '') + (error.stderr or ''), file=sys.stderr)
        raise


def clean_environment():
    allowed = {'HOME', 'USER', 'LOGNAME', 'SHELL', 'PATH', 'LANG', 'LC_ALL',
               'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
               'XDG_SESSION_TYPE', 'XDG_DATA_DIRS', 'DBUS_SESSION_BUS_ADDRESS'}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                       GIT_TERMINAL_PROMPT='0')
    return environment


def podman(*args, **kwargs):
    return run('podman', *args, env=clean_environment(), **kwargs)


def inspect_configuration(name=NAME, *, legacy=False):
    container = json.loads(podman('inspect', name))[0]
    allowed = {str(WORKSPACE.resolve())}
    for mount in container['Mounts']:
        if mount['Type'] == 'bind' and mount['Source'] not in allowed:
            raise ValueError('Unexpected host bind mount; agent access is blocked')
        if mount['Type'] == 'volume' and mount.get('Name') != 'kotibot-development-home':
            raise ValueError('Unexpected host volume; agent access is blocked')
    if set(container['NetworkSettings']['Networks']) != {NETWORK}:
        raise ValueError('Development container has an unexpected network')
    network = json.loads(podman('network', 'inspect', NETWORK))[0]
    if not network.get('internal'):
        raise ValueError('Development network is not internal')
    if (container['HostConfig'].get('Privileged')
            or container['HostConfig'].get('PidMode') == 'host'
            or not container['HostConfig'].get('ReadonlyRootfs')
            or 'no-new-privileges' not in container['HostConfig'].get('SecurityOpt', [])):
        raise ValueError('Development container has host privileges')
    label = container.get('ProcessLabel', '').split(':', 3)
    permitted = {'container_t', SELINUX_TYPE} if legacy else {SELINUX_TYPE}
    if (len(label) != 4 or label[:2] != ['system_u', 'system_r']
            or label[2] not in permitted
            or not re.fullmatch(r's0:c\d+,c\d+', label[3])):
        raise ValueError('Unexpected SELinux container label; run repair-selinux for the original container_t setup')
    options = container['HostConfig'].get('SecurityOpt', [])
    if any(option in ('label=disable', 'seccomp=unconfined') for option in options):
        raise ValueError('Container security enforcement is disabled')
    return container


def container_inspection(*, codex=False, name=NAME):
    inspect_configuration(name)
    probe = Path(__file__).resolve().parents[2]/'deploy/agent-access/probe.py'
    extra = ['--codex'] if codex else []
    print(podman('exec', '-i', name, 'python', '-', *extra, input=probe.read_text()).strip())


def development_options(image='localhost/kotibot-development', *, level=None):
    options = ['--network', NETWORK,
               '--read-only', '--userns=keep-id:uid=1000,gid=1000', '--cap-drop=all',
               '--security-opt=no-new-privileges',
               '--security-opt=label=type:' + SELINUX_TYPE,
               '--http-proxy=false', '--tmpfs', '/tmp:rw,exec,nosuid',
               '--tmpfs', '/run:rw,nosuid',
               '-v', f'{WORKSPACE}:/workspace/kotibot:Z',
               '-v', 'kotibot-development-home:/home/developer']
    if level is not None:
        if not re.fullmatch(r's0:c\d+,c\d+', level):
            raise ValueError('Invalid SELinux category level')
        options.append('--security-opt=label=level:' + level)
    for variable in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy'):
        options.extend(['-e', variable + '=http://kotibot-dev-proxy:3128'])
    return options + ['-e', 'NO_PROXY=localhost,127.0.0.1', image]


def setup(source, head):
    if os.geteuid() == 0:
        raise ValueError('Run Greenie setup as your ordinary desktop user, without sudo')
    for tool in ('podman', 'code', 'git'):
        if not shutil.which(tool):
            raise ValueError('Required desktop tool is missing: ' + tool)
    if STATE.exists() or WORKSPACE.exists():
        raise ValueError('Development destination already exists; refusing replacement')
    info = json.loads(podman('info', '--format', 'json'))
    if info['host'].get('networkBackend') != 'netavark':
        raise ValueError('This setup requires the Netavark network backend')
    if not info['host']['security']['rootless']:
        raise ValueError('Rootless Podman is required')
    resources = [('container', NAME), ('container', PROXY), ('network', NETWORK),
                 ('network', OUTSIDE), ('volume', 'kotibot-development-home'),
                 ('image', 'localhost/kotibot-development'), ('image', 'localhost/kotibot-proxy')]
    for kind, name in resources:
        result = subprocess.run(['podman', kind, 'exists', name], capture_output=True,
                                env=clean_environment(), timeout=15)
        if result.returncode != 1:
            raise ValueError('A setup resource exists or could not be checked: ' + name)
    STATE.mkdir(parents=True, mode=0o700)
    print('Installing the separate VS Code container profile...', flush=True)
    configure_editor(clean_environment())
    WORKSPACE.parent.mkdir(parents=True, exist_ok=True)
    # A shallow fetch carries only current tracked source, no ignored residue or old history.
    environment = clean_environment()
    run('git', 'init', str(WORKSPACE), env=environment)
    run('git', '-C', str(WORKSPACE), 'remote', 'add', 'origin',
        'https://github.com/shift2076-creator/KotiBot.git', env=environment)
    run('git', '-C', str(WORKSPACE), 'fetch', '--depth=1', '--no-tags', 'origin', head, env=environment)
    run('git', '-C', str(WORKSPACE), 'checkout', '--detach', head, env=environment)
    for key in ('user.name', 'user.email'):
        configured = subprocess.run(['git', '-C', str(source), 'config', '--get', key],
                                    text=True, capture_output=True, timeout=15)
        if configured.returncode == 0 and configured.stdout.strip():
            run('git', '-C', str(WORKSPACE), 'config', key, configured.stdout.strip(), env=environment)
    # Trusted build context contains only selected source and this installation's helper files.
    with tempfile.TemporaryDirectory(prefix='kotibot-build-') as temporary:
        context = Path(temporary)
        export_source(source, head, context)
        shutil.copytree(source/'deploy/agent-access', context/'deploy/agent-access', dirs_exist_ok=True)
        for target in ('development', 'proxy'):
            print('Building isolated ' + target + ' image...', flush=True)
            podman('build', '--target', target, '-t', 'localhost/kotibot-' + target,
                   '-f', str(context/'deploy/agent-access/Containerfile'), str(context))
    podman('network', 'create', '--driver', 'bridge', '--internal', NETWORK)
    podman('network', 'create', OUTSIDE)
    podman('run', '-d', '--name', PROXY, '--network', OUTSIDE, '--network', NETWORK,
           '--read-only', '--tmpfs', '/tmp:rw,noexec,nosuid', '--cap-drop=all',
           '--security-opt=no-new-privileges', 'localhost/kotibot-proxy')
    podman('volume', 'create', 'kotibot-development-home')
    podman('run', '-d', '--name', NAME, *development_options())
    resume(source, head)


def verify_source_heads(source, head, name=NAME):
    if run('git', '-C', str(source), 'rev-parse', 'HEAD').strip() != head:
        raise ValueError('Operator source commit changed; stopped')
    if podman('exec', name, 'git', 'rev-parse', 'HEAD').strip() != head:
        raise ValueError('Development source commit changed; stopped')


def resume(source, head, *, name=NAME):
    verify_source_heads(source, head, name)
    wait_proxy(name)
    container_inspection(name=name)
    print('Running the full suite inside the isolated environment...', flush=True)
    print(podman('exec', name, 'python', '-m', 'tests').strip())
    print('Isolated full test suite: PASS')
    print(podman('exec', name, 'python', 'tools/path001d3_verify_source_boundary.py',
                 '--expected-head', head).strip())
    if podman('exec', name, 'git', 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Development source changed unexpectedly during preparation')
    if name == NAME:
        print('Development environment prepared. Open it, then run the post-attachment check before signing into Codex.')
    else:
        print('Replacement verification passed; preparing activation.', flush=True)


def require_absent_container(name):
    result = subprocess.run(['podman', 'container', 'exists', name], capture_output=True,
                            env=clean_environment(), timeout=15)
    if result.returncode != 1:
        raise ValueError('Recovery container already exists or could not be checked: ' + name)


def repair_selinux(source, head):
    """Test a replacement before activation; preserve the original and all volumes."""
    if os.geteuid() == 0:
        raise ValueError('Run on Greenie as your ordinary desktop user, without sudo')
    verify_source_heads(source, head)
    original = inspect_configuration(legacy=True)
    if original['ProcessLabel'].split(':', 3)[2] == SELINUX_TYPE:
        resume(source, head)
        return
    expected_mounts = {
        ('bind', str(WORKSPACE.resolve()), '/workspace/kotibot'),
        ('volume', 'kotibot-development-home', '/home/developer'),
    }
    mounts = {(mount['Type'], mount.get('Name') if mount['Type'] == 'volume' else mount.get('Source'),
               mount.get('Destination'))
              for mount in original['Mounts'] if mount['Type'] in ('bind', 'volume')}
    if mounts != expected_mounts:
        raise ValueError('Workspace/home mounts differ from the original setup; refusing reconstruction')
    for name in (SELINUX_BACKUP, SELINUX_CANDIDATE):
        require_absent_container(name)
    info = json.loads(podman('info', '--format', 'json'))
    if not info['host']['security']['rootless']:
        raise ValueError('Rootless Podman is required')
    original_id, image = original['Id'], original['Image']
    if not all(re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', value) for value in (original_id, image)):
        raise ValueError('Unexpected container/image identity')
    level = original['ProcessLabel'].split(':', 3)[3]
    print('Preparing replacement with the existing image, workspace, home and SELinux categories...', flush=True)
    candidate = podman('create', '--pull=never', '--name', SELINUX_CANDIDATE,
                       *development_options(image, level=level)).strip()
    if not re.fullmatch(r'[0-9a-f]{64}', candidate):
        raise ValueError('Could not identify the candidate; original container was not stopped')
    renamed = False
    try:
        podman('stop', original_id)
        podman('start', candidate)
        resume(source, head, name=SELINUX_CANDIDATE)
        podman('rename', original_id, SELINUX_BACKUP)
        renamed = True
        podman('rename', candidate, NAME)
    except BaseException:
        # No container, checkout, image or volume is deleted, including on failure.
        try:
            podman('stop', candidate)
            if renamed:
                podman('rename', original_id, NAME)
            podman('start', original_id)
            print('Repair failed; original development container restored. Candidate retained for inspection.',
                  file=sys.stderr)
        except Exception:
            print('Automatic container recovery needs attention; both containers and all data are retained.',
                  file=sys.stderr)
        raise
    print('SELinux repair verified. Original container retained as ' + SELINUX_BACKUP)
    print('Rollback: python3 tools/agent_development.py rollback-selinux')


def rollback_selinux():
    if os.geteuid() == 0:
        raise ValueError('Run on Greenie as your ordinary desktop user, without sudo')
    active = inspect_configuration()
    previous = inspect_configuration(SELINUX_BACKUP, legacy=True)
    if (previous['ProcessLabel'].split(':', 3)[2] != 'container_t'
            or previous['Image'] != active['Image']
            or previous['ProcessLabel'].split(':', 3)[3] != active['ProcessLabel'].split(':', 3)[3]):
        raise ValueError('Original container does not match the repaired container')
    require_absent_container(SELINUX_CANDIDATE)
    renamed = False
    restored_name = False
    try:
        podman('stop', active['Id'])
        podman('rename', active['Id'], SELINUX_CANDIDATE)
        renamed = True
        podman('rename', previous['Id'], NAME)
        restored_name = True
        podman('start', previous['Id'])
    except BaseException:
        try:
            if restored_name:
                podman('stop', previous['Id'])
                podman('rename', previous['Id'], SELINUX_BACKUP)
            if renamed:
                podman('rename', active['Id'], NAME)
            podman('start', active['Id'])
            print('Rollback failed; repaired container restored. Both containers retained.', file=sys.stderr)
        except Exception:
            print('Rollback recovery needs attention. Both containers and all data are retained; inspect podman ps -a.',
                  file=sys.stderr)
        raise
    print('Original container restored; repaired container retained as ' + SELINUX_CANDIDATE)
    print('Agent access remains blocked until the SELinux repair and boundary checks pass.')


def configure_editor(environment):
    profile = STATE/'profile'
    extensions = STATE/'extensions'
    run('code', '--user-data-dir', str(profile), '--extensions-dir', str(extensions),
        '--install-extension', 'ms-vscode-remote.remote-containers', env=environment)
    # Refuse versions without the controls on which credential isolation depends.
    manifests = list(extensions.glob('ms-vscode-remote.remote-containers-*/package.json'))
    if len(manifests) != 1:
        raise ValueError('Could not identify the installed Dev Containers extension')
    manifest = manifests[0].read_text()
    required = ('dev.containers.copyGitConfig', 'dev.containers.gitCredentialHelperConfigLocation')
    if not all(key in manifest for key in required):
        raise ValueError('Installed Dev Containers lacks required credential-isolation settings')
    settings = {'dev.containers.dockerPath': 'podman',
                'dev.containers.copyGitConfig': False,
                'dev.containers.gitCredentialHelperConfigLocation': 'none',
                'git.terminalAuthentication': False, 'git.autofetch': False,
                'terminal.integrated.env.linux': {'PATH':'/opt/tests/bin:/usr/local/bin:/usr/bin:/bin'},
                'extensions.autoUpdate': False, 'extensions.autoCheckUpdates': False}
    (profile/'User').mkdir(parents=True, exist_ok=True)
    (profile/'User/settings.json').write_text(json.dumps(settings, indent=2)+'\n')


def wait_proxy(name=NAME):
    code = 'import socket; socket.create_connection(("kotibot-dev-proxy",3128),timeout=1).close()'
    for attempt in range(20):
        try:
            podman('exec', name, 'python', '-c', code)
            return
        except subprocess.CalledProcessError:
            time.sleep(0.25)
    raise ValueError('Proxy did not become ready; inspect podman logs kotibot-dev-proxy')


def enable_codex():
    editor = ('import os; from pathlib import Path; '
              'paths=Path("/proc").glob("[0-9]*/cmdline"); '
              'assert any(b".vscode-server" in p.read_bytes() for p in paths '
              'if int(p.parent.name)!=os.getpid())')
    podman('exec', NAME, 'python', '-c', editor)
    # This is the operator process on Greenie, not a container/agent command.
    subprocess.run(['ssh', '-t', 'kotibot',
                    'cd /home/shift2076/kotibot && sudo python3 tools/path002_production.py verify'],
                   check=True)
    container_inspection()
    if list((STATE/'extensions').glob('openai.chatgpt-*')):
        raise ValueError('Codex is installed outside the container; do not sign in')
    print('Attached-editor boundary passed. In the attached VS Code terminal, run:')
    print('code --install-extension openai.chatgpt')
    print('Then on Greenie run: python3 tools/agent_development.py verify --codex')
    print('Sign in only after that verification passes.')


def open_editor():
    podman('start', PROXY, NAME)
    wait_proxy()
    container_inspection()
    authority = json.dumps({'containerName': '/' + NAME}, separators=(',', ':')).encode().hex()
    subprocess.Popen(['code', '--user-data-dir', str(STATE/'profile'), '--extensions-dir',
                      str(STATE/'extensions'), '--disable-extension', 'vscode.github-authentication',
                      '--new-window', '--folder-uri',
                      f'vscode-remote://attached-container+{authority}/workspace/kotibot'],
                     env=clean_environment())
