#!/usr/bin/env python3
"""PATH-001D.2 live worktree mutation trace for the KotiBot service.

Security properties:
- watches the entire checkout recursively, including ignored files, .git, and
  .venv, so transient service writes are not hidden by Git status;
- uses Linux inotify plus a before/after metadata snapshot so create/modify/
  rename/delete activity is detected without reading file contents;
- verifies the running systemd MainPID is executing as the unit's configured
  service identity without printing that identity;
- never reads runtime JSON, credentials, logs, media contents, environment
  values, notification payloads, or Matter state contents;
- emits only counts and redacted evidence for untracked mutation paths.

The operator performs the representative PATH-001D.2 scenarios while this
process is watching. No service mutation is initiated by this tool.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import platform
import pwd
import select
import stat
import struct
import subprocess
import sys
import threading
import time


SCENARIOS = (
    (
        "startup-restart",
        "Restart kotibot in another terminal, wait for active, then return here.",
    ),
    (
        "device-synchronization",
        "Exercise normal Android/Tapo/Matter device synchronization or a live state change.",
    ),
    (
        "dashboard-mutations",
        "Make one reversible server-persisted dashboard edit and restore it.",
    ),
    (
        "automations",
        "Trigger one existing automation through its normal device/sensor path.",
    ),
    (
        "security-actions",
        "Trigger one existing KotiBot security action through its normal sensor path.",
    ),
    (
        "notifications",
        "Trigger one configured notification through its normal KotiBot action path.",
    ),
    (
        "recordings",
        "Start and stop one normal camera recording.",
    ),
    (
        "apk-serving-deployment",
        "Serve/download an existing KotiBot APK. External deployment-path safety is covered by the focused package-runtime test; do not alter packages solely for this audit.",
    ),
    (
        "matter-subscriptions-repair",
        "Exercise a normal Matter subscription update. Repair rollback/path safety is covered by the focused Matter fixture test; do not force a live repair solely for this audit.",
    ),
    (
        "caches",
        "Exercise a normal cache-producing path such as opening and closing a Tapo live preview.",
    ),
    (
        "logs",
        "Allow normal service logging while the preceding actions run.",
    ),
    (
        "temporary-staging",
        "Exercise a normal operation that uses temporary staging, such as recording/video normalization when available.",
    ),
)

SCENARIO_NAMES = tuple(name for name, _ in SCENARIOS)

# inotify constants from linux/inotify.h
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ISDIR = 0x40000000

MUTATION_MASK = (
    IN_MODIFY
    | IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)
WATCH_MASK = MUTATION_MASK | IN_Q_OVERFLOW

EVENT_STRUCT = struct.Struct("iIII")

EVENT_NAMES = (
    (IN_MODIFY, "modify"),
    (IN_ATTRIB, "attrib"),
    (IN_CLOSE_WRITE, "close-write"),
    (IN_MOVED_FROM, "move-from"),
    (IN_MOVED_TO, "move-to"),
    (IN_CREATE, "create"),
    (IN_DELETE, "delete"),
    (IN_DELETE_SELF, "delete-self"),
    (IN_MOVE_SELF, "move-self"),
)

SAFE_TOP_LEVELS = {
    ".git",
    ".venv",
    "deploy",
    "docs",
    "licenses",
    "server_core",
    "static",
    "subsystems",
    "templates",
    "tests",
    "tools",
}

SYSTEMCTL_PROPERTIES = (
    "ActiveState",
    "SubState",
    "MainPID",
    "User",
    "Group",
    "WorkingDirectory",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PATH-001D.2 live KotiBot worktree mutation trace. "
            "Linux/systemd host only; reads no runtime file contents."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="KotiBot repository root (default: current directory)",
    )
    parser.add_argument(
        "--unit",
        default="kotibot.service",
        help="systemd service unit (default: kotibot.service)",
    )
    parser.add_argument(
        "--expected-head",
        required=True,
        help="exact authoritative Git HEAD required before tracing",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help=(
            "on mutation, print exact tracked source paths and redacted "
            "untracked path evidence; never prints file contents"
        ),
    )
    return parser


def _run_text(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout


def exact_head(root: Path) -> str:
    return _run_text(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
    ).strip()


def tracked_paths(root: Path) -> set[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.split(b"\0")
        if item
    }


def _entry_metadata(entry: os.DirEntry) -> tuple[int, int, int, int, int]:
    info = entry.stat(follow_symlinks=False)
    return (
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def metadata_snapshot(root: Path) -> dict[str, tuple[int, int, int, int, int]]:
    """Snapshot names and stat metadata only; never read file contents."""
    root = Path(root).resolve()
    snapshot = {}
    stack = [root]

    while stack:
        directory = stack.pop()

        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                snapshot[relative] = _entry_metadata(entry)

                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)

    return snapshot


def snapshot_delta(
    before: dict[str, tuple[int, int, int, int, int]],
    after: dict[str, tuple[int, int, int, int, int]],
) -> dict[str, int]:
    before_keys = set(before)
    after_keys = set(after)
    shared = before_keys & after_keys

    return {
        "added": len(after_keys - before_keys),
        "removed": len(before_keys - after_keys),
        "changed": sum(
            1
            for key in shared
            if before[key] != after[key]
        ),
    }


def parse_systemctl_show(output: str) -> dict[str, str]:
    result = {}

    for raw_line in str(output or "").splitlines():
        if "=" not in raw_line:
            continue

        key, value = raw_line.split("=", 1)
        result[key.strip()] = value.strip()

    return result


def service_state(unit: str) -> dict[str, str]:
    command = ["systemctl", "show", unit, "--no-pager"]

    for prop in SYSTEMCTL_PROPERTIES:
        command.append(f"--property={prop}")

    return parse_systemctl_show(_run_text(command))


def _proc_uid(pid: int) -> int:
    status_path = Path("/proc") / str(pid) / "status"

    # /proc/<pid>/status contains process metadata, not KotiBot runtime data.
    # Read only the Uid line and never print the numeric identity.
    with status_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("Uid:"):
                fields = line.split()

                if len(fields) >= 2:
                    return int(fields[1])

    raise RuntimeError("service process Uid metadata unavailable")


def service_identity_matches(state: dict[str, str]) -> bool:
    try:
        pid = int(state.get("MainPID") or 0)
    except ValueError:
        return False

    if pid <= 0:
        return False

    configured_user = str(state.get("User") or "").strip()

    try:
        expected_uid = (
            pwd.getpwnam(configured_user).pw_uid
            if configured_user
            else 0
        )
        actual_uid = _proc_uid(pid)
    except (KeyError, OSError, RuntimeError, ValueError):
        return False

    return int(actual_uid) == int(expected_uid)


def service_active(state: dict[str, str]) -> bool:
    try:
        pid = int(state.get("MainPID") or 0)
    except ValueError:
        return False

    return (
        state.get("ActiveState") == "active"
        and state.get("SubState") == "running"
        and pid > 0
    )


def service_pid(state: dict[str, str]) -> int:
    try:
        return int(state.get("MainPID") or 0)
    except ValueError:
        return 0


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(
            root.resolve(strict=False)
        )
        return True
    except ValueError:
        return False


def working_directory_class(state: dict[str, str], root: Path) -> str:
    raw = str(state.get("WorkingDirectory") or "").strip()

    if not raw:
        return "unset"

    path = Path(raw)

    if path.resolve(strict=False) == root.resolve(strict=False):
        return "source-root"

    if _is_within(path, root):
        return "inside-source"

    return "outside-source"


def _event_kinds(mask: int) -> tuple[str, ...]:
    return tuple(
        name
        for flag, name in EVENT_NAMES
        if mask & flag
    )


def parse_inotify_buffer(data: bytes):
    offset = 0

    while offset + EVENT_STRUCT.size <= len(data):
        wd, mask, cookie, name_length = EVENT_STRUCT.unpack_from(
            data,
            offset,
        )
        offset += EVENT_STRUCT.size

        if offset + name_length > len(data):
            raise ValueError("truncated inotify event buffer")

        raw_name = data[offset:offset + name_length]
        offset += name_length
        name = raw_name.split(b"\0", 1)[0].decode(
            "utf-8",
            errors="surrogateescape",
        )

        yield wd, mask, cookie, name


def redacted_path_evidence(
    path: Path,
    root: Path,
    tracked: set[str],
) -> str:
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))

    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return "outside-source"

    if relative in tracked:
        return f"tracked:{relative}"

    parts = Path(relative).parts
    top = parts[0] if parts else "<root>"

    if top not in SAFE_TOP_LEVELS:
        top = "<other>"

    suffix = Path(relative).suffix.lower() or "<none>"
    digest = hashlib.sha256(
        relative.encode(
            "utf-8",
            errors="surrogateescape",
        )
    ).hexdigest()[:12]

    return (
        f"untracked:top={top} suffix={suffix} "
        f"path-digest={digest}"
    )


class RecursiveInotify:
    def __init__(
        self,
        root: Path,
        *,
        tracked: set[str] | None = None,
        evidence_limit: int = 50,
    ) -> None:
        if platform.system() != "Linux":
            raise RuntimeError("Linux inotify is required")

        self.root = Path(root).resolve()
        self.tracked = set(tracked or ())
        self.evidence_limit = max(1, int(evidence_limit))
        self._libc = ctypes.CDLL(None, use_errno=True)
        self._fd = self._init_fd()
        self._wd_to_path: dict[int, Path] = {}
        self._path_to_wd: dict[Path, int] = {}
        self._lock = threading.Lock()
        self._current_stage = "preflight"
        self._stage_counts = Counter()
        self._stage_kind_counts = defaultdict(Counter)
        self._evidence: list[tuple[str, str, str]] = []
        self._evidence_seen = set()
        self._overflow = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._add_recursive(self.root)

    def _init_fd(self) -> int:
        init1 = getattr(self._libc, "inotify_init1", None)

        if init1 is None:
            raise RuntimeError("inotify_init1 unavailable")

        init1.argtypes = [ctypes.c_int]
        init1.restype = ctypes.c_int
        fd = init1(os.O_NONBLOCK | os.O_CLOEXEC)

        if fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))

        return fd

    def _add_watch(self, directory: Path) -> None:
        directory = Path(directory)

        if directory in self._path_to_wd:
            return

        add_watch = self._libc.inotify_add_watch
        add_watch.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        add_watch.restype = ctypes.c_int
        encoded = os.fsencode(directory)
        wd = add_watch(self._fd, encoded, WATCH_MASK)

        if wd < 0:
            err = ctypes.get_errno()
            raise OSError(
                err,
                f"inotify watch failed: {os.strerror(err)}",
            )

        self._wd_to_path[wd] = directory
        self._path_to_wd[directory] = wd

    def _add_recursive(self, root: Path) -> None:
        stack = [Path(root)]

        while stack:
            directory = stack.pop()
            self._add_watch(directory)

            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))

    def start(self) -> None:
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._loop,
            name="path001d2-inotify",
            daemon=True,
        )
        self._thread.start()

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._current_stage = str(stage)

    def _record(self, path: Path, mask: int) -> None:
        kinds = _event_kinds(mask)

        if not kinds:
            return

        with self._lock:
            stage = self._current_stage
            self._stage_counts[stage] += 1

            for kind in kinds:
                self._stage_kind_counts[stage][kind] += 1

            evidence = redacted_path_evidence(
                path,
                self.root,
                self.tracked,
            )

            for kind in kinds:
                marker = (stage, kind, evidence)

                if marker in self._evidence_seen:
                    continue

                self._evidence_seen.add(marker)

                if len(self._evidence) < self.evidence_limit:
                    self._evidence.append(marker)

    def _consume(self) -> None:
        while True:
            try:
                data = os.read(self._fd, 1024 * 1024)
            except BlockingIOError:
                return
            except OSError as exc:
                if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                    return
                raise

            if not data:
                return

            for wd, mask, _cookie, name in parse_inotify_buffer(data):
                if mask & IN_Q_OVERFLOW:
                    with self._lock:
                        self._overflow = True
                    continue

                base = self._wd_to_path.get(wd)

                if base is None:
                    continue

                path = base / name if name else base

                if mask & MUTATION_MASK:
                    self._record(path, mask)

                if (
                    mask & IN_ISDIR
                    and mask & (IN_CREATE | IN_MOVED_TO)
                ):
                    try:
                        if path.is_dir():
                            self._add_recursive(path)
                    except OSError:
                        # The end-of-session snapshot is the second detection
                        # layer; an inaccessible just-created directory still
                        # produced a mutation event above.
                        pass

                if mask & IN_IGNORED:
                    old = self._wd_to_path.pop(wd, None)

                    if old is not None:
                        self._path_to_wd.pop(old, None)

    def _loop(self) -> None:
        while not self._stop.is_set():
            readable, _, _ = select.select(
                [self._fd],
                [],
                [],
                0.25,
            )

            if readable:
                try:
                    self._consume()
                except OSError:
                    with self._lock:
                        self._overflow = True
                    return

    def stage_count(self, stage: str) -> int:
        with self._lock:
            return int(self._stage_counts.get(stage, 0))

    def total_count(self) -> int:
        with self._lock:
            return int(sum(self._stage_counts.values()))

    def overflowed(self) -> bool:
        with self._lock:
            return bool(self._overflow)

    def evidence(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._evidence)

    def close(self) -> None:
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

        try:
            self._consume()
        except OSError:
            pass

        os.close(self._fd)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def evaluate_gate(
    *,
    covered: set[str],
    skipped: set[str],
    event_count: int,
    overflowed: bool,
    delta: dict[str, int],
    service_identity_ok: bool,
    service_active_ok: bool,
    restart_observed: bool,
) -> tuple[bool, list[str]]:
    reasons = []
    accounted_for = set(covered) | set(skipped)
    missing = set(SCENARIO_NAMES) - accounted_for

    if missing:
        reasons.append(f"scenario-coverage-missing={len(missing)}")

    if skipped:
        reasons.append(f"scenario-skipped={len(skipped)}")

    if event_count:
        reasons.append(f"worktree-events={int(event_count)}")

    if overflowed:
        reasons.append("inotify-overflow=1")

    delta_total = sum(int(value) for value in delta.values())

    if delta_total:
        reasons.append(f"snapshot-delta={delta_total}")

    if not service_identity_ok:
        reasons.append("service-identity-mismatch=1")

    if not service_active_ok:
        reasons.append("service-not-active=1")

    if not restart_observed:
        reasons.append("restart-not-observed=1")

    return not reasons, reasons


def _prompt_scenario(name: str, instruction: str) -> str:
    print()
    print(f"[PATH-001D.2] scenario: {name}")
    print(instruction)
    print(
        "Type 'done' after exercising it, 'skip' if it cannot be "
        "exercised on this installation, or 'abort'."
    )

    while True:
        answer = input("> ").strip().lower()

        if answer in {"done", "skip", "abort"}:
            return answer

        print("Enter exactly: done, skip, or abort")


def _service_checkpoint(unit: str) -> tuple[dict[str, str], bool, bool]:
    state = service_state(unit)
    return (
        state,
        service_active(state),
        service_identity_matches(state),
    )


def run(args) -> int:
    root = Path(args.root).resolve()

    if platform.system() != "Linux":
        print(
            "PATH-001D.2 stopped: current live tracer requires "
            "Linux/systemd/inotify."
        )
        return 2

    if exact_head(root) != str(args.expected_head).strip():
        print(
            "PATH-001D.2 stopped: authoritative source mismatch; "
            "no runtime data read."
        )
        return 2

    tracked = tracked_paths(root)
    initial_state, initial_active, initial_identity = (
        _service_checkpoint(args.unit)
    )

    print("PATH-001D.2 live worktree trace preflight.")
    print("authoritative-head-match: yes")
    print(
        "service-active-before: "
        + ("yes" if initial_active else "no")
    )
    print(
        "service-identity-match-before: "
        + ("yes" if initial_identity else "no")
    )
    print(
        "service-working-directory: "
        + working_directory_class(initial_state, root)
    )
    print("runtime-file-contents-read: no")
    print("credential-values-read: no")
    print("destructive-changes-performed-by-tool: no")
    print(
        "supplemental-proof-required: "
        "package-runtime-paths matter-repair-fixture"
    )

    if not initial_active or not initial_identity:
        print("PATH-001D.2 live gate: BLOCKED")
        return 1

    print()
    print(
        "Do not edit, commit, extract files into, or otherwise mutate "
        "the checkout while the trace is running."
    )
    print(
        "The tracer watches the entire checkout. Any mutation from any "
        "process blocks the gate."
    )

    try:
        before = metadata_snapshot(root)
    except OSError as exc:
        print(
            "PATH-001D.2 stopped: baseline metadata snapshot failed: "
            f"{type(exc).__name__}"
        )
        return 2

    covered = set()
    skipped = set()
    aborted = False
    initial_pid = service_pid(initial_state)
    restart_pid = initial_pid
    all_service_active = initial_active
    all_identity_match = initial_identity

    try:
        watcher = RecursiveInotify(
            root,
            tracked=tracked,
        )
    except (OSError, RuntimeError) as exc:
        print(
            "PATH-001D.2 stopped: recursive inotify setup failed: "
            f"{type(exc).__name__}"
        )
        return 2

    with watcher:
        for name, instruction in SCENARIOS:
            watcher.set_stage(name)
            answer = _prompt_scenario(name, instruction)

            if answer == "abort":
                aborted = True
                break

            if answer == "done":
                covered.add(name)
            else:
                skipped.add(name)

            try:
                state, active_ok, identity_ok = _service_checkpoint(
                    args.unit
                )
            except (OSError, subprocess.CalledProcessError):
                active_ok = False
                identity_ok = False
                state = {}

            all_service_active = all_service_active and active_ok
            all_identity_match = all_identity_match and identity_ok

            if name == "startup-restart":
                restart_pid = service_pid(state)

            print(
                f"scenario-result: {name} "
                f"operator={answer} "
                f"service-active={'yes' if active_ok else 'no'} "
                f"identity-match={'yes' if identity_ok else 'no'} "
                f"worktree-events={watcher.stage_count(name)}"
            )

        # Give queued close-write/move events a chance to drain before
        # taking the final metadata snapshot.
        time.sleep(0.35)

    try:
        after = metadata_snapshot(root)
    except OSError as exc:
        print(
            "PATH-001D.2 stopped: final metadata snapshot failed: "
            f"{type(exc).__name__}"
        )
        return 2

    delta = snapshot_delta(before, after)
    restart_observed = (
        initial_pid > 0
        and restart_pid > 0
        and restart_pid != initial_pid
    )
    event_count = watcher.total_count()
    overflowed = watcher.overflowed()

    if aborted:
        skipped.update(
            set(SCENARIO_NAMES)
            - covered
            - skipped
        )

    passed, reasons = evaluate_gate(
        covered=covered,
        skipped=skipped,
        event_count=event_count,
        overflowed=overflowed,
        delta=delta,
        service_identity_ok=all_identity_match,
        service_active_ok=all_service_active,
        restart_observed=restart_observed,
    )

    print()
    print("PATH-001D.2 live worktree trace completed.")
    print(
        f"scenario-coverage: covered={len(covered)}/{len(SCENARIOS)} "
        f"skipped={len(skipped)}"
    )
    print(
        "restart-observed: "
        + ("yes" if restart_observed else "no")
    )
    print(
        "service-active-all-checkpoints: "
        + ("yes" if all_service_active else "no")
    )
    print(
        "service-identity-match-all-checkpoints: "
        + ("yes" if all_identity_match else "no")
    )
    print(f"worktree-mutation-events: {event_count}")
    print(
        "snapshot-delta: "
        f"added={delta['added']} "
        f"removed={delta['removed']} "
        f"changed={delta['changed']}"
    )
    print(
        "inotify-overflow: "
        + ("yes" if overflowed else "no")
    )
    print("runtime-file-contents-read: no")
    print("credential-values-read: no")
    print("destructive-changes-performed-by-tool: no")
    print(
        "PATH-001D.2 live gate: "
        + ("PASS" if passed else "BLOCKED")
    )

    if not passed:
        for reason in reasons:
            print("BLOCKED:", reason)

        if args.details and event_count:
            for stage, kind, evidence in watcher.evidence():
                print(
                    f"mutation-evidence: stage={stage} "
                    f"kind={kind} {evidence}"
                )

        return 1

    return 0


def main(argv=None) -> int:
    try:
        return run(_parser().parse_args(argv))
    except KeyboardInterrupt:
        print()
        print("PATH-001D.2 stopped: operator aborted; gate not satisfied.")
        return 130
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            "PATH-001D.2 stopped: live trace failed closed: "
            f"{type(exc).__name__}"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
