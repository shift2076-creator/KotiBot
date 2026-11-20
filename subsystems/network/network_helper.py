"""Root-owned host helper: applies a pair of port roles and goes back if the change is not confirmed in time.

Not installed anywhere yet, and nothing here runs by itself. A later step will run tick() from a systemd path or timer unit
and let the portal write the request and confirm files. All outside effects (commands, files, the clock, the "does the new
network work" check) are passed in, so the whole flow is tested without a Pi.

Files in the state directory (default /var/lib/kotibot-network):
- request.json   written by the portal: {"ethernet": ..., "wifi": ...}. Removed once handled.
- confirm        created by the portal when the admin still has a working session. Removed once handled.
- state.json     what the helper last applied, and the change waiting for confirmation (if any).
- result.json    what happened to the last request: {"status": "waiting" | "failed" | "confirmed" | "reverted", ...}.
"""
import json
import os
import sys
from pathlib import Path

import network_plan as plan_module

STATE_DIR = Path('/var/lib/kotibot-network')
DEFAULT_ROLES = (plan_module.OFF, plan_module.INTERNET)  # today's network: cable off, Wi-Fi is the internet port


class ApplyError(Exception):
    pass


def run_steps(steps, runner):
    """Run each step through runner(argv) -> exit code. A failing step stops the run unless the plan marked it tolerable."""
    for step in steps:
        code = runner(list(step.argv))
        if code != 0 and not step.tolerate:
            raise ApplyError('command failed (%s): %s' % (code, ' '.join(step.argv)))


def apply_roles(ethernet, wifi, *, runner, write_file, remove_file, check, identity=False):
    """Bring a pair of roles up. The old setup is removed only after check() says the new one works."""
    plan = plan_module.plan(ethernet, wifi, identity=identity)
    if plan.error:
        raise ApplyError(plan.error)
    run_steps(plan.up, runner)
    run_steps(plan.firewall, runner)
    for path, content in plan.files.items():
        if content is None:
            remove_file(path)
        else:
            write_file(path, content)
    if not check():
        raise ApplyError('the new setup did not come up, so the old one was kept')
    run_steps(plan.down, runner)


def _read(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = Path(str(path) + '.new')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, path)


def tick(state_dir, now, *, runner, write_file, remove_file, check, identity=False):
    """One pass: handle a new request, a confirmation, and an expired change, in that order. Returns result.json's content or None."""
    state_dir = Path(state_dir)
    state_path, result_path = state_dir / 'state.json', state_dir / 'result.json'
    request_path, confirm_path = state_dir / 'request.json', state_dir / 'confirm'
    state = _read(state_path, {'current': list(DEFAULT_ROLES), 'change': None})
    result = None

    def apply(roles):
        apply_roles(roles[0], roles[1], runner=runner, write_file=write_file, remove_file=remove_file,
                    check=check, identity=identity)

    if request_path.exists():
        request = _read(request_path, {})
        request_path.unlink()
        requested = (request.get('ethernet'), request.get('wifi'))
        previous = tuple(state['current'])
        problem = plan_module.unsupported(*requested)
        if problem is None and state['change'] is None:
            try:
                apply(requested)
            except ApplyError as error:
                problem = str(error)
                try:
                    apply(previous)  # put the last good setup back
                except ApplyError:
                    problem += ' The previous setup could not be restored either.'
        elif problem is None:
            problem = 'A change is already waiting for confirmation.'
        if problem is None:
            state['current'] = list(requested)
            state['change'] = plan_module.begin_change(previous, requested, now)
            result = {'status': 'waiting', 'deadline': state['change']['deadline']}
        else:
            result = {'status': 'failed', 'error': problem}

    if confirm_path.exists():
        confirm_path.unlink()
        if state['change'] is not None:
            state['change'] = None
            result = {'status': 'confirmed'}

    if state['change'] is not None and plan_module.must_revert(state['change'], now):
        target = plan_module.revert_target(state['change'])
        try:
            apply(target)
            state['current'] = list(target)
            state['change'] = None
            result = {'status': 'reverted', 'roles': list(target)}
        except ApplyError as error:
            result = {'status': 'failed', 'error': 'Could not go back: ' + str(error)}

    _write(state_path, state)
    if result is not None:
        _write(result_path, result)
    return result


def main():  # pragma: no cover - the real entry point, run as root by a unit that does not exist yet
    import subprocess
    import time
    from datetime import datetime

    def runner(argv):
        return subprocess.run(argv, capture_output=True, text=True, timeout=60).returncode

    def write_file(path, content):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)

    def remove_file(path):
        Path(path).unlink(missing_ok=True)

    def check():
        # The Pi must answer on the identity address again, as the owner will use it.
        return subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'to', plan_module.IDENTITY_ADDRESS],
                              capture_output=True, text=True).stdout.strip() != ''

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    result = tick(STATE_DIR, time.time(), runner=runner, write_file=write_file, remove_file=remove_file, check=check, identity=True)
    if result:
        print(datetime.now().isoformat(timespec='seconds'), json.dumps(result))


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
