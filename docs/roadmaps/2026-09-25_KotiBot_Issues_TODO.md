# KotiBot outstanding functional checks

The earlier Matter patch instructions are retired: their implementation is in
the current source. Source tests and installation do not establish physical
reliability. These checks remain open until verified on KotiBot.

- Greenie/Dolphin access works at `/var/mnt/kotibot`; reboot persistence still
  needs a host check.
- Verify Matter monitoring resumes after manual sync and recommissioning with
  the installed chip-tool build.
- Leave a bulb unchanged beyond the stale interval, interrupt its power, and
  restore it. Verify other devices keep updating and the bulb recovers.
- Compare at least ten occupied/clear cycles with dashboard, automation and
  security events. Confirm reconnect baselines cause no false actions, each
  later edge fires once, and retrigger/timer behavior is preserved.
- Verify Tapo/Android cold-start display and command readiness across restart.
- Verify native per-node subscription processes, CPU/memory use and first-event
  latency on the Raspberry Pi. Windows behavior remains unverified.

The active security/source-access lane remains
`1a_KotiBot_Safe_Local_Agent_Access_Checklist.md`; these physical checks do not
silently activate beta work or mark deferred stability items complete.
