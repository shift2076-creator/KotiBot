# One-session execution prompt

Copy the prompt below into an Astra extra-high session with the current audit package. Select the model/effort in your session interface; the prompt does not change model settings.

```text
Execute KotiBot audit chunk KB-A00 from docs/audits/edf516f/01_Audit_Checklist.md.

Authoritative repository: shift2076-creator/KotiBot
Authoritative source: edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a
Mode: audit the specified chunk; produce evidence and findings, without implementing production fixes.

Read AGENTS.md at the designated revision, the chosen chunk, coverage.json, and the latest handoff. Follow the existing authority and privacy boundaries. Verify source identity before substantive work. Use the provided GitHub source when available; do not ask me to upload files you can retrieve.

First check dependencies and define the precise functions/routes/cases inside this chunk. Trace relevant callers, state, persistence, consumers, UI and trust boundaries. Direct dependencies are in scope for understanding; unrelated remediation is not. Split oversized work into clear children and keep the parent open.

Complete the bounded audit using source review and safe isolated tests appropriate to it. Do not launch unattended production actions, device commands, service restarts, credential rotations or destructive tests under this audit prompt. If a required fact is unavailable, complete independent work and mark the exact evidence blocked. Do not ask for routine choices already resolved by the plan.

Give meaningful progress updates. Record confirmed findings separately from hypotheses and existing known issues. Reuse prior evidence only with a revision/applicability check. A green unit suite is not hardware or deployment proof.

Update only the audit/support artifacts authorized by this task. Add narrowly relevant regression fixtures if necessary to substantiate a finding. Do not silently fix production code. Deliver the chunk report, updated coverage/findings and handoff in the repository-relative support ZIP required by AGENTS.md.

Finish with: outcome; key confirmed findings; tests/evidence and limits; remaining blockers; exact next unblocked chunk. Do not claim the full audit complete or activate beta/local-agent access.
```

For later sessions change the chunk ID and designated source only when the user has supplied/accepted the new revision. Include the newest register and handoff. Preserve the initial baseline; fixes create candidate revisions with explicit affected-chunk rechecks.

## Handoff template

1. Baseline and current candidate revision:
2. Last completed/reviewed chunk and evidence links:
3. Open findings, accepted risks and pending reproductions:
4. Outstanding required browser/live/hardware proof:
5. Changed contracts/symbols and invalidated evidence after any fix:
6. Next unblocked chunk and exact prerequisite inputs:
7. Current scope/authority and any user steering:

## First handoff — September 25, 2026

- Planning package completed at `edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a`.
- All 50 initial execution chunks are `not_started`; all 367 tracked artifacts are `unreviewed`.
- First execution task: **KB-A00** (scope, inventory and ownership map).
- This package already supplies the complete tracked tree and provisional owners; refine it into exact behavior/route/state/worker coverage instead of rebuilding the file list from memory.
- Existing Matter patch comparison and prior test results are summarized in the checklist. No fresh full-suite run or live-host audit is claimed.
- External Android app source/build and sanitized effective deployment configuration will be needed in their owning chunks. Neither blocks the initial public-source map.
