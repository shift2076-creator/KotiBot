"""Local execution proof streamed through the installed Codex command runner."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


def git(*args):
    return subprocess.run(['git', *args], check=True, text=True, capture_output=True).stdout.strip()


def main():
    root = Path('/workspace/kotibot')
    # Read the standing rules before running any project verification commands.
    if not (root / 'AGENTS.md').read_text().strip():
        raise RuntimeError('AGENTS.md is empty')
    if Path.cwd() != root:
        raise RuntimeError('Unexpected working directory')
    expected = sys.argv[1]
    boundary = sys.argv[2] if len(sys.argv) > 2 else 'nested'
    if boundary not in ('nested', 'container'):
        raise RuntimeError('Unknown development boundary')
    head = git('rev-parse', 'HEAD')
    if head != expected:
        raise RuntimeError('Development HEAD changed')
    if git('status', '--porcelain', '--untracked-files=all'):
        raise RuntimeError('Development checkout is not clean')
    print('Codex command working directory:', root, flush=True)
    print('Codex command Git HEAD:', head, flush=True)
    print('Initial Git status: clean', flush=True)

    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if os.getuid() != 1000 or any(int(status[key].strip(), 16) for key in ('CapEff', 'CapPrm', 'CapBnd')):
        raise RuntimeError('Unexpected sandbox identity or capabilities')
    if status['NoNewPrivs'].strip() != '1' or status['Seccomp'].strip() != '2':
        raise RuntimeError('Sandbox process restrictions missing')
    if not os.statvfs('/').f_flag & os.ST_RDONLY or os.access('/etc', os.W_OK):
        raise RuntimeError('Container system filesystem is writable')
    if boundary == 'nested':
        mask = Path('/tmp/codex-daemon-1000')
        if stat.S_IMODE(mask.stat().st_mode) != 0 or not os.statvfs(mask).f_flag & os.ST_RDONLY:
            raise RuntimeError('Codex daemon directory is not masked read-only with mode 000')
        if os.access(Path.home(), os.W_OK):
            raise RuntimeError('Unexpected writes outside the workspace')
    with tempfile.NamedTemporaryFile(prefix='.codex-sandbox-check-', dir=root, mode='w+') as stream:
        stream.write('temporary workspace verification\n')
        stream.flush()
        stream.seek(0)
        if stream.read() != 'temporary workspace verification\n':
            raise RuntimeError('Workspace read/write check failed')
    print('PASS: actual Codex command; boundary=' + boundary + '; temporary workspace write/delete', flush=True)
    print('Running the full suite through the actual Codex command runner...', flush=True)
    subprocess.run(['/opt/tests/bin/python', '-m', 'tests'], check=True)
    subprocess.run(['/opt/tests/bin/python', 'tools/path001d3_verify_source_boundary.py',
                    '--expected-head', expected], check=True)
    if git('rev-parse', 'HEAD') != head or git('status', '--porcelain', '--untracked-files=all'):
        raise RuntimeError('Development checkout changed during verification')
    print('Final Git status: clean', flush=True)
    print('ACTUAL CODEX SANDBOX AND FULL SUITE: PASS' if boundary == 'nested'
          else 'ACTUAL CODEX COMMAND AND FULL SUITE: PASS', flush=True)


if __name__ == '__main__':
    main()
