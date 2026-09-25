# Matter reliability patch — verification and application

Source: `shift2076-creator/KotiBot`, commit
`7f43621c11b90dc1cce9ecd9e374b9a2a3b5f332`.

## Changes

- Restored Matter observations start unknown; saved identity, name, zone, and
  configuration remain intact.
- Cached discovery and failed attribute reads cannot establish live status.
- A healthy endpoint cannot lend its timestamp to an uninitialized sibling.
- Persistent subscriptions include bulb OnOff and bridged reachability reports.
- Independent per-node workers recover failed subscriptions with bounded
  exponential backoff (configured retry interval, capped at at least 300 seconds).
- Quiet ReportData frames maintain liveness; console noise does not.
- Initial and reconnect attribute reports are baselines, suppressing false
  contact, motion, environment, and bulb transition activity.
- Manual sync drains node subscriptions; sync and recommission take lifecycle
  locks in the same order.

## Verified locally

48 tests passed on Linux, Python 3.12, Flask 3.1.3:

| Suite | Tests |
|---|---:|
| New Matter reliability behavior | 16 |
| Existing Matter protected paths and runtime wiring | 9 |
| Existing private permissions | 10 |
| Existing state backups | 8 |
| Existing typed state reads | 5 |

The new tests exercise real state-loader and Flask-route functions with synthetic
devices; controlled subprocess output tests parsing and watchdog behavior.
Threaded tests verify simultaneous monitoring, one-node failure/recovery, and
draining before sync. No hardware is simulated as proof of physical reliability.
The private-permission suite deliberately prints a source-mismatch refusal for
its negative test; the suite passes.

All four changed Python files compile. Every PRE block in
`docs/Matter-Reliability-Exact-Changes.md` is unique in the designated source.
Replaying all replacements produces the tested files exactly. Whitespace checks
on the four changed files pass.

## Apply

1. Confirm the checkout matches the designated commit and preserve any local
   changes before editing. Do not apply these replacements to different source.
2. Apply the exact PRE/POST replacements in the companion document to:
   `server_core/state.py`, `server_core/status.py`,
   `subsystems/matter/matter_routes.py`, and
   `subsystems/matter/matter_runtime.py`.
3. Extract the support archive at the KotiBot repository root. It contains new
   tests and documentation only; it does not contain replacement production files.
4. Activate KotiBot's existing Python environment and run:

```bash
python -m unittest discover -s tests -p test_matter_reliability.py -v
python -m unittest discover -s tests -p 'test_*matter*runtime*.py' -v
python -m unittest discover -s tests -p test_state003_private_permissions.py -v
python -m unittest discover -s tests -p test_state_backups.py -v
python -m unittest discover -s tests -p test_typed_state_reads.py -v
python -m compileall -q server_core subsystems/matter
git diff --check
```

5. After the existing project pre-restart gate passes, restart only the KotiBot
   service using its established service control, then reload the portal.
   A reboot is not the fix; this restart loads the changed Python code.

No migration, credential rotation, recommissioning, or state-file deletion is
required by this patch. Do not recommission devices merely to test recovery.

## Still requires the KotiBot host

- Confirm the installed chip-tool build's output and subscription behavior.
  The new quiet-report path recognizes its existing `ReportDataMessage =` log
  framing; native process behavior was not exercised locally.
- Keep a bulb unchanged longer than the normal stale interval; confirm it stays
  live. Disconnect its power; confirm other devices keep updating. Restore power
  and allow for the configured recovery backoff.
- Repeat at least ten occupied/clear cycles and compare the physical sensor,
  dashboard, automation, and security activity. The observed miss rate has not
  been claimed resolved without this check.
- Verify reconnect baselines produce no unsolicited actions; later real edges
  produce one action each. Check existing retrigger/timer behavior.
- Verify a manual sync resumes monitoring; check CPU, memory, first-event latency,
  and the native per-node process count on the Raspberry Pi.
- Windows and full portal-wide Tapo/Android startup behavior remain unverified.
  Those remaining items stay open in the active to-do list.
