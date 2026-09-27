#!/usr/bin/env python3
"""Prepare, open and verify isolated KotiBot development on Greenie."""
import argparse
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.agent_access.greenie import (container_inspection, enable_codex, open_editor,
                                      setup, resume, repair_selinux, rollback_selinux,
                                      repair_bubblewrap, rollback_bubblewrap, codex_sandbox_check,
                                      launch_codex)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'resume', 'repair-selinux',
                                         'rollback-selinux', 'repair-bubblewrap',
                                         'rollback-bubblewrap', 'check-codex', 'codex', 'open', 'verify', 'enable'))
    parser.add_argument('--expected-head')
    parser.add_argument('--codex', action='store_true', help='Verify the installed remote Codex extension')
    parser.add_argument('--image', help='Exact tested replacement image ID')
    parser.add_argument('--expected-image', help='Exact original image ID used to build the candidate')
    args = parser.parse_args()
    if args.action in ('setup', 'resume', 'repair-selinux'):
        if not args.expected_head:
            raise ValueError('The exact source commit is required')
        {'setup': setup, 'resume': resume, 'repair-selinux': repair_selinux}[args.action](ROOT, args.expected_head)
    elif args.action == 'repair-bubblewrap':
        if not all((args.expected_head, args.image, args.expected_image)):
            raise ValueError('Expected source commit, original image and candidate image IDs are required')
        repair_bubblewrap(ROOT, args.expected_head, args.image, args.expected_image)
    elif args.action == 'rollback-bubblewrap':
        rollback_bubblewrap()
    elif args.action == 'check-codex':
        codex_sandbox_check(expected_head=args.expected_head, boundary='container')
    elif args.action == 'codex':
        launch_codex()
    elif args.action == 'rollback-selinux':
        rollback_selinux()
    elif args.action == 'open':
        open_editor()
    elif args.action == 'enable':
        enable_codex()
    else:
        container_inspection(codex=args.codex, boundary='container')
        print('Container boundary verification passed. Run check-codex for actual Codex command execution and the full suite.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Development setup stopped: {type(error).__name__}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(f'Command failed: {error.cmd[0]} (exit {error.returncode})', file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        raise SystemExit(1)
