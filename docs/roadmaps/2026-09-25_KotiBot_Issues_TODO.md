# KotiBot current issues — September 25, 2026

Authoritative source: `shift2076-creator/KotiBot` commit
`7f43621c11b90dc1cce9ecd9e374b9a2a3b5f332`.

This is the active issue list requested by the user. It does not mark the
broader security, stability, or beta roadmaps complete. Local implementation,
automated verification, installation, and physical verification are distinct.

| # | Issue | Current status | Acceptance |
|---|---|---|---|
| 1 | Greenie/Dolphin access | Working; user confirmed `/var/mnt/kotibot` mount | Share remains accessible; reboot persistence has not been independently checked here. |
| 2 | False startup status | Implemented locally; automated checks pass; not installed | Matter observations start unknown, failed reads do not establish live state, and the first report does not fire automation/security events. Tapo/Android startup behavior remains a separate unfinished portion of the portal-wide request. |
| 3 | Powered Matter bulbs become stale | Implemented locally; automated checks pass; not installed | On/off subscriptions cover bulbs, valid quiet reports maintain liveness, and a disconnected node can recover without blocking other nodes. |
| 4 | Intermittent occupancy | Implemented locally; automated checks pass; not installed | Independent node subscriptions; occupied/clear transitions delivered once; initial/reconnect baselines do not fire false events. Physical miss-rate verification remains required. |
| 5 | Verified delivery | Prepared; 48 automated checks pass | Exact PRE/POST replacements, downloadable regression tests, source and validation record, and precise remaining live checks. |

## Required checks before marking items 2–4 complete

- [x] Automated: Cold restart with recently saved Matter observations remains unknown until live reports arrive.
- [x] Automated: A failed read, cached discovery, or a healthy sibling endpoint cannot falsely mark an endpoint live.
- [x] Automated: Bulbs receive ongoing on/off updates and do not become stale merely because their values stay unchanged.
- [x] Automated: Two nodes remain monitored simultaneously; loss of either does not stall the other.
- [x] Automated: manual sync drains active node workers before reading device state.
- [ ] Live verification: monitoring resumes correctly after sync; recommission behavior with the installed chip-tool build remains unverified.
- [x] Automated: Initial/reconnect baselines do not fire automation/security actions.
- [x] Automated: Repeated unchanged reports do not fire duplicate occupancy transitions.
- [x] Automated: Existing protected Matter storage and private-permission tests pass.
- [ ] Changes are installed by the user against the designated source.
- [ ] Physical bulb power interruption/recovery and repeated occupied/clear transitions pass on KotiBot.
- [ ] Tapo/Android cold-start display and command-readiness behavior are verified and corrected as needed.

## Scope and delivery

No production files, live services, device identities, credentials, or GitHub
branches have been changed by this work. Local patches are not an installed fix.
The user applies and commits changes through VS Code under the repository's
existing delivery contract.

## Automated verification

48 tests pass on Linux with Python 3.12 and Flask 3.1.3: 16 new Matter reliability
tests, 9 existing Matter storage/wiring tests, 10 private-permission tests,
8 state-backup tests, and 5 typed-state-read tests. No physical hardware, native
chip-tool process, production server, Windows host, or Pi resource measurements
were available in this environment. No claim of full hardware resolution is made.
