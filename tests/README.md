# KotiBot tests

Twelve suites, grouped by responsibility. Each suite contains focused modules
and individually selectable test cases. The suite names are the everyday entry
points; keeping the individual cases gives failures useful, precise names.

Run commands from the repository root, with Python 3.11 or newer.

## Setup

Use an isolated test environment outside the checkout on Greenie:

```bash
cd /var/mnt/kotibot
python3 -m venv "$HOME/.local/share/kotibot-test-venv"
source "$HOME/.local/share/kotibot-test-venv/bin/activate"
python -m pip install -r tests/requirements.txt
```

If the environment already exists, activate it and install the test requirements;
do not recreate it.
The application service does not need to be running or restarted.
The status-capacity test starts an isolated Waitress server on an ephemeral
loopback port. Waitress is included in `tests/requirements.txt`; the test never
connects to the deployed KotiBot service or devices.

Scene browser-logic tests execute JavaScript with Node.js 18 or newer:

```bash
node --test tests/dashboard/interface/scene_reliability.test.js
```

These eight tests are separate from the Python runner. They exercise the actual
Scene submission/queue/status functions with controlled HTTP and DOM fixtures.
The Python suite also sends 15 Scene requests through a real local Waitress
server with eight status feeds open and simulated devices; this does not prove
physical bulb behavior or browser rendering on the deployed host.

Scene dispatch regression tests also verify one combined color-bulb write,
12 concurrently pending device writes, independence from busy/offline devices,
per-device cold authentication, no application replay, HTTP click sequencing,
power-preserving presets, cached metadata, client replacement and desired state.
Run `python -m tests devices.tapo.test_tapo_scene_dispatch` for this contract.
The browser tests include overlapping selections and plain-LAN-HTTP support.
These tests use controlled devices; physical response and Pi/Windows behavior
still require deployment checks. Slow Scene requests emit numeric timing only.

## Choose what to run

| Scope | Command |
| --- | --- |
| Show the 12 suites and counts | `python -m tests --list` |
| Full suite | `python -m tests` |
| One category | `python -m tests devices` |
| One suite | `python -m tests devices.matter` |
| One module | `python -m tests devices.matter.test_matter_reliability` |
| One test, selected by name | `python -m tests devices.matter -k fresh_sibling -v` |
| List individual test IDs in a suite | `python -m tests devices.matter --list` |

To run a listed case exactly, append its dotted ID to `python -m tests`.
For example:

```bash
python -m tests devices.matter.test_matter_reliability.MatterColdStartTests.test_fresh_sibling_does_not_make_unknown_or_unreachable_endpoint_live -v
```

`-v` shows each case. `-f` stops after the first failure. `-k` accepts a name
substring or a quoted wildcard pattern. A misspelled selector, an empty match,
an import error, or missing test dependencies returns a nonzero exit code.
Dependency checks prevent the old missing-Flask skips from hiding an incomplete
test setup. Any platform-specific unittest skips remain visible in the result.

## Categories and suites

| Category | Suite | Coverage |
| --- | --- | --- |
| Security | `security.access` | Route protection, signing policy, origins, trusted hosts, markup policy |
| Security | `security.credentials` | Protected credential readers and application integration contracts |
| Security | `security.privacy` | Audit output, notification history, status and dashboard data sanitization |
| Devices | `devices.android` | Roles, signed uploads, key-client sessions, re-enrollment and key handoff |
| Devices | `devices.matter` | Startup state, freshness, subscriptions, event delivery and protected storage wiring |
| Devices | `devices.tapo` | Command integrity, persistence, streams and preview lifecycle |
| Dashboard | `dashboard.interface` | Metadata editing/rendering, camera talk, recording indicators and navigation |
| Dashboard | `dashboard.accounts` | Account UI, sessions, provenance and dashboard credential rotation |
| Storage | `storage.state` | Typed reads, atomic writes, recovery copies, private permissions and authentication state |
| Storage | `storage.paths` | External runtime roots for cache, media, notifications, packages and temporary files |
| Maintenance | `maintenance.migrations` | Retained migration/cutover tools and their rejection/recovery paths |
| Maintenance | `maintenance.cleanup` | Source-write detection, cleanup, credential maintenance, inventories and test runner |

Migration-tool tests stay because those tools are still present. Completing a
migration does not make its validation and recovery checks obsolete.

## Standard unittest compatibility

The runner uses Python's standard unittest library. These commands also work:

```bash
python -m unittest discover -s tests -t . -p 'test_*.py' -v
python -m unittest tests.devices.matter.test_matter_reliability -v
```

The old flat `tests/test_*.py` paths have been removed. Use the category paths
above; new test modules belong under an existing suite where appropriate.
Historical checklist IDs remain in some class names for traceability, while
the folders and filenames describe what is being checked.

## What a pass proves

These are source and fixture tests: isolated Flask requests, fake device/process
responses, an isolated loopback Waitress capacity test, temporary filesystem/Git
fixtures, and source-contract checks. They
do not validate live Matter/Tapo/Android hardware, real camera audio/video,
browser rendering, provider credentials, or the deployed systemd service.

Some dashboard checks inspect JavaScript source rather than execute it in a
browser. A full pass is useful regression evidence, not a complete application
audit or proof of live device reliability. Maintenance tests exercise destructive
operations only against disposable fixture data; their printed cleanup counts
refer to those fixtures.
