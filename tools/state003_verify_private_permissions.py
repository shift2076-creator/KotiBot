#!/usr/bin/env python3
"""STATE-003 metadata-only private runtime permission verifier."""

from __future__ import annotations

import argparse
import grp
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys


SYSTEMCTL_PROPERTIES = (
    "ActiveState",
    "SubState",
    "MainPID",
    "User",
    "Group",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "STATE-003 private runtime metadata verifier. "
            "Reads no runtime file contents."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )
    parser.add_argument(
        "--unit",
        default="kotibot.service",
        help="systemd service unit (default: kotibot.service)",
    )
    parser.add_argument(
        "--expected-head",
        required=True,
        help="exact authoritative Git HEAD required before verification",
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


def process_identity(pid: int) -> tuple[int, int]:
    uid = None
    gid = None
    status_path = Path("/proc") / str(pid) / "status"

    with status_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("Uid:"):
                fields = line.split()

                if len(fields) >= 2:
                    uid = int(fields[1])
            elif line.startswith("Gid:"):
                fields = line.split()

                if len(fields) >= 2:
                    gid = int(fields[1])

            if uid is not None and gid is not None:
                return uid, gid

    raise RuntimeError("service process identity metadata unavailable")


def service_identity_status(
    state: dict[str, str],
) -> tuple[bool, bool, int, int]:
    try:
        pid = int(state.get("MainPID") or 0)
    except ValueError:
        pid = 0

    active = (
        state.get("ActiveState") == "active"
        and state.get("SubState") == "running"
        and pid > 0
    )

    if not active:
        return False, False, -1, -1

    process_uid, process_gid = process_identity(pid)
    configured_user = str(state.get("User") or "").strip()
    configured_group = str(state.get("Group") or "").strip()

    if configured_user:
        user_record = pwd.getpwnam(configured_user)
        configured_uid = user_record.pw_uid
        default_gid = user_record.pw_gid
    else:
        configured_uid = 0
        default_gid = 0

    configured_gid = (
        grp.getgrnam(configured_group).gr_gid
        if configured_group
        else default_gid
    )
    configured_match = (
        process_uid == configured_uid
        and process_gid == configured_gid
    )
    current_match = (
        os.geteuid() == process_uid
        and os.getegid() == process_gid
    )

    return configured_match, current_match, process_uid, process_gid


def private_runtime_roots(paths) -> tuple[Path, ...]:
    candidates = (
        paths.state_root,
        paths.security_state_dir,
        paths.device_credential_state_dir,
        paths.matter_protected_dir,
        paths.activity_log_dir,
        paths.security_log_dir,
        paths.notification_log_dir,
        paths.recording_dir,
    )
    roots = []

    for candidate in candidates:
        candidate = Path(candidate).resolve(strict=False)

        if any(
            candidate == root or root in candidate.parents
            for root in roots
        ):
            continue

        roots.append(candidate)

    return tuple(roots)


def inspect_private_roots(
    roots: tuple[Path, ...],
    *,
    expected_uid: int,
    expected_gid: int,
) -> dict[str, int]:
    result = {
        "roots": len(roots),
        "missing_roots": 0,
        "entries": 0,
        "directories": 0,
        "files": 0,
        "symlinks": 0,
        "non_regular": 0,
        "wrong_owner": 0,
        "wrong_directory_mode": 0,
        "wrong_file_mode": 0,
        "inspection_errors": 0,
    }

    def inspect_info(info, *, directory: bool) -> None:
        result["entries"] += 1

        if (
            info.st_uid != expected_uid
            or info.st_gid != expected_gid
        ):
            result["wrong_owner"] += 1

        mode = stat.S_IMODE(info.st_mode)

        if directory:
            result["directories"] += 1

            if mode != 0o700:
                result["wrong_directory_mode"] += 1
        else:
            result["files"] += 1

            if mode != 0o600:
                result["wrong_file_mode"] += 1

    for raw_root in roots:
        root = Path(raw_root)

        try:
            root_info = root.lstat()
        except FileNotFoundError:
            result["missing_roots"] += 1
            continue
        except OSError:
            result["inspection_errors"] += 1
            continue

        if stat.S_ISLNK(root_info.st_mode):
            result["symlinks"] += 1
            continue

        if not stat.S_ISDIR(root_info.st_mode):
            result["non_regular"] += 1
            continue

        inspect_info(root_info, directory=True)
        stack = [root]

        while stack:
            directory = stack.pop()

            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError:
                            result["inspection_errors"] += 1
                            continue

                        if stat.S_ISLNK(info.st_mode):
                            result["symlinks"] += 1
                        elif stat.S_ISDIR(info.st_mode):
                            inspect_info(info, directory=True)
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(info.st_mode):
                            inspect_info(info, directory=False)
                        else:
                            result["non_regular"] += 1
            except OSError:
                result["inspection_errors"] += 1

    return result


def run(args) -> int:
    root = Path(args.root).resolve(strict=False)

    if exact_head(root) != str(args.expected_head).strip():
        print(
            "STATE-003 stopped: authoritative source mismatch; "
            "no runtime metadata read."
        )
        return 2

    if os.name == "nt" or not Path("/proc").is_dir():
        raise RuntimeError(
            "STATE-003 live verification requires Linux systemd"
        )

    state = service_state(args.unit)
    (
        configured_identity_match,
        current_identity_match,
        service_uid,
        service_gid,
    ) = service_identity_status(state)

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from server_core.paths import build_runtime_paths

    paths = build_runtime_paths(root)
    result = inspect_private_roots(
        private_runtime_roots(paths),
        expected_uid=service_uid,
        expected_gid=service_gid,
    )
    metadata_failures = sum(
        result[name]
        for name in (
            "missing_roots",
            "symlinks",
            "non_regular",
            "wrong_owner",
            "wrong_directory_mode",
            "wrong_file_mode",
            "inspection_errors",
        )
    )
    blocked = (
        not configured_identity_match
        or not current_identity_match
        or metadata_failures > 0
    )

    print("STATE-003 private runtime verification completed.")
    print("authoritative-head-match: yes")
    print(
        "service-configured-identity-match: "
        + ("yes" if configured_identity_match else "no")
    )
    print(
        "verifier-running-as-service-identity: "
        + ("yes" if current_identity_match else "no")
    )
    print(f"private-roots-inspected: {result['roots']}")
    print(f"metadata-entries-inspected: {result['entries']}")
    print(f"private-directories: {result['directories']}")
    print(f"private-files: {result['files']}")
    print(f"missing-private-roots: {result['missing_roots']}")
    print(f"symbolic-links: {result['symlinks']}")
    print(f"non-regular-entries: {result['non_regular']}")
    print(f"ownership-mismatches: {result['wrong_owner']}")
    print(
        "private-directory-mode-mismatches: "
        f"{result['wrong_directory_mode']}"
    )
    print(
        "private-file-mode-mismatches: "
        f"{result['wrong_file_mode']}"
    )
    print(f"metadata-inspection-errors: {result['inspection_errors']}")
    print("runtime-file-contents-read: no")
    print("credential-values-read: no")
    print("destructive-changes-performed: no")
    print(
        "STATE-003 live gate: "
        + ("BLOCKED" if blocked else "PASS")
    )

    return 1 if blocked else 0


def main(argv=None) -> int:
    try:
        return run(_parser().parse_args(argv))
    except (
        KeyError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        ValueError,
    ) as exc:
        print(
            "STATE-003 stopped: private runtime verification "
            f"failed closed: {type(exc).__name__}; "
            "no runtime file contents read."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
