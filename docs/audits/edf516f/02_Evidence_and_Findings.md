# Evidence and findings contract

Use `coverage.json` as the machine-readable register and keep the checklist and latest handoff consistent. The initial file ownership is provisional. Expand behavior rows into exact cases before reviewing each chunk. Never replace evidence with a percentage of files opened.

## Per-chunk report template

- Chunk / parent / children:
- Status: not_started | in_progress | review_complete | verified | blocked | not_applicable
- Baseline / candidate commit / external component versions:
- Review date and reviewer:
- Source files and exact functions / routes / methods:
- Ownership trace: input → parser/validation → state owner → persistence → consumers → render/action:
- Required invariants and their source:
- Cases completed, expected result, actual result and evidence reference:
- Environment and commands; discovery/pass/fail/skip counts:
- Source / isolated tests / browser / live host / hardware evidence, each separately:
- Findings and unresolved hypotheses:
- Unreviewed scope, unavailable input, and exclusion rationale:
- Next unblocked chunk:

Evidence references should identify a sanitized local report/log, test and invocation, fixture version, source symbol/line at the pinned revision, browser observation, or physical test record. Keep complete command text and relevant output, not private payloads. Do not place secrets or personal household data in source-controlled audit artifacts.

## Finding template

- ID: KB-F-0001 (unique and stable)
- Title / owning chunk / related chunks:
- State: hypothesis | confirmed | rejected | fix_proposed | fixed_pending_verification | verified_fixed | accepted_risk
- Severity: critical | high | medium | low | informational
- Confidence and evidence basis:
- Affected source and deployed revisions:
- Exact file/symbol/line at the pinned revision:
- Preconditions, attacker/caller capability if applicable:
- Expected behavior and requirement:
- Reproduction steps, minimal safe fixture, actual behavior:
- Impact: user-visible failure, exploit reach, data/identity consequence, frequency:
- Negative controls / alternative explanations checked:
- Proposed fix boundary (no implementation authorization implied):
- Regression cases and live/browser/hardware verification required:
- Fix commit, verification environment and result:
- Risk acceptance owner, reason, mitigation, review date (only when explicitly accepted):

Severity reflects consequence and reach, not how alarming a code pattern looks. A hypothesis stays a hypothesis until supported. Prioritize reproducible defects and trust-boundary violations; maintainability preferences should not become security findings without impact evidence. Dedupe repeated symptoms under the common cause while preserving affected paths.

## Evidence rules

- Test startup is not a test pass. Record discovered, executed, passed, failed and skipped counts.
- Mocked success proves only the contract tested. Include assertions that would fail on the original defect where known.
- Use negative controls for authorization and recovery claims. Test under the actual identity when identity is the claim.
- Existing tests may be structural/source-text checks; record that limit instead of treating them as runtime proof.
- Run live failure injection only in its specifically agreed window. Corrupt state, full disks and interrupted migration belong in disposable fixtures/staging.
- Dependency advice requires current primary-source advisories and exact package/native versions when that chunk executes.
- Read-only live collectors must emit metadata or value-free results, never full environments, credential-bearing URLs, private state or raw journal dumps by default.
- All reviewers must check the designated revision before relying on a report. A report at another revision is historical evidence with an applicability assessment.

## Current findings

No application findings are asserted by this planning package. Missing external Android client source and effective deployment configuration are planned evidence gaps. The earlier slow stop and known roadmap defects are investigation inputs, not newly proven root causes.
