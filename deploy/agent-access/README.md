# KotiBot: production and isolated VS Code development

Linux operator setup for the verified Greenie/KotiBot deployment. This is not
shared application runtime and does not claim Windows support. No device,
credential, state, recording or Matter identity migration is performed.

## Current development workflow — 2026-09-27

PATH-002 and AGENT-AUDIT-001 are complete. The user has authorized development
writes throughout `/workspace/kotibot` without per-diff approval. Follow
AGENTS.md Section 0.4 and preserve existing uncommitted work.

The saved `kotibot-workspace` profile enables writes to that checkout while
keeping command network access disabled and native approvals `on-request`.
AGENT-001 remains open until the client activates those permissions and an
ordinary workspace write succeeds without escalation. The preparing session
still has an enforced read-only profile; configuration alone is not activation.

The container-only CLI instructions below describe the earlier setup. They
are not remaining gate requirements. Do not run their full-access launcher,
clean-tree probe or installation/recovery commands to resume this session.
Current evidence is in `docs/roadmaps/1a_KotiBot_Safe_Local_Agent_Access_Checklist.md`.

## Production

Run `sudo python3 tools/path002_production.py install --expected-head COMMIT`
on KotiBot from the original operator checkout. The helper exports the exact
Git commit into `/opt/kotibot/releases/COMMIT`, copies/verifies the existing
Python environment, checks it with the value-free credential scanner, and
makes the release root-owned. It installs only
`zzz-path002-source.conf`, preserving the existing service identity, 12-worker
command, credentials and other drop-ins. A restart loads the release.

Verification checks the actual process working directory, unchanged resolved
runtime destinations, and write denial under the service UID. A failed cutover
attempt restores the previous drop-in/service. Original source and releases
are retained for recovery. No rollback material is deleted.

Later promotion uses the same explicit operator command with a reviewed,
committed SHA. Changed Python dependency declarations require a separately
reviewed environment update; the helper refuses to reuse incompatible packages.
Run `sudo python3 tools/path002_production.py rollback` to restore the previous
service source. Run `verify` to repeat the production boundary checks.

## Greenie: approved container boundary

The operator approved container-only Codex execution on 2026-09-26. Rootless
Podman provides the security boundary. The stock Codex CLI uses
`--sandbox danger-full-access --ask-for-approval on-request` only inside that
verified container. This is an explicit policy choice, never an automatic
fallback after a failed nested sandbox.

OpenAI documents this pattern for containers that cannot run the nested Linux
sandbox: https://learn.chatgpt.com/docs/agent-approvals-security#os-level-sandbox

### What is enforced

The container retains its dedicated source checkout and named developer-home
volume, enforcing SELinux `container_userns_t`, read-only system filesystem,
zero Linux capabilities, no-new-privileges, seccomp, and private internal network.
Its HTTPS CONNECT proxy limits destinations to the configured OpenAI, VS Code,
and Python-package endpoints. Direct LAN/Internet access, production/publication
routes, operator authentication, production mounts, host engine sockets and
service-management access remain denied. No audio device or audio-service
forwarding is permitted.

Commands can write the container's home and workspace and use its permitted
network destinations. Codex login material inside that dedicated home is
available to processes inside the container. The nested workspace-only write
restriction, inner daemon-directory mask and inner network namespace are not
part of this mode. Use only the trusted KotiBot checkout. On-request approval
allows Codex to ask for approval; it does not require approval for every command.

### Finish the existing installation

The restored `kotibot-development` container, existing image, workspace, home,
login and proxy are reused. No rebuild, container replacement, production change
or new sign-in is needed. The operator checkout can remain at `0c273d0...` while
the clean development checkout remains at its separately recorded `834b7ff...`.
Nothing fetches, resets, commits or synchronizes those checkouts.

From the ordinary Greenie terminal:

```bash
cd /var/mnt/kotibot
python3 tools/agent_development.py check-codex \
  --expected-head 834b7ff478e18a56613aa9a741103407828c7a40
python3 tools/agent_development.py codex
```

