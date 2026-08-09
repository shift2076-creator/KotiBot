#!/usr/bin/env python3
"""Write a private, value-free SEC-001C history and release inventory.

The scanner inspects historical Git text blobs, tag snapshots, annotated tag
messages, and local archive text members. It retains only repository-relative
paths, artifact/member names, commit IDs, tag names, and sensitive identifier
names. Matching lines and values are never written to the report or stdout.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from typing import Iterable
import zipfile


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


REPORT_NAME = "SEC-001C_HISTORY_RELEASE_INVENTORY.md"
DEFAULT_MAX_TEXT_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_MEMBERS = 100_000

ZIP_SUFFIXES = (".zip", ".jar", ".whl", ".apk")
TAR_SUFFIXES = (
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)
UNSUPPORTED_ARCHIVE_SUFFIXES = (".7z", ".rar", ".tar.zst", ".tzst")
ARCHIVE_SUFFIXES = tuple(
    sorted(
        (*ZIP_SUFFIXES, *TAR_SUFFIXES, *UNSUPPORTED_ARCHIVE_SUFFIXES),
        key=len,
        reverse=True,
    )
)

SKIP_ARCHIVE_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}

RUNTIME_STATE_NAMES = {
    "activity_state.json",
    "android_home_state.json",
    "automations_state.json",
    "environment_state.json",
    "matter_device_state.json",
    "matter_state.json",
    "notification_queue.jsonl",
    "security_actions.json",
    "security_audit.jsonl",
    "security_state.json",
    "server_state.json",
    "tapo_device_state.json",
    "tapo_lighting_state.json",
}

SENSITIVE_DIRECTORY_NAMES = {
    "backups": "backup path",
    "camera_hls": "camera stream path",
    "chip_tool_storage": "Matter controller identity path",
    "chip_tool_subscription_storage": "Matter controller storage path",
    "credentials.d": "credential-store path",
    "recordings": "recording path",
    "videos": "recording path",
}

KEY_MATERIAL_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}

ASSIGNMENT_NAME_RE = re.compile(
    r"(?m)^[ \t]*(?:export[ \t]+)?"
    r"([A-Za-z_][A-Za-z0-9_.-]{0,127})[ \t]*[:=]"
)
QUOTED_KEY_RE = re.compile(
    r"(?m)(?:^|[{,\s])['\"]([A-Za-z_][A-Za-z0-9_.-]{0,127})"
    r"['\"][ \t]*[:=]"
)
NAMED_ATTRIBUTE_RE = re.compile(
    r"\bname[ \t]*=[ \t]*['\"]([A-Za-z_][A-Za-z0-9_.-]{0,127})['\"]"
)
GETENV_RE = re.compile(
    r"\b(?:getenv|environ\.get)[ \t]*\([ \t]*"
    r"['\"]([A-Za-z_][A-Za-z0-9_]{0,127})['\"]"
)
ENVIRON_INDEX_RE = re.compile(
    r"\benviron[ \t]*\[[ \t]*"
    r"['\"]([A-Za-z_][A-Za-z0-9_]{0,127})['\"][ \t]*\]"
)
MAPPING_GET_RE = re.compile(
    r"\.get[ \t]*\([ \t]*"
    r"['\"]([A-Za-z_][A-Za-z0-9_.-]{0,127})['\"]"
)
MAPPING_INDEX_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.-]*[ \t]*\[[ \t]*"
    r"['\"]([A-Za-z_][A-Za-z0-9_.-]{0,127})['\"][ \t]*\]"
)
KEYWORD_ARGUMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"([A-Za-z_][A-Za-z0-9_.-]{0,127})[ \t]*=(?!=)"
)


@dataclass(frozen=True, order=True)
class Finding:
    container: str
    item: str
    path_indicators: tuple[str, ...]
    key_names: tuple[str, ...]


@dataclass(frozen=True, order=True)
class TagRecord:
    name: str
    target_commit: str
    annotation_key_names: tuple[str, ...]
    status: str


@dataclass(frozen=True, order=True)
class ArchiveRecord:
    name: str
    format: str
    status: str
    member_count: int


@dataclass(frozen=True, order=True)
class ScanIssue:
    scope: str
    item: str
    status: str


@dataclass
class ScanResult:
    head_commit: str
    ref_count: int
    commit_count: int
    history_findings: list[Finding]
    tags: list[TagRecord]
    tag_findings: list[Finding]
    archives: list[ArchiveRecord]
    archive_findings: list[Finding]
    issues: list[ScanIssue]


def git_output(repository: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", os.fspath(repository), *arguments),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        command = " ".join(arguments[:2])
        raise RuntimeError(
            f"git {command} failed with exit code {result.returncode}"
        )
    return result.stdout


def is_archive(path: Path | PurePosixPath | str) -> bool:
    lowered = str(path).casefold()
    return any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def archive_format(path: Path | PurePosixPath | str) -> str:
    lowered = str(path).casefold()
    if lowered.endswith(ZIP_SUFFIXES):
        return "zip"
    if lowered.endswith(TAR_SUFFIXES):
        return "tar"
    return "unsupported"


def normalized_identifier(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def sensitive_identifier(name: str) -> bool:
    normalized = normalized_identifier(name)
    if not normalized:
        return False

    patterns = (
        r"(?:^|_)(?:password|passwd|passphrase)(?:_|$)",
        r"(?:^|_)(?:secret|secrets)(?:_|$)",
        r"(?:^|_)(?:credential|credentials)(?:_|$)",
        r"(?:^|_)(?:private_key|api_key|api_token)(?:_|$)",
        r"(?:^|_)(?:access_token|refresh_token|auth_token|bearer_token)(?:_|$)",
        r"(?:^|_)(?:client_secret|session_secret|session_key)(?:_|$)",
        r"(?:^|_)(?:signing_secret|signing_key|hmac_secret|hmac_key)(?:_|$)",
        r"(?:^|_)(?:enrollment_secret|enrollment_key|enrollment_token)(?:_|$)",
        r"(?:^|_)(?:fcm_token|registration_token|device_token)(?:_|$)",
        r"(?:^|_)(?:username|user_name)(?:_|$)",
        r"(?:^|_)(?:dashboard_email|account_email|client_email)(?:_|$)",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def extract_sensitive_names(data: bytes) -> tuple[str, ...]:
    """Return sensitive variable/key names while discarding all values."""
    if not data or b"\0" in data:
        return ()

    text = data.decode("utf-8", errors="replace")
    candidates: set[str] = set()

    for pattern in (
        ASSIGNMENT_NAME_RE,
        QUOTED_KEY_RE,
        NAMED_ATTRIBUTE_RE,
        GETENV_RE,
        ENVIRON_INDEX_RE,
        MAPPING_GET_RE,
        MAPPING_INDEX_RE,
        KEYWORD_ARGUMENT_RE,
    ):
        candidates.update(
            match.group(1)
            for match in pattern.finditer(text)
        )

    return tuple(
        sorted(
            (
                name
                for name in candidates
                if sensitive_identifier(name)
            ),
            key=str.casefold,
        )
    )


def sensitive_path_indicators(path_name: str) -> tuple[str, ...]:
    path = PurePosixPath(path_name.replace("\\", "/"))
    name = path.name.casefold()
    parts = {
        part.casefold()
        for part in path.parts
    }
    indicators: set[str] = set()

    if name.startswith(".env") and name != ".env.example":
        indicators.add("environment file")

    if any(
        word in name
        for word in ("credential", "password", "secret")
    ):
        indicators.add("credential-named path")

    if name in {
        "firebase-service-account.json",
        "google-services.json",
    }:
        indicators.add("service credential path")

    if name in RUNTIME_STATE_NAMES or (
        "_state.json" in name
        and not name.startswith("test_")
    ):
        indicators.add("runtime state path")

    if (
        path.suffix.casefold() in KEY_MATERIAL_SUFFIXES
        or name.startswith("id_rsa")
    ):
        indicators.add("private-key/certificate path")

    if (
        name.endswith((".bak", ".jsonl", ".log"))
        or ".bak." in name
        or ".jsonl." in name
        or ".log." in name
    ):
        indicators.add("backup or log path")

    if is_archive(path):
        indicators.add("archive artifact path")

    for directory, label in SENSITIVE_DIRECTORY_NAMES.items():
        if directory in parts:
            indicators.add(label)

    return tuple(
        sorted(
            indicators,
            key=str.casefold,
        )
    )


def safe_name(value: str) -> str:
    output: list[str] = []

    for character in value:
        codepoint = ord(character)

        if character == "`":
            output.append("\\x60")
        elif character == "|":
            output.append("\\|")
        elif character == "\n":
            output.append("\\n")
        elif character == "\r":
            output.append("\\r")
        elif character == "\t":
            output.append("\\t")
        elif codepoint < 32 or codepoint == 127:
            output.append(f"\\x{codepoint:02x}")
        elif 0xD800 <= codepoint <= 0xDFFF:
            output.append(f"\\u{codepoint:04x}")
        else:
            output.append(character)

    return "".join(output)


def code(value: str) -> str:
    return f"`{safe_name(value)}`"


def read_blob_names(
    repository: Path,
    object_id: str,
    max_text_bytes: int,
    cache: dict[str, tuple[tuple[str, ...], str]],
) -> tuple[tuple[str, ...], str]:
    cached = cache.get(object_id)
    if cached is not None:
        return cached

    try:
        object_type = git_output(
            repository,
            "cat-file",
            "-t",
            object_id,
        ).strip()

        if object_type != b"blob":
            result = ((), "non-blob")
        else:
            size = int(
                git_output(
                    repository,
                    "cat-file",
                    "-s",
                    object_id,
                )
            )

            if size > max_text_bytes:
                result = ((), "text-size-limit")
            else:
                data = git_output(
                    repository,
                    "cat-file",
                    "blob",
                    object_id,
                )
                result = (
                    extract_sensitive_names(data),
                    "scanned",
                )
    except (RuntimeError, ValueError):
        result = ((), "unreadable")

    cache[object_id] = result
    return result


def object_for_path(
    repository: Path,
    commit: str,
    path: str,
) -> str | None:
    try:
        return git_output(
            repository,
            "rev-parse",
            f"{commit}:{path}",
        ).decode("ascii").strip()
    except (RuntimeError, UnicodeDecodeError):
        return None


def changed_paths(
    repository: Path,
    commit: str,
) -> tuple[str, ...]:
    raw = git_output(
        repository,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        "--diff-filter=ACMT",
        "--no-renames",
        "-m",
        commit,
    )

    return tuple(
        os.fsdecode(item)
        for item in raw.split(b"\0")
        if item
    )


def tree_entries(
    repository: Path,
    commit: str,
) -> tuple[tuple[str, str], ...]:
    raw = git_output(
        repository,
        "ls-tree",
        "-rz",
        "--full-tree",
        commit,
    )

    entries: list[tuple[str, str]] = []

    for record in raw.split(b"\0"):
        if not record or b"\t" not in record:
            continue

        metadata, raw_path = record.split(b"\t", 1)
        fields = metadata.split()

        if len(fields) != 3 or fields[1] != b"blob":
            continue

        entries.append(
            (
                os.fsdecode(raw_path),
                fields[2].decode("ascii"),
            )
        )

    return tuple(entries)


def tag_records(repository: Path) -> tuple[TagRecord, ...]:
    raw = git_output(
        repository,
        "for-each-ref",
        "--format=%(refname:strip=2)%09%(objectname)%09%(objecttype)",
        "refs/tags",
    )

    records: list[TagRecord] = []

    for line in raw.decode(
        "utf-8",
        errors="replace",
    ).splitlines():
        fields = line.split("\t")

        if len(fields) != 3:
            continue

        name, object_id, object_type = fields

        try:
            target = git_output(
                repository,
                "rev-parse",
                f"refs/tags/{name}^{{commit}}",
            ).decode("ascii").strip()
            status = "scanned"
        except (RuntimeError, UnicodeDecodeError):
            target = "-"
            status = "not a commit"

        annotation_names: tuple[str, ...] = ()

        if object_type == "tag":
            try:
                annotation_names = extract_sensitive_names(
                    git_output(
                        repository,
                        "cat-file",
                        "tag",
                        object_id,
                    )
                )
            except RuntimeError:
                status = "annotation unreadable"

        records.append(
            TagRecord(
                name,
                target,
                annotation_names,
                status,
            )
        )

    return tuple(sorted(records))


def scan_git(
    repository: Path,
    max_text_bytes: int,
) -> tuple[
    str,
    int,
    int,
    list[Finding],
    list[TagRecord],
    list[Finding],
    list[ScanIssue],
]:
    head = git_output(
        repository,
        "rev-parse",
        "HEAD",
    ).decode("ascii").strip()

    commits = tuple(
        line.decode("ascii")
        for line in git_output(
            repository,
            "rev-list",
            "--all",
            "--topo-order",
            "--reverse",
        ).splitlines()
        if line
    )

    refs = tuple(
        line
        for line in git_output(
            repository,
            "for-each-ref",
            "--format=%(refname)",
        ).splitlines()
        if line
    )

    blob_cache: dict[
        str,
        tuple[tuple[str, ...], str],
    ] = {}

    history_findings: list[Finding] = []
    issues: list[ScanIssue] = []

    for commit in commits:
        for path in changed_paths(repository, commit):
            path_indicators = sensitive_path_indicators(path)
            object_id = object_for_path(
                repository,
                commit,
                path,
            )
            key_names: tuple[str, ...] = ()

            if object_id:
                key_names, status = read_blob_names(
                    repository,
                    object_id,
                    max_text_bytes,
                    blob_cache,
                )

                if status not in {
                    "scanned",
                    "non-blob",
                }:
                    issues.append(
                        ScanIssue(
                            "Git history",
                            f"{commit}:{path}",
                            status,
                        )
                    )

            if path_indicators or key_names:
                history_findings.append(
                    Finding(
                        commit,
                        path,
                        path_indicators,
                        key_names,
                    )
                )

    tags = list(tag_records(repository))
    tag_findings: list[Finding] = []

    for tag in tags:
        if tag.target_commit == "-":
            issues.append(
                ScanIssue(
                    "Git tag",
                    tag.name,
                    tag.status,
                )
            )
            continue

        for path, object_id in tree_entries(
            repository,
            tag.target_commit,
        ):
            path_indicators = sensitive_path_indicators(path)
            key_names, status = read_blob_names(
                repository,
                object_id,
                max_text_bytes,
                blob_cache,
            )

            if status not in {
                "scanned",
                "non-blob",
            }:
                issues.append(
                    ScanIssue(
                        "Git tag",
                        f"{tag.name}:{path}",
                        status,
                    )
                )

            if path_indicators or key_names:
                tag_findings.append(
                    Finding(
                        tag.name,
                        path,
                        path_indicators,
                        key_names,
                    )
                )

    return (
        head,
        len(refs),
        len(commits),
        sorted(set(history_findings)),
        tags,
        sorted(set(tag_findings)),
        sorted(set(issues)),
    )


def archive_aliases(
    source_root: Path,
    archive_roots: Iterable[Path],
) -> tuple[tuple[Path, str], ...]:
    aliases: list[tuple[Path, str]] = [
        (
            source_root.resolve(),
            "<source>",
        )
    ]
    seen = {source_root.resolve()}

    for root in archive_roots:
        resolved = root.resolve()

        if resolved in seen:
            continue

        seen.add(resolved)
        aliases.append(
            (
                resolved,
                f"<archive-root-{len(aliases)}>",
            )
        )

    return tuple(
        sorted(
            aliases,
            key=lambda item: len(item[0].parts),
            reverse=True,
        )
    )


def display_archive_path(
    path: Path,
    aliases: tuple[tuple[Path, str], ...],
) -> str:
    resolved = Path(
        os.path.abspath(
            os.fspath(path)
        )
    )

    for root, alias in aliases:
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue

        if relative == Path("."):
            return alias

        return f"{alias}/{relative.as_posix()}"

    return f"<external-archive>/{resolved.name}"


def discover_archives(
    roots: Iterable[Path],
) -> tuple[Path, ...]:
    discovered: set[Path] = set()

    for supplied_root in roots:
        root = Path(
            os.path.abspath(
                os.fspath(supplied_root)
            )
        )

        if root.is_symlink():
            if is_archive(root):
                discovered.add(root)
            continue

        if root.is_file():
            if is_archive(root):
                discovered.add(root)
            continue

        if not root.is_dir():
            continue

        for (
            current,
            directory_names,
            file_names,
        ) in os.walk(
            root,
            followlinks=False,
        ):
            directory_names[:] = [
                name
                for name in directory_names
                if name not in SKIP_ARCHIVE_DIRECTORIES
            ]

            for name in file_names:
                path = Path(current) / name

                if is_archive(path):
                    discovered.add(path)

    return tuple(
        sorted(
            discovered,
            key=lambda path: path.as_posix().casefold(),
        )
    )


def member_finding(
    archive_name: str,
    member_name: str,
    data: bytes | None,
) -> Finding | None:
    indicators = sensitive_path_indicators(member_name)
    key_names = extract_sensitive_names(data or b"")

    if not indicators and not key_names:
        return None

    return Finding(
        archive_name,
        member_name,
        indicators,
        key_names,
    )


def scan_zip(
    path: Path,
    shown_path: str,
    max_text_bytes: int,
    max_archive_bytes: int,
    max_members: int,
) -> tuple[
    ArchiveRecord,
    list[Finding],
    list[ScanIssue],
]:
    findings: list[Finding] = []
    issues: list[ScanIssue] = []

    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()

        if len(members) > max_members:
            return (
                ArchiveRecord(
                    shown_path,
                    "zip",
                    "member-count-limit",
                    len(members),
                ),
                findings,
                [
                    ScanIssue(
                        "Local archive",
                        shown_path,
                        "member-count-limit",
                    )
                ],
            )

        bytes_read = 0
        byte_limit_hit = False

        for member in members:
            data: bytes | None = None

            if member.is_dir():
                pass
            elif member.file_size > max_text_bytes:
                issues.append(
                    ScanIssue(
                        "Archive member",
                        f"{shown_path}:{member.filename}",
                        "text-size-limit",
                    )
                )
            elif (
                bytes_read + member.file_size
                > max_archive_bytes
            ):
                if not byte_limit_hit:
                    issues.append(
                        ScanIssue(
                            "Local archive",
                            shown_path,
                            "archive-byte-limit",
                        )
                    )
                    byte_limit_hit = True
            else:
                try:
                    data = archive.read(member)
                    bytes_read += len(data)
                except (
                    OSError,
                    RuntimeError,
                    zipfile.BadZipFile,
                ):
                    issues.append(
                        ScanIssue(
                            "Archive member",
                            f"{shown_path}:{member.filename}",
                            "unreadable",
                        )
                    )

            finding = member_finding(
                shown_path,
                member.filename,
                data,
            )

            if finding:
                findings.append(finding)

        status = (
            "archive-byte-limit"
            if byte_limit_hit
            else "scanned"
        )

        return (
            ArchiveRecord(
                shown_path,
                "zip",
                status,
                len(members),
            ),
            findings,
            issues,
        )


def scan_tar(
    path: Path,
    shown_path: str,
    max_text_bytes: int,
    max_archive_bytes: int,
    max_members: int,
) -> tuple[
    ArchiveRecord,
    list[Finding],
    list[ScanIssue],
]:
    findings: list[Finding] = []
    issues: list[ScanIssue] = []

    with tarfile.open(path, mode="r:*") as archive:
        member_count = 0
        bytes_read = 0
        byte_limit_hit = False
        member_limit_hit = False

        for member in archive:
            member_count += 1

            if member_count > max_members:
                issues.append(
                    ScanIssue(
                        "Local archive",
                        shown_path,
                        "member-count-limit",
                    )
                )
                member_limit_hit = True
                break

            data: bytes | None = None

            if not member.isfile():
                pass
            elif member.size > max_text_bytes:
                issues.append(
                    ScanIssue(
                        "Archive member",
                        f"{shown_path}:{member.name}",
                        "text-size-limit",
                    )
                )
            elif (
                bytes_read + member.size
                > max_archive_bytes
            ):
                if not byte_limit_hit:
                    issues.append(
                        ScanIssue(
                            "Local archive",
                            shown_path,
                            "archive-byte-limit",
                        )
                    )
                    byte_limit_hit = True
            else:
                try:
                    handle = archive.extractfile(member)
                    data = (
                        handle.read()
                        if handle
                        else None
                    )
                    bytes_read += len(data or b"")
                except (
                    OSError,
                    tarfile.TarError,
                ):
                    issues.append(
                        ScanIssue(
                            "Archive member",
                            f"{shown_path}:{member.name}",
                            "unreadable",
                        )
                    )

            finding = member_finding(
                shown_path,
                member.name,
                data,
            )

            if finding:
                findings.append(finding)

        status = "scanned"

        if member_limit_hit:
            status = "member-count-limit"
        elif byte_limit_hit:
            status = "archive-byte-limit"

        return (
            ArchiveRecord(
                shown_path,
                "tar",
                status,
                member_count,
            ),
            findings,
            issues,
        )


def scan_archives(
    source_root: Path,
    additional_roots: Iterable[Path],
    max_text_bytes: int,
    max_archive_bytes: int,
    max_members: int,
) -> tuple[
    list[ArchiveRecord],
    list[Finding],
    list[ScanIssue],
]:
    roots = (
        source_root,
        *tuple(additional_roots),
    )
    aliases = archive_aliases(
        source_root,
        roots,
    )

    records: list[ArchiveRecord] = []
    findings: list[Finding] = []
    issues: list[ScanIssue] = []

    for path in discover_archives(roots):
        shown_path = display_archive_path(
            path,
            aliases,
        )
        format_name = archive_format(path)

        if path.is_symlink():
            records.append(
                ArchiveRecord(
                    shown_path,
                    format_name,
                    "symlink not followed",
                    0,
                )
            )
            issues.append(
                ScanIssue(
                    "Local archive",
                    shown_path,
                    "symlink not followed",
                )
            )
            continue

        if format_name == "unsupported":
            records.append(
                ArchiveRecord(
                    shown_path,
                    format_name,
                    "unsupported",
                    0,
                )
            )
            issues.append(
                ScanIssue(
                    "Local archive",
                    shown_path,
                    "unsupported format",
                )
            )
            continue

        try:
            if format_name == "zip":
                (
                    record,
                    found,
                    errors,
                ) = scan_zip(
                    path,
                    shown_path,
                    max_text_bytes,
                    max_archive_bytes,
                    max_members,
                )
            else:
                (
                    record,
                    found,
                    errors,
                ) = scan_tar(
                    path,
                    shown_path,
                    max_text_bytes,
                    max_archive_bytes,
                    max_members,
                )
        except (
            EOFError,
            OSError,
            tarfile.TarError,
            zipfile.BadZipFile,
        ):
            record = ArchiveRecord(
                shown_path,
                format_name,
                "unreadable",
                0,
            )
            found = []
            errors = [
                ScanIssue(
                    "Local archive",
                    shown_path,
                    "unreadable",
                )
            ]

        records.append(record)
        findings.extend(found)
        issues.extend(errors)

    return (
        sorted(set(records)),
        sorted(set(findings)),
        sorted(set(issues)),
    )


def join_names(values: Iterable[str]) -> str:
    values = tuple(values)

    if not values:
        return "-"

    return ", ".join(
        code(value)
        for value in values
    )


def finding_table(
    lines: list[str],
    findings: Iterable[Finding],
    first_column: str,
) -> None:
    lines.extend(
        (
            (
                f"| {first_column} | Path/member name | "
                "Path indicators | Secret-variable/key names |"
            ),
            "| --- | --- | --- | --- |",
        )
    )

    for finding in findings:
        lines.append(
            "| "
            + " | ".join(
                (
                    code(finding.container),
                    code(finding.item),
                    join_names(finding.path_indicators),
                    join_names(finding.key_names),
                )
            )
            + " |"
        )


def render_report(result: ScanResult) -> str:
    lines = [
        "# SEC-001C - Private Git history and release inventory",
        "",
        f"Source commit at scan time: `{result.head_commit}`",
        "",
        "## Safety boundary",
        "",
        (
            "The scanner reads historical Git text blobs, annotated tag messages, "
            "and text members of local release archives in memory. It retains only "
            "commit IDs, tag names, repository-relative path names, aliased "
            "artifact/member names, sensitive path classifications, and "
            "secret-variable/key names."
        ),
        "",
        (
            "Matching lines, file contents, commit messages, author identities, "
            "absolute home paths, and values are never retained, written to this "
            "report, or sent to stdout. Runtime working-tree files remain covered "
            "by SEC-001B and are not read by this scanner unless they are members "
            "of an archive selected for SEC-001C review."
        ),
        "",
        "## Coverage summary",
        "",
        f"- Git references inventoried: `{result.ref_count}`",
        f"- Unique commits scanned: `{result.commit_count}`",
        f"- History findings: `{len(result.history_findings)}`",
        f"- Tags inventoried: `{len(result.tags)}`",
        (
            "- Tagged-snapshot findings: "
            f"`{len(result.tag_findings)}`"
        ),
        (
            "- Local archives inventoried: "
            f"`{len(result.archives)}`"
        ),
        (
            "- Local-archive findings: "
            f"`{len(result.archive_findings)}`"
        ),
        (
            "- Skipped/unreadable items requiring review: "
            f"`{len(result.issues)}`"
        ),
        "",
        "## Git history findings",
        "",
    ]

    finding_table(
        lines,
        result.history_findings,
        "Suspect commit",
    )

    lines.extend(
        (
            "",
            "## Tag inventory",
            "",
            "| Tag | Target commit | Annotation key names | Status |",
            "| --- | --- | --- | --- |",
        )
    )

    for tag in result.tags:
        lines.append(
            "| "
            + " | ".join(
                (
                    code(tag.name),
                    code(tag.target_commit),
                    join_names(tag.annotation_key_names),
                    tag.status,
                )
            )
            + " |"
        )

    lines.extend(
        (
            "",
            "## Tagged-snapshot findings",
            "",
        )
    )

    finding_table(
        lines,
        result.tag_findings,
        "Tag",
    )

    lines.extend(
        (
            "",
            "## Local archive inventory",
            "",
            "| Artifact | Format | Status | Members |",
            "| --- | --- | --- | ---: |",
        )
    )

    for archive in result.archives:
        lines.append(
            f"| {code(archive.name)} | "
            f"{archive.format} | "
            f"{archive.status} | "
            f"{archive.member_count} |"
        )

    lines.extend(
        (
            "",
            "## Local archive findings",
            "",
        )
    )

    finding_table(
        lines,
        result.archive_findings,
        "Artifact",
    )

    lines.extend(
        (
            "",
            "## Items requiring manual follow-up",
            "",
            "| Scope | Item | Status |",
            "| --- | --- | --- |",
        )
    )

    for issue in result.issues:
        lines.append(
            f"| {issue.scope} | "
            f"{code(issue.item)} | "
            f"{issue.status} |"
        )

    lines.extend(
        (
            "",
            "## SEC-001C.1 collector gate",
            "",
            (
                "- [c] Every commit reachable from local Git references "
                "is scanned by changed text blob."
            ),
            (
                "- [c] Every tag is inventoried and each commit-target "
                "tag snapshot is scanned."
            ),
            (
                "- [c] Supported local release archives are inventoried "
                "and scanned without extraction."
            ),
            (
                "- [c] Output is restricted to IDs, names, path "
                "classifications, statuses, and counts."
            ),
            (
                "- [c] The private report is written atomically outside "
                "the repository with mode `0600`."
            ),
            "",
            (
                "Do not check off SEC-001C until SEC-001C.2 and "
                "SEC-001C.3 are complete."
            ),
            "",
        )
    )

    return "\n".join(lines)


def write_private_report(
    report_path: Path,
    report: str,
) -> None:
    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    temporary = report_path.with_suffix(
        report_path.suffix + ".tmp"
    )
    temporary.write_text(
        report,
        encoding="utf-8",
        newline="\n",
    )

    if os.name != "nt":
        os.chmod(report_path.parent, 0o700)
        os.chmod(temporary, 0o600)

    os.replace(
        temporary,
        report_path,
    )

    if os.name != "nt":
        os.chmod(report_path, 0o600)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a value-free SEC-001C "
            "Git history/tag/archive inventory."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=SOURCE_ROOT,
        help=(
            "Git worktree to scan "
            "(default: this KotiBot source tree)."
        ),
    )
    parser.add_argument(
        "--archive-root",
        action="append",
        type=Path,
        default=[],
        help=(
            "Additional local archive file or directory; "
            "may be repeated."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Private report path "
            "(default: <data-root>/audit/SEC-001C report)."
        ),
    )
    parser.add_argument(
        "--max-text-bytes",
        type=int,
        default=DEFAULT_MAX_TEXT_BYTES,
        help=(
            "Maximum bytes read from one Git blob "
            "or archive member."
        ),
    )
    parser.add_argument(
        "--max-archive-bytes",
        type=int,
        default=DEFAULT_MAX_ARCHIVE_BYTES,
        help=(
            "Maximum uncompressed content bytes "
            "read from one archive."
        ),
    )
    parser.add_argument(
        "--max-archive-members",
        type=int,
        default=DEFAULT_MAX_ARCHIVE_MEMBERS,
        help=(
            "Maximum members scanned from one archive."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()

    if (
        args.max_text_bytes < 1
        or args.max_archive_bytes < 1
        or args.max_archive_members < 1
    ):
        raise SystemExit("scan limits must be positive")

    (
        head,
        ref_count,
        commit_count,
        history_findings,
        tags,
        tag_findings,
        git_issues,
    ) = scan_git(
        source_root,
        args.max_text_bytes,
    )

    (
        archives,
        archive_findings,
        archive_issues,
    ) = scan_archives(
        source_root,
        args.archive_root,
        args.max_text_bytes,
        args.max_archive_bytes,
        args.max_archive_members,
    )

    result = ScanResult(
        head_commit=head,
        ref_count=ref_count,
        commit_count=commit_count,
        history_findings=history_findings,
        tags=tags,
        tag_findings=tag_findings,
        archives=archives,
        archive_findings=archive_findings,
        issues=sorted(
            set(
                (
                    *git_issues,
                    *archive_issues,
                )
            )
        ),
    )

    report_path = args.output or (
        build_runtime_paths(SOURCE_ROOT).data_root
        / "audit"
        / REPORT_NAME
    )

    try:
        report_path.resolve().relative_to(source_root)
    except ValueError:
        pass
    else:
        raise SystemExit(
            "private report output must be outside "
            "the source repository"
        )

    write_private_report(
        report_path,
        render_report(result),
    )
    print(
        "SEC-001C private report written "
        "outside the repository."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
