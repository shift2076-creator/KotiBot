# KotiBot: production and isolated VS Code development

Linux operator setup for the verified Greenie/KotiBot deployment. This is not
shared application runtime and does not claim Windows support. No device,
credential, state, recording or Matter identity migration is performed.

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

## Greenie

`python3 tools/agent_development.py setup --expected-head COMMIT` creates:

- `~/Projects/kotibot-development`: shallow source checkout of that commit.
- `~/.local/share/kotibot-development`: separate VS Code profile and extension
  installation; no copying of your existing profile or credentials.
- Rootless Podman development and proxy containers, two dedicated networks,
  and the `kotibot-development-home` volume for the isolated editor/Codex login.

The development container mounts only its dedicated checkout and home volume.
On Greenie it uses the distribution's existing `container_userns_t` SELinux
process type, which permits the nested user-namespace sandbox's procfs and
terminal mounts. SELinux stays enforcing; no custom policy or global boolean
change is required. The outer container still drops every Linux capability.
It has a read-only system, no capabilities, no privilege escalation, no host
SSH agent, no production mounts, no container-control socket, and no service
bus. A private network has no external default route. An HTTPS CONNECT proxy
permits only OpenAI authentication/model endpoints, VS Code extension/server
endpoints, and Python package downloads. Production, GitHub publication and
private-address destinations are denied. GitHub fetching/publishing remains
an operator action outside the container. The proxy has no request log/cache.

The public dependency images are built on Greenie. Setup validates rootless
Podman/Netavark, runs the denial matrix, and runs the normal full test suite
inside the development environment. It also starts a nested bubblewrap sandbox
with workspace write access before any production cutover. It stops on a
failed boundary/sandbox/test/build; it never disables seccomp or adds capabilities.
A denied fresh procfs mount gets one retry retaining the container procfs, as
Codex does; all user/PID/IPC/network namespaces and capability drops remain.
This prerequisite check does not replace an actual Codex command test.
It refuses to overwrite an existing workspace or setup state. Once the containers
exist, `resume --expected-head COMMIT` reruns verification and tests without
rebuilding or replacing them. Failures include the underlying command output.
The operator helper sends the current checked-in probe over stdin, so a corrected
probe does not require rebuilding an otherwise unchanged development image.

### Repair the earlier SELinux profile

The original `container_t` setup on Greenie denied Bubblewrap's procfs/devpts
mounts. A disposable test using the same image and `container_userns_t` passed
on 2026-09-26. This proves sandbox startup only; the full live boundary check,
attached editor and actual Codex session remain separate gates.

Close the dedicated development VS Code window if it is open. From the
operator checkout on Greenie run:

```bash
python3 tools/agent_development.py repair-selinux --expected-head COMMIT
```

This validates both checkout commits and the original container configuration,
then prepares `kotibot-development-selinux-candidate` from the existing image
ID without pulling or rebuilding. It retains the same checkout, named home
volume, private network/proxy and SELinux categories. It stops the original
before starting the candidate, runs the full denial matrix, nested sandbox,
test suite and source-boundary check, and activates the candidate only after
all pass. The original is retained, stopped, as
`kotibot-development-before-selinux`.

If candidate verification fails, the original is restarted and the failed
candidate is retained for inspection. An existing recovery name blocks another
attempt rather than overwriting it. Unexpected source commits, host mounts,
security labels or rootful Podman also block the repair. An already repaired
container is reverified without recreating it. No production operation runs.

To restore the previous development container after a successful repair:

```bash
python3 tools/agent_development.py rollback-selinux
```

Rollback preserves the repaired container under the candidate name and keeps
the shared checkout and home volume. This restores container configuration,
not earlier versions of files in those shared locations. Agent access is again
blocked under the old profile. No container, image, checkout or volume is
deleted. If rollback itself fails, the helper attempts to restore the repaired
container and reports any recovery failure. Source-package rollback is separate.

Policy reference:
https://github.com/containers/container-selinux/blob/main/container.te
(`container_userns_t` rules). Label selection:
https://docs.podman.io/en/latest/markdown/podman-run.1.html#security-opt-option

## Open and enable

1. Run `python3 tools/agent_development.py open` on Greenie. It starts the
   dedicated containers and opens a separate VS Code window attached to them.
2. Wait for the attached window to finish connecting. Run
   `python3 tools/agent_development.py enable` from your ordinary Greenie
   terminal. This rechecks mounts, network restrictions, denied reads/writes,
   SSH forwarding in the running editor processes, and Git credential helpers
   before permitting Codex installation.
3. In the attached VS Code terminal run
   `code --install-extension openai.chatgpt`.
   Then run `python3 tools/agent_development.py verify --codex` in the ordinary
   Greenie terminal to verify the extension location and repeat the boundary checks.
4. After that passes, sign into Codex in that attached window. Use its normal sandboxed mode;
   do not enable host mounts, credential forwarding, host networking or a
   container-engine socket. If Codex's own sandbox fails on the installed
   kernel/container stack, stop and report that failure; do not disable it.

Run `verify` after changing editor/container configuration. The actual running
editor check is required; an isolated unit test is not that proof. A container
check does not prove Windows, physical devices, or a future changed setup.
The local CLI must not be launched against `/var/mnt/kotibot`.

## Operator workflow and recovery

Review and commit in the attached VS Code window. Publish from the ordinary
Greenie terminal after review; no GitHub credentials are shared with the agent.
Fetch the approved commit in the original server/operator checkout, run tests,
and explicitly invoke the production promotion command. Agent edits have no
automatic effect on the running service.

To stop the development environment: close its VS Code window, then run
`podman stop kotibot-development kotibot-dev-proxy`. Reopen with the `open`
command. This preserves source and editor state. Failed setup also preserves
all created files/resources for inspection; no broad automatic cleanup runs.
Source-package rollback is separate from production rollback. Restore the
service first if undoing the whole setup; neither operation deletes runtime
recovery archives or your development work.

PATH-002, AGENT-AUDIT-001 and AGENT-001 remain pending until the production,
container, post-attachment checks and actual Codex session succeed on the hosts.
