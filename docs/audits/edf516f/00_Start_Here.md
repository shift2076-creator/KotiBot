# KotiBot audit pack

Pinned source: `edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a`.

This is a ready-to-use plan for **50 initial bounded audit chunks** across ten groups. It includes every one of the **367 tracked files** in the pinned Git tree, plus **150 starter acceptance requirements**. These counts measure the plan, not completed audit coverage.

Read `01_Audit_Checklist.md` for the complete task cards and dependencies. Use `03_Session_Prompt.md` to start KB-A00 in Astra extra-high. Keep `coverage.json` and a chunk report using `02_Evidence_and_Findings.md` with each session's results.

| File | Purpose |
|---|---|
| 01_Audit_Checklist.md | Fifty task cards, ordering, evidence rules and existing-roadmap crosswalk |
| coverage.json | All tracked paths/hashes, chunk dependencies, provisional owners and acceptance rows |
| 02_Evidence_and_Findings.md | Per-chunk report and finding templates |
| 03_Session_Prompt.md | Reusable execution prompt and initial handoff |

The ZIP preserves `docs/audits/edf516f/`. Extract it into the KotiBot source checkout to add documentation/support files, or read the files directly. It contains no production replacements, executable collectors or runtime data. No restart is needed.

The current task creates the plan. It does not claim to have executed its audit chunks, closed existing gates, enabled agent access or established beta readiness.
