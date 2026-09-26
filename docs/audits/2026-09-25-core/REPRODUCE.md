# Reproducing the audit evidence

Read `AUDIT.md` first. This ZIP is a report and isolated reproduction package. It contains no application replacements, installer, runtime data, or service commands. Nothing needs to be installed into the running KotiBot service.

The recorded runs used CPython 3.12.14, Flask 3.1.3, Werkzeug 3.1.8, and Waitress 3.0.2 on Linux. The probes use standard-library mocking and temporary directories. Real device calls and credential reads are replaced before invoking the Tapo functions. The connection/worker probes use local threads; they do not open a server socket or contact devices.

The scripts verify pinned application-file hashes before importing their helpers. Supply a source checkout with the audited bytes from `edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a`. The reorganized test layout is not required. The source checkout is read-only for these probes when bytecode generation is disabled as below.

From a directory containing the extracted `docs/` folder, use an existing development virtual environment containing the listed dependencies, or create an isolated one:

```bash
python3 -m venv /tmp/kotibot-core-audit-venv
/tmp/kotibot-core-audit-venv/bin/python -m pip install \
  Flask==3.1.3 Werkzeug==3.1.8 waitress==3.0.2

audit_python=/tmp/kotibot-core-audit-venv/bin/python
audit_source=/var/mnt/kotibot
audit_evidence=docs/audits/2026-09-25-core/evidence

PYTHONDONTWRITEBYTECODE=1 "$audit_python" "$audit_evidence/probes.py" \
  --source "$audit_source"
PYTHONDONTWRITEBYTECODE=1 "$audit_python" "$audit_evidence/network_probes.py" \
  --source "$audit_source"
```

Adjust `audit_source` to the source checkout if necessary. These commands do not restart the service or modify its state. No rerun is necessary to read or assess the already recorded evidence.

Expected result: both scripts exit zero and print JSON matching the included records. The Waitress test can print `Task queue depth is 1` to stderr because it deliberately fills the request-worker pool. That line is part of the reproduction.

An exit-zero result confirms that the baseline exhibits the audited behavior. These scripts are not fixed-behavior regression tests and should not be copied wholesale into the normal suite. When each defect is repaired, add a focused test that asserts the desired outcome. The source guard intentionally rejects a different implementation rather than silently claiming the old evidence applies.

## Recorded outcomes

| Scenario | Observation |
|---|---|
| `boot-invalid-json` | First load false; second true; healthy subsystem primary records reduced to zero after flush |
| `boot-wrong-schema` | Load true; six documents queued; healthy subsystem records reduced to zero |
| `broadcast-blocks-save` | Zero persistence calls after publication fails |
| `concurrent-registry-save` | Swallowed `RuntimeError`; only two of six documents queued |
| `json-symlink` | Redirected target modified and target backup created |
| `credential-retry` | Failed set/removal not attempted again on identical retry |
| `metadata-amplification` | One successful POST: three status builds, two broadcasts, six queued documents |
| `offline-control-status` | `last_seen=0` yields non-stale/Online |
| `repeated-theme-build` | Two dark-theme requests read both themes' image files twice |
| `sse-worker-capacity` | Four active streams block a short task in a four-worker dispatcher |
| `cancelled-tapo-connect` | Cancelled waiter later leaves global connection lock held |
| `tapo-duplicate-read` | One cached-device enrichment performs two device-info reads |
| `tapo-discovery-unbounded-read` | Later discovery read remains pending beyond shortened configured call and refresh deadlines |
| `automation-network-lock` | Global state lock remains held during device I/O |

`source-integrity.json` records the original source comparison. `probe-source-hashes.json` supplies the runtime guard for the reproductions. Recorded observations use only synthetic values.
