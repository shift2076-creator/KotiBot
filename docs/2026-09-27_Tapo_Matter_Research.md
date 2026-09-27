# Tapo and Matter research for the simplification audit — 2026-09-27

This records primary sources reviewed before implementing the
[simplification audit](2026-09-27_Simplification_Audit.md). Recommendations below
are KotiBot engineering judgments derived from those sources and the current
working files, not vendor certification or measurements on the user's devices.
No dependency, runtime code, device configuration or controller identity was
changed during this research.

**Authority and version baseline.** CSA defines Matter's protocol. The official
`project-chip/connectedhomeip` project defines its SDK and CHIP Tool behavior.
TP-Link documents product and firmware constraints. The maintainers of `tapo`
and `python-kasa` define their respective library APIs; these are unofficial
integrations, not TP-Link-supported SDKs. See the
[Tapo package description](https://pypi.org/project/tapo/),
[python-kasa project](https://github.com/python-kasa/python-kasa), and
[TP-Link compatibility policy](https://www.tp-link.com/us/support/faq/4416/).

| Component | KotiBot source baseline | Upstream verified on this date |
| --- | --- | --- |
| `tapo` | `requirements.txt`: `0.9.0` | PyPI latest is **0.9.0**, released April 25, 2026. [Package](https://pypi.org/project/tapo/) |
| `python-kasa` | `requirements.txt`: `0.10.2` | PyPI latest is **0.10.2**, released February 12, 2025. [Package](https://pypi.org/project/python-kasa/) |
| Matter specification | No device/specification version inferred from the application | CSA currently lists **1.6.1** Core, Application Clusters, Device Type Library and Standard Namespace documents. [CSA catalogue](https://csa-iot.org/developer-resource/specifications-download-request/) |
| Matter SDK / CHIP Tool | README requires an external `chip-tool`; its deployed revision is not established here | Official latest release is **v1.6.1.0**, released September 25, 2026. [SDK release](https://github.com/project-chip/connectedhomeip/releases/tag/v1.6.1.0) |

The checkout remains the authoritative application source at HEAD
`0c273d031fa2b2aa23ba975acc3af6f4c53e9ad3`, including existing working changes.
An upstream release does not establish the deployed controller or device
firmware version. There is no recommendation here to upgrade automatically.

**Tapo: preserve capability differences while consolidating ownership.**

The upstream feature matrix exposes a combined `set()` request for color bulbs
and supported light strips, but not L510/L520/L610 dimmable-only bulbs. The
0.9.0 Rust API similarly distinguishes `ColorLightHandler` from `LightHandler`.
Its ordinary color-light brightness/color setters also turn the light on.
[Feature matrix](https://raw.githubusercontent.com/mihai-dinculescu/tapo/main/SUPPORTED_DEVICES.md),
[color-light API](https://docs.rs/tapo/latest/tapo/struct.ColorLightHandler.html),
[dimmable-light API](https://docs.rs/tapo/latest/tapo/struct.LightHandler.html).

For KotiBot, retain the capability branch in `tapo_scenes.py`. Reuse combined
commands where supported; preserve the minimum required sequence elsewhere.
Power-preserving presets need their own behavioral checks because ordinary
setters can power on a device. Fewer lines are not sufficient justification to
flatten these differences or redirect child commands to their parent.

The matrix on `main` includes unreleased features. The
[maintainer changelog](https://raw.githubusercontent.com/mihai-dinculescu/tapo/main/CHANGELOG.md)
lists plug schedules/timers and unchecked child-handler constructors under
Unreleased. Do not use those as if they shipped in 0.9.0. Conversely, native
discovery is already present in 0.9.0, so its existence should be considered
before adding more discovery parsing or another transport wrapper.

**Tapo: distinguish commands, observations and discovery.**

The python-kasa tutorial says setters do not refresh cached device state;
`update()` retrieves it. It also requires operations on a device to use one
asyncio event loop and recommends checking available modules/features.
[Maintainer tutorial](https://python-kasa.readthedocs.io/en/latest/tutorial.html).

For KotiBot, successful command completion may support an optimistic UI update,
but should not silently become proof of an observed physical state. Keep bounded
refreshes where the integration needs them. Removing every poll or readback
would be an incorrect interpretation of the audit's efficiency goal.

KotiBot currently invokes Kasa in separate CLI processes for discovery and some
child operations. If that path is replaced by cached in-process Kasa devices,
give those objects one long-lived event loop. The Kasa rule is not evidence
that the separate Rust-backed `tapo` library has the same loop restrictions.
Do not declare KotiBot's `run_async()` erroneous on that basis alone.

Discovery may also perform necessary device recovery. Tapo's maintainer
troubleshooting page documents a P110 firmware case where a discovery probe
starts the local API after boot.
[Maintainer troubleshooting](https://raw.githubusercontent.com/mihai-dinculescu/tapo/main/TROUBLESHOOTING.md).
Treat that as a specific recovery case to validate, not a reason for continuous
whole-network scans or automatic factory resets.

**Tapo: account for retries already inside the library.**

The exact `python-kasa` 0.10.2 `SmartProtocol` source serializes queries within
one protocol object and implements bounded retries. Authentication errors are
raised without retry; selected connection, retryable and timeout failures take
different paths. It also falls back from batching for specified device errors.
[Pinned protocol source](https://raw.githubusercontent.com/python-kasa/python-kasa/0.10.2/kasa/protocols/smartprotocol.py).

For KotiBot, an application retry budget must include the selected SDK's own
behavior. A lock inside one SDK instance does not order multiple CLI processes
or KotiBot's read/modify/reconcile transaction. Reuse the existing application
command queue across scheduled, manual and Scene callers. Preserve SDK
compatibility handling until its purpose and supported devices are understood.

Tapo exposes session renewal, and its Rust error model distinguishes expired
sessions from other authentication failures.
[Error source, displayed version 0.9.0](https://docs.rs/crate/tapo/latest/source/src/error.rs).
KotiBot's narrow Scene exception matching therefore has a defensible purpose.
Its exact Python exception representation still needs verification against the
pinned distribution before changing that matcher. Neither a timeout nor a
generic authentication failure establishes that a write was safely rejected.
Retries of writes require operation-specific idempotency and ordering analysis;
this is not a blanket prohibition on retries.

TP-Link says Third-Party Compatibility is firmware/model dependent, disabled
by default, and does not guarantee unofficial integrations will work. Enabling
it changes security exposure.
[Vendor FAQ](https://www.tp-link.com/us/support/faq/4416/).
KotiBot should report such failures distinctly rather than endlessly retrying,
changing compatibility settings, or treating every failure as a wrong password.

**Matter: preserve subscriptions and reduce unnecessary session setup.**

The official CHIP Tool guide documents a new CASE session for each
single-command invocation. Interactive mode reuses available sessions and
supports persistent subscriptions and multiple attribute paths. It also
documents explicit controller storage and commissioner identity selection.
[CHIP Tool guide](https://project-chip.github.io/connectedhomeip-doc/development_controllers/chip-tool/chip_tool_guide.html).

For KotiBot, retain the existing sensor subscription mechanism. Its ordinary
commands still create subprocesses, so a persistent command owner is a concrete
option to evaluate for latency and complexity. This requires a separate
comparison of process lifecycle, request/result correlation, failure isolation,
storage ownership and hardware measurements. This research does not establish
that replacing CHIP Tool with a different controller is necessary.

Do not copy the guide's test-environment cleanup commands into production.
KotiBot's protected fabric storage and existing commissioning identity remain
invariants. The present per-subscriber storage copies deserve explicit lifecycle
review before any controller consolidation; no storage change is authorized by
this note.

**Matter: let protocol semantics determine subscription health and recovery.**

The current SDK `ReadClient` provides attribute/event callbacks, subscription
establishment and recovery hooks, and backoff for automatic resubscription.
An empty report can still establish liveness. Its default liveness timeout
accounts for the negotiated maximum report interval and session ACK timing;
it also has special handling for intermittently connected devices.
[Official SDK ReadClient source](https://raw.githubusercontent.com/project-chip/connectedhomeip/master/src/app/ReadClient.h).

Google's older, introductory Matter documentation also explains the initial
subscription report and negotiated reporting intervals; it is supporting
background, not the latest normative specification.
[Read/subscription primer](https://developers.home.google.com/matter/primer/interaction-model-reading).

For KotiBot, preserve its existing treatment of empty `ReportData` frames as
liveness. Compare the application watchdog (`requested max_interval + 15`) and
process restart policy against the actual CHIP Tool version, negotiated interval
and SDK resubscription options before changing them. Source comparison exposes
a question to test; it does not prove a failure on the user's bridge.

The SDK also implements retransmission of messages awaiting acknowledgments.
[Official reliable-message manager](https://raw.githubusercontent.com/project-chip/connectedhomeip/master/src/messaging/ReliableMessageMgr.h).
Application-level command replay is a separate operation. Do not multiply these
layers indiscriminately or interpret a missing reply as proof that the device
did nothing. Preserve explicit error status and freshness information.

**Implications for the existing audit.**

| Audit area | Refined implementation constraint |
| --- | --- |
| 01: Scheduled Tapo command ownership | The reproduced race remains valid. Consolidate ordering and identity-aware reconciliation using the existing application owner; SDK locks do not replace it. |
| 02: Matter durable configuration | The reproduced lost update remains valid regardless of Matter release. Separate transient command diagnostics from synchronized durable configuration before changing transport architecture. |
| 05: Tapo batch/lighting retries | Consolidate dispatch without deleting capability branches, necessary observations, narrow session renewal, or documented SDK workarounds. Count application attempts separately from network transmissions. |
| CLI/parsing simplification | Evaluate structured library interfaces and persistent sessions against the current device matrix. KotiBot's Kasa child read path explicitly documents missing power fields in the Tapo response; replacing it needs equivalent data evidence. |
| Further Matter work | Verify deployed SDK revision, subscription negotiation, controller storage ownership and reported capabilities before designing a broader refactor. |

**Coverage and remaining verification.** The sources above were read on
September 27, 2026; `main`, `master`, `latest` and catalogue links can change.
Version-specific claims are limited to release metadata, displayed API versions
and the pinned Kasa source. Exact-tag Tapo Python binding pages and the latest
CSA specification download targets could not be retrieved through the research
tool. Consequently this is not a claim to have read every Matter 1.6.1 clause
or independently verified every Python binding detail. Clause-level changes
need the applicable specification, and exception/binding changes need the exact
0.9.0 source distribution or installed API contract.

No production credentials, controller storage or devices were accessed. Live
firmware/hardware revisions, deployed CHIP Tool revision, first-action latency,
reconnect behavior, Raspberry Pi resource use and Windows behavior remain
environment checks. Only documentation changed in this follow-up; the earlier
audit's test results are not new hardware or upstream-conformance evidence.