Run the second command only if the first succeeds. `check-codex`:

1. Checks rootless Podman, SELinux enforcement, exact approved mount destinations,
   internal networking and the running container identity.
2. Runs the denial matrix and checks the installed Codex binary/version.
3. Uses that actual CLI's `sandbox` command with `sandbox_mode="danger-full-access"`
   to execute the denial matrix again, a temporary workspace write/delete,
   `/opt/tests/bin/python -m tests`, and the source-boundary verifier.
4. Requires the expected development HEAD and clean initial/final Git status,
   then rechecks the outer boundary before reporting completion.

This is a real local Codex command-execution check, without a model request or
login. It deliberately does not claim nested Bubblewrap verification. The final
success marker is `CODEX CONTAINER EXECUTION AND FULL SUITE: PASS`.
A failed command stops verification and is never retried with broader permissions.

`codex` checks the boundary on every launch, pins the inspected container ID,
then runs the installed CLI inside `/workspace/kotibot` with the approved flags.
It inherits terminal input directly, so normal CLI exit and Ctrl+C reach Podman.
It does not install an extension, change Codex configuration or start a login.
Use this CLI launcher for typed input; the separate VS Code editor remains
available. IDE extension execution settings are not changed by this package.

For the first model session, ask it to read `AGENTS.md`, report `pwd`, Git HEAD
and Git status, and create/delete one temporary workspace file. Do not grant
production, credential, publication or audio access. Model-session completion
is separate from the local command-runner test; neither is claimed before its
actual result is observed.

### Routine use

- `python3 tools/agent_development.py verify --codex` repeats the outer-boundary
  checks and confirms extension presence; it does not run the suite.
- `python3 tools/agent_development.py check-codex` repeats full local execution
  verification against the current clean development HEAD. Use `--expected-head`
  to require a particular development commit.
- `python3 tools/agent_development.py codex` starts the guarded CLI. Existing
  work in progress is allowed; this command does not rerun the full suite.
- `python3 tools/agent_development.py open` starts the dedicated development
  containers and opens the separate VS Code profile. If attachment needs to be
  selected manually, use Dev Containers: Attach to Running Container and choose
  `kotibot-development` in that dedicated profile.

Keep Git credential copying/forwarding disabled. Review changes in VS Code.
Publication and production promotion remain explicit operator actions outside
the development container. Never run the container-mode Codex flags directly on
Greenie or against `/var/mnt/kotibot`.

For a new installation, `setup --expected-head COMMIT` creates the shallow clean
checkout, isolated editor profile, images, networks, proxy and home volume.
`resume --expected-head COMMIT` reuses those resources, checks matching source
commits and runs the outer-boundary and test gates. `enable` remains the initial
attached-editor/production verification step before installing Codex inside the
container. These initial setup steps are already complete on Greenie.

### Recovery and earlier nested-sandbox work

The existing SELinux/Bubblewrap repair and rollback commands are retained for
recovery. They are not prerequisites for the approved container mode. In
particular, do not rerun `repair-bubblewrap` or `rollback-bubblewrap` after the
failed candidate was automatically rolled back: the original container is
already running, while the failed candidate and recovery record remain intact.

The nested Bubblewrap probe and `repair-bubblewrap` still require all original
nested restrictions and real nested Codex verification. They do not silently
select container mode. Their read-only-mask/procfs failures remain failures.
The optional Bubblewrap 0.13 image build remains available; this update neither
builds nor activates it. The current command launcher works with the restored
image because it does not request a nested Bubblewrap sandbox.

To stop development, exit Codex and the dedicated editor, then run
`podman stop kotibot-development kotibot-dev-proxy`. Workspace/home contents and
all recovery material remain. Source-package restoration uses the installer's
`--restore` option with the backup path printed during installation. It restores
operator helper files only, never shared workspace/home contents or containers.
Restoring those helpers restores their old nested-sandbox behavior and blockers.

The active checklist records the current gate status and remaining activation
check. Installing these helpers alone does not establish an audited session.
