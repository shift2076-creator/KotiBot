#!/usr/bin/env python3
"""Read-only, value-free SEC-007 virtual-environment credential audit.

Run this tool with a trusted system Python in isolated mode.  The selected
virtual environment is inspected only as inert filesystem data; no interpreter,
package, activation script, ``.pth`` file, or other content from it is executed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import Iterable


SOURCE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENV_ROOT = SOURCE_ROOT / ".venv"
DEFAULT_CREDENTIAL_DIRECTORY = Path("/etc/kotibot/credentials.d")

MAX_CREDENTIAL_FILES = 64
MAX_CREDENTIAL_BYTES = 1024 * 1024
MAX_VENV_FILES = 250_000
MAX_VENV_BYTES = 4 * 1024 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MIN_EXACT_VALUE_BYTES = 8

# Standalone usernames are identifiers rather than usable credentials.  They
# are covered when present inside a complete credential document, but are not
# searched as short independent byte strings because common values such as
# "admin" would not establish credential contamination.
IDENTIFIER_ONLY_CREDENTIAL_NAMES = frozenset({
    "tapo-username",
    "tapo-camera-username",
})

# These are the retired environment authorities removed by SEC-004/SEC-006.
# An assignment in executable or configuration content is a contamination
# signal even if its value no longer matches the current protected credential.
# Installed package documentation and wheel metadata may contain inert usage
# examples; those references are counted separately and never hide an exact
# protected-value match.
LEGACY_CREDENTIAL_ENVIRONMENTS = (
    "TAPO_USERNAME",
    "TAPO_PASSWORD",
    "TAPO_CAMERA_USERNAME",
    "TAPO_CAMERA_PASSWORD",
    "KOTIBOT_CLOUDFLARE_API_TOKEN",
    "KOTIBOT_CAMERA_TALK_TURN_USERNAME",
    "KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL",
    "KOTIBOT_CAMERA_TALK_ICE_SERVERS",
    "KOTIBOT_DASHBOARD_EMAIL",
    "KOTIBOT_DASHBOARD_PASSWORD",
)

_ASSIGNMENT_PATTERN = re.compile(
    rb"(?<![A-Z0-9_])(?:"
    + rb"|".join(
        re.escape(name.encode("ascii"))
        for name in LEGACY_CREDENTIAL_ENVIRONMENTS
    )
    + rb")[\"']?\]?[ \t]*(?:=|:)",
)

_PROTECTED_JSON_FIELDS = frozenset({
    "accesskey",
    "apikey",
    "apitoken",
    "authorization",
    "clientemail",
    "clientid",
    "credential",
    "dashboardkey",
    "dashboardkeyhash",
    "dashboardpasswordhash",
    "fcmtoken",
    "password",
    "passwordhash",
    "privatekey",
    "privatekeyid",
    "secret",
    "sessionsecret",
    "token",
    "tokenhash",
    "username",
})


class AuditError(RuntimeError):
    """A value-free failure that prevents a reliable audit decision."""


@dataclass(frozen=True)
class CredentialInventory:
    files: int
    needles: tuple[bytes, ...]


@dataclass(frozen=True)
class AuditResult:
    credential_files: int
    protected_needles: int
    venv_files: int
    venv_bytes: int
    symlinks_skipped: int
    credential_match_files: int
    legacy_assignment_files: int
    package_reference_files: int

    @property
    def contaminated(self) -> bool:
        return bool(
            self.credential_match_files
            or self.legacy_assignment_files
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect .venv as inert data for current protected credential "
            "matches and retired credential-environment assignments."
        ),
    )
    parser.add_argument(
        "--venv-root",
        type=Path,
        default=DEFAULT_VENV_ROOT,
        help="absolute virtual-environment root to inspect",
    )
    parser.add_argument(
        "--credential-directory",
        type=Path,
        default=DEFAULT_CREDENTIAL_DIRECTORY,
        help="absolute manager-owned protected credential directory",
    )
    return parser


def _absolute(path: Path, label: str) -> Path:
    candidate = Path(path).expanduser()

    if not candidate.is_absolute():
        raise AuditError(f"{label} must be absolute")

    return candidate


def _directory_metadata(
    path: Path,
    label: str,
    *,
    private: bool = False,
    expected_uid: int | None = None,
) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AuditError(f"{label} could not be inspected") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise AuditError(f"{label} must not be a symbolic link")

    if not stat.S_ISDIR(metadata.st_mode):
        raise AuditError(f"{label} must be a directory")

    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise AuditError(f"{label} permissions are not private")

    if expected_uid is not None and metadata.st_uid != expected_uid:
        raise AuditError(f"{label} ownership is invalid")

    return metadata


def _open_regular_file(
    path: Path,
    label: str,
    *,
    max_bytes: int,
    private: bool = False,
    expected_uid: int | None = None,
):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AuditError(f"{label} could not be opened safely") from exc

    try:
        metadata = os.fstat(descriptor)

        if not stat.S_ISREG(metadata.st_mode):
            raise AuditError(f"{label} must be a regular file")

        if metadata.st_size > max_bytes:
            raise AuditError(f"{label} exceeds the audit size limit")

        if private and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise AuditError(f"{label} permissions are not private")

        if expected_uid is not None and metadata.st_uid != expected_uid:
            raise AuditError(f"{label} ownership is invalid")

        return os.fdopen(descriptor, "rb", closefd=True), metadata.st_size
    except BaseException:
        os.close(descriptor)
        raise


def _compact_key(value: object) -> str:
    return "".join(
        character
        for character in str(value or "").lower()
        if character.isalnum()
    )


def _encoded_json_value(value: object) -> bytes | None:
    if isinstance(value, str):
        try:
            return value.strip().encode("utf-8")
        except UnicodeEncodeError as exc:
            raise AuditError(
                "Protected credential JSON is not valid UTF-8"
            ) from exc

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        return None


def _protected_json_values(value: object) -> Iterable[bytes]:
    if isinstance(value, dict):
        for key, child in value.items():
            compact = _compact_key(key)

            if compact in _PROTECTED_JSON_FIELDS:
                encoded = _encoded_json_value(child)

                if encoded:
                    if len(encoded) < MIN_EXACT_VALUE_BYTES:
                        raise AuditError(
                            "A protected credential value is too short for "
                            "reliable exact matching"
                        )
                    yield encoded

            yield from _protected_json_values(child)
        return

    if isinstance(value, list):
        for child in value:
            yield from _protected_json_values(child)


def _credential_payload(path: Path, expected_uid: int | None) -> bytes:
    stream, _ = _open_regular_file(
        path,
        "Protected credential file",
        max_bytes=MAX_CREDENTIAL_BYTES,
        private=True,
        expected_uid=expected_uid,
    )

    with stream:
        payload = stream.read(MAX_CREDENTIAL_BYTES + 1)

    if not payload:
        raise AuditError("Protected credential file is empty")

    return payload


def load_credential_inventory(
    credential_directory: Path,
    *,
    expected_uid: int | None,
) -> CredentialInventory:
    root = _absolute(
        credential_directory,
        "Protected credential directory",
    )
    _directory_metadata(
        root,
        "Protected credential directory",
        private=True,
        expected_uid=expected_uid,
    )

    try:
        children = sorted(root.iterdir(), key=lambda child: child.name)
    except OSError as exc:
        raise AuditError(
            "Protected credential directory could not be enumerated"
        ) from exc

    if not children:
        raise AuditError("Protected credential directory is empty")

    if len(children) > MAX_CREDENTIAL_FILES:
        raise AuditError("Protected credential file count exceeds the limit")

    needles: set[bytes] = set()

    for path in children:
        payload = _credential_payload(path, expected_uid)
        stripped = payload.strip()
        document: object | None = None

        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        if path.name not in IDENTIFIER_ONLY_CREDENTIAL_NAMES:
            if len(stripped) < MIN_EXACT_VALUE_BYTES:
                raise AuditError(
                    "A protected credential value is too short for reliable "
                    "exact matching"
                )
            needles.add(stripped)

        if document is not None:
            normalized = _encoded_json_value(document)

            if normalized and len(normalized) >= MIN_EXACT_VALUE_BYTES:
                needles.add(normalized)

            needles.update(_protected_json_values(document))

    if not needles:
        raise AuditError("No reliably comparable credential material exists")

    return CredentialInventory(
        files=len(children),
        needles=tuple(sorted(needles, key=lambda value: (len(value), value))),
    )


def _validate_venv_root(venv_root: Path) -> Path:
    root = _absolute(venv_root, "Virtual-environment root")
    _directory_metadata(root, "Virtual-environment root")

    marker = root / "pyvenv.cfg"
    stream, _ = _open_regular_file(
        marker,
        "Virtual-environment marker",
        max_bytes=64 * 1024,
    )
    stream.close()
    return root


def _scan_stream(
    stream,
    needles: tuple[bytes, ...],
) -> tuple[int, bool, bool]:
    overlap = max(
        max((len(needle) for needle in needles), default=1),
        max(len(name) for name in LEGACY_CREDENTIAL_ENVIRONMENTS) + 16,
    ) - 1
    tail = b""
    size = 0
    credential_match = False
    assignment_match = False

    while True:
        chunk = stream.read(READ_CHUNK_BYTES)

        if not chunk:
            break

        size += len(chunk)
        candidate = tail + chunk

        if not credential_match:
            credential_match = any(
                needle in candidate
                for needle in needles
            )

        if not assignment_match:
            assignment_match = bool(_ASSIGNMENT_PATTERN.search(candidate))

        tail = candidate[-overlap:] if overlap else b""

    return size, credential_match, assignment_match


def _is_non_executable_package_reference(
    venv_root: Path,
    path: Path,
) -> bool:
    try:
        relative_parts = path.relative_to(venv_root).parts
    except ValueError:
        return False

    for package_directory in ("site-packages", "dist-packages"):
        try:
            index = relative_parts.index(package_directory)
        except ValueError:
            continue

        package_parts = relative_parts[index + 1:]

        if len(package_parts) == 1:
            return package_parts[0].lower() in {
                "readme",
                "readme.md",
                "readme.rst",
                "readme.txt",
            }

        if len(package_parts) == 2:
            distribution, filename = package_parts
            return (
                distribution.lower().endswith(".dist-info")
                and filename.lower() == "metadata"
            )

    return False


def scan_virtualenv(
    venv_root: Path,
    needles: tuple[bytes, ...],
) -> tuple[int, int, int, int, int, int]:
    root = _validate_venv_root(venv_root)
    files = 0
    total_bytes = 0
    symlinks = 0
    credential_match_files = 0
    legacy_assignment_files = 0
    package_reference_files = 0

    try:
        walker = os.walk(root, topdown=True, followlinks=False)

        for directory, names, filenames in walker:
            safe_names = []

            for name in names:
                child = Path(directory) / name

                try:
                    metadata = child.lstat()
                except OSError as exc:
                    raise AuditError(
                        "Virtual-environment entry could not be inspected"
                    ) from exc

                if stat.S_ISLNK(metadata.st_mode):
                    symlinks += 1
                    continue

                if not stat.S_ISDIR(metadata.st_mode):
                    raise AuditError(
                        "Virtual-environment tree contains an invalid entry"
                    )

                safe_names.append(name)

            names[:] = safe_names

            for name in filenames:
                path = Path(directory) / name

                try:
                    metadata = path.lstat()
                except OSError as exc:
                    raise AuditError(
                        "Virtual-environment entry could not be inspected"
                    ) from exc

                if stat.S_ISLNK(metadata.st_mode):
                    symlinks += 1
                    continue

                files += 1

                if files > MAX_VENV_FILES:
                    raise AuditError(
                        "Virtual-environment file count exceeds the limit"
                    )

                remaining = MAX_VENV_BYTES - total_bytes

                if remaining < 0 or metadata.st_size > remaining:
                    raise AuditError(
                        "Virtual-environment content exceeds the audit limit"
                    )

                stream, expected_size = _open_regular_file(
                    path,
                    "Virtual-environment file",
                    max_bytes=remaining,
                )

                with stream:
                    size, credential_match, assignment_match = _scan_stream(
                        stream,
                        needles,
                    )

                if size != expected_size:
                    raise AuditError(
                        "Virtual-environment changed during the audit"
                    )

                total_bytes += size
                credential_match_files += int(credential_match)

                if assignment_match:
                    if _is_non_executable_package_reference(root, path):
                        package_reference_files += 1
                    else:
                        legacy_assignment_files += 1
    except AuditError:
        raise
    except OSError as exc:
        raise AuditError(
            "Virtual-environment tree could not be scanned"
        ) from exc

    return (
        files,
        total_bytes,
        symlinks,
        credential_match_files,
        legacy_assignment_files,
        package_reference_files,
    )


def audit_virtualenv(
    venv_root: Path,
    credential_directory: Path,
    *,
    expected_credential_uid: int | None,
) -> AuditResult:
    inventory = load_credential_inventory(
        credential_directory,
        expected_uid=expected_credential_uid,
    )
    (
        files,
        total_bytes,
        symlinks,
        credential_matches,
        assignment_matches,
        package_references,
    ) = scan_virtualenv(venv_root, inventory.needles)

    return AuditResult(
        credential_files=inventory.files,
        protected_needles=len(inventory.needles),
        venv_files=files,
        venv_bytes=total_bytes,
        symlinks_skipped=symlinks,
        credential_match_files=credential_matches,
        legacy_assignment_files=assignment_matches,
        package_reference_files=package_references,
    )


def _print_result(result: AuditResult) -> None:
    print("SEC-007 VIRTUAL-ENVIRONMENT CREDENTIAL AUDIT")
    print("Result: " + ("FAIL" if result.contaminated else "PASS"))
    print(
        "Decision: "
        + (
            "SEC-007 REBUILD REQUIRED"
            if result.contaminated
            else "SEC-007 NOT TRIGGERED"
        )
    )
    print("Privacy: no credential values or identifiers were displayed.")
    print("Execution: virtual-environment content was not executed.")
    print(f"Protected credential files: {result.credential_files}")
    print(f"Protected comparison values: {result.protected_needles}")
    print(f"Virtual-environment files scanned: {result.venv_files}")
    print(f"Virtual-environment bytes scanned: {result.venv_bytes}")
    print(f"Symbolic links skipped: {result.symlinks_skipped}")
    print(
        "Files matching protected credential material: "
        f"{result.credential_match_files}"
    )
    print(
        "Executable/configuration files containing retired assignments: "
        f"{result.legacy_assignment_files}"
    )
    print(
        "Non-executable package reference files: "
        f"{result.package_reference_files}"
    )
    print("Destructive action performed: NO")


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        print("SEC-007 stopped: this protected audit adapter requires Linux")
        print("Privacy: no credential values or identifiers were displayed.")
        print("Destructive action performed: NO")
        return 2

    if os.geteuid() != 0:
        print("SEC-007 stopped: run this protected audit as root")
        print("Privacy: no credential values or identifiers were displayed.")
        print("Destructive action performed: NO")
        return 2

    args = _parser().parse_args(argv)

    try:
        result = audit_virtualenv(
            args.venv_root,
            args.credential_directory,
            expected_credential_uid=0,
        )
    except AuditError as exc:
        print(f"SEC-007 stopped: {exc}")
        print("Privacy: no credential values or identifiers were displayed.")
        print("Destructive action performed: NO")
        return 2

    _print_result(result)
    return 1 if result.contaminated else 0


if __name__ == "__main__":
    raise SystemExit(main())
