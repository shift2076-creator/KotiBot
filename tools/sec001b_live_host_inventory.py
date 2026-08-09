#!/usr/bin/env python3
"""Write a private, metadata-only SEC-001B live-host inventory."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


REPORT_NAME = "SEC-001B_LIVE_HOST_INVENTORY.md"
SYSTEMD_ROOTS = (
    Path("/etc/systemd/system"),
    Path("/run/systemd/system"),
    Path("/usr/lib/systemd/system"),
    Path("/lib/systemd/system"),
)
HOST_ROOTS = (
    ("Protected configuration", Path("/etc/kotibot")),
    ("Service data", Path("/var/lib/kotibot")),
    ("Service logs", Path("/var/log/kotibot")),
    ("Service cache", Path("/var/cache/kotibot")),
    ("Service backups", Path("/var/backups/kotibot")),
    ("Service runtime", Path("/run/kotibot")),
    ("Service temporary data", Path("/var/tmp/kotibot")),
)
SOURCE_RUNTIME_PATHS = (
    "subsystems/activities/activity_state.json",
    "subsystems/client-android-home/android_home_state.json",
    "subsystems/client-tapo/runtime",
    "subsystems/client-tapo/tapo_config.json",
    "subsystems/client-tapo/tapo_device_state.json",
    "subsystems/environment/environment_state.json",
    "subsystems/matter/chip_tool_storage",
    "subsystems/matter/chip_tool_subscription_storage",
    "subsystems/matter/matter_device_state.json",
    "subsystems/matter/matter_state.json",
    "subsystems/notifications/firebase-service-account.json",
    "subsystems/notifications/notification_queue.jsonl",
    "subsystems/security/security_audit.jsonl",
    "subsystems/security/security_state.json",
    "subsystems/video/videos",
)
RUNTIME_PARTS = {
    "backups",
    "cache",
    "camera_hls",
    "chip_tool_storage",
    "chip_tool_subscription_storage",
    "credentials.d",
    "logs",
    "recordings",
    "runtime",
    "temp",
    "tmp",
    "videos",
}
RUNTIME_SUFFIXES = (
    ".bak",
    ".db",
    ".env",
    ".json",
    ".jsonl",
    ".log",
    ".pid",
    ".sqlite",
    ".sqlite3",
)
VENV_NAMES = {
    "Activate.ps1",
    "activate",
    "activate.csh",
    "activate.fish",
    "activate.nu",
    "distutils.cfg",
    "pip.conf",
    "pip.ini",
    "pyvenv.cfg",
    "sitecustomize.py",
    "usercustomize.py",
}


def git_output(*arguments: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(SOURCE_ROOT), *arguments),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed with exit code {result.returncode}"
        )
    return result.stdout


def absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def path_aliases(data_root: Path) -> tuple[tuple[Path, str], ...]:
    home = absolute(Path.home())
    aliases = (
        (absolute(SOURCE_ROOT), "<source>"),
        (absolute(data_root), "<data-root>"),
        (home / ".cache" / "kotibot", "<user-cache>"),
        (home / ".config" / "kotibot", "<user-config>"),
        (home / ".local" / "state" / "kotibot", "<user-state>"),
        (Path("/etc/kotibot"), "<etc-kotibot>"),
        (Path("/etc/systemd/system"), "<systemd-etc>"),
        (Path("/run/systemd/system"), "<systemd-run>"),
        (Path("/usr/lib/systemd/system"), "<systemd-usr>"),
        (Path("/lib/systemd/system"), "<systemd-lib>"),
        (Path("/var/backups/kotibot"), "<service-backups>"),
        (Path("/var/cache/kotibot"), "<service-cache>"),
        (Path("/var/lib/kotibot"), "<service-data>"),
        (Path("/var/log/kotibot"), "<service-logs>"),
        (Path("/run/kotibot"), "<service-runtime>"),
        (Path("/var/tmp/kotibot"), "<service-temp>"),
        (home, "<home>"),
    )
    return tuple(
        sorted(
            ((absolute(root), alias) for root, alias in aliases),
            key=lambda item: len(item[0].parts),
            reverse=True,
        )
    )


def display_path(path: Path, aliases: tuple[tuple[Path, str], ...]) -> str:
    path = absolute(path)
    for root, alias in aliases:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        return alias if relative == Path(".") else f"{alias}/{relative.as_posix()}"
    return path.as_posix()


def file_type(mode: int) -> str:
    for matches, name in (
        (stat.S_ISDIR, "directory"),
        (stat.S_ISREG, "file"),
        (stat.S_ISLNK, "symlink"),
        (stat.S_ISSOCK, "socket"),
        (stat.S_ISFIFO, "fifo"),
        (stat.S_ISCHR, "character device"),
        (stat.S_ISBLK, "block device"),
    ):
        if matches(mode):
            return name
    return "other"


def metadata_row(
    category: str,
    path: Path,
    aliases: tuple[tuple[Path, str], ...],
    *,
    include_missing: bool = False,
    note: str = "",
) -> tuple[str, ...] | None:
    shown = display_path(path, aliases)
    try:
        details = path.lstat()
    except FileNotFoundError:
        if not include_missing:
            return None
        return category, shown, "missing", "-", "-", "-", "-", "-", note
    except PermissionError:
        return (
            category,
            shown,
            "metadata denied",
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            note,
        )
    except OSError as error:
        return (
            category,
            shown,
            f"metadata error:{error.errno or 'unknown'}",
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            "unknown",
            note,
        )

    target = "-"
    if stat.S_ISLNK(details.st_mode):
        try:
            raw_target = Path(os.readlink(path))
            target = (
                display_path(raw_target, aliases)
                if raw_target.is_absolute()
                else raw_target.as_posix()
            )
        except OSError:
            target = "unreadable"

    return (
        category,
        shown,
        "present",
        file_type(details.st_mode),
        f"{stat.S_IMODE(details.st_mode):04o}",
        f"uid:{details.st_uid}",
        f"gid:{details.st_gid}",
        target,
        note,
    )


def add_tree(
    rows: list[tuple[str, ...]],
    category: str,
    root: Path,
    aliases: tuple[tuple[Path, str], ...],
    *,
    include_missing: bool = False,
) -> None:
    root_row = metadata_row(
        category,
        root,
        aliases,
        include_missing=include_missing,
    )
    if root_row:
        rows.append(root_row)
    if not root.is_dir() or root.is_symlink():
        return

    def record_walk_error(error: OSError) -> None:
        row = metadata_row(category, Path(error.filename), aliases)
        if row:
            rows.append(row[:-7] + ("scan denied",) + row[-6:])

    for current, directory_names, file_names in os.walk(
        root,
        followlinks=False,
        onerror=record_walk_error,
    ):
        for name in sorted((*directory_names, *file_names)):
            row = metadata_row(category, Path(current) / name, aliases)
            if row:
                rows.append(row)


def runtime_candidate(path: Path) -> bool:
    parts = set(path.parts)
    name = path.name
    if ".venv" in parts:
        return (
            name in VENV_NAMES
            or name.endswith(".pth")
            or ("bin" in parts and name.startswith(("activate", "python")))
        )
    return (
        bool(parts & RUNTIME_PARTS)
        or (name.startswith(".env") and name != ".env.example")
        or name.endswith(RUNTIME_SUFFIXES)
        or ".bak." in name
    )


def add_git_paths(
    rows: list[tuple[str, ...]],
    aliases: tuple[tuple[Path, str], ...],
) -> None:
    scans = (
        (
            "Ignored source runtime path",
            ("ls-files", "--others", "--ignored", "--exclude-standard", "-z"),
        ),
        (
            "Untracked source runtime path",
            ("ls-files", "--others", "--exclude-standard", "-z"),
        ),
    )
    for category, command in scans:
        for raw_name in git_output(*command).split(b"\0"):
            if not raw_name:
                continue
            relative = Path(os.fsdecode(raw_name))
            if runtime_candidate(relative):
                row = metadata_row(category, SOURCE_ROOT / relative, aliases)
                if row:
                    rows.append(row)


def add_source_paths(
    rows: list[tuple[str, ...]],
    aliases: tuple[tuple[Path, str], ...],
) -> None:
    for relative_name in SOURCE_RUNTIME_PATHS:
        path = SOURCE_ROOT / relative_name
        if path.is_dir() and not path.is_symlink():
            add_tree(rows, "Known source runtime path", path, aliases)
        else:
            row = metadata_row(
                "Known source runtime path",
                path,
                aliases,
                include_missing=True,
            )
            if row:
                rows.append(row)


def environment_file_names(unit_path: Path) -> set[str]:
    """Read only EnvironmentFile path declarations from a small regular unit."""
    try:
        details = unit_path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_size > 2 * 1024 * 1024:
            return set()
        declarations: set[str] = set()
        with unit_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped.startswith("EnvironmentFile="):
                    continue
                value = stripped.split("=", 1)[1].strip()
                try:
                    candidates = shlex.split(value, comments=False, posix=True)
                except ValueError:
                    candidates = (value,)
                declarations.update(
                    candidate.removeprefix("-").strip()
                    for candidate in candidates
                    if candidate.removeprefix("-").strip()
                )
        return declarations
    except (OSError, UnicodeError):
        return set()


def add_systemd(
    rows: list[tuple[str, ...]],
    aliases: tuple[tuple[Path, str], ...],
) -> None:
    unit_paths: set[Path] = set()
    for root in SYSTEMD_ROOTS:
        if not root.is_dir():
            continue
        for pattern in ("kotibot*.service", "kotibot*.socket", "kotibot*.timer"):
            unit_paths.update(root.glob(pattern))
        for drop_in in root.glob("kotibot*.d"):
            unit_paths.add(drop_in)
            if drop_in.is_dir() and not drop_in.is_symlink():
                try:
                    unit_paths.update(drop_in.iterdir())
                except OSError:
                    pass

    for unit_path in sorted(unit_paths, key=lambda path: path.as_posix()):
        row = metadata_row("systemd unit or drop-in", unit_path, aliases)
        if row:
            rows.append(row)
        if not unit_path.is_file() or unit_path.is_symlink():
            continue
        for declaration in sorted(environment_file_names(unit_path)):
            note = f"declared by {display_path(unit_path, aliases)}"
            if declaration.startswith("/") and not any(
                marker in declaration for marker in ("%", "$", "*")
            ):
                row = metadata_row(
                    "systemd environment file",
                    Path(declaration),
                    aliases,
                    include_missing=True,
                    note=note,
                )
            else:
                row = (
                    "systemd environment file",
                    declaration,
                    "declared; unresolved",
                    "-",
                    "-",
                    "-",
                    "-",
                    "-",
                    note,
                )
            rows.append(row)


def add_venv(
    rows: list[tuple[str, ...]],
    aliases: tuple[tuple[Path, str], ...],
) -> None:
    root = SOURCE_ROOT / ".venv"
    row = metadata_row(
        "Virtual environment metadata",
        root,
        aliases,
        include_missing=True,
    )
    if row:
        rows.append(row)
    if not root.is_dir():
        return
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        for name in sorted((*directory_names, *file_names)):
            path = Path(current) / name
            if not (
                name in VENV_NAMES
                or name.endswith(".pth")
                or (
                    path.parent.name in {"bin", "Scripts"}
                    and name.startswith(("activate", "python"))
                )
            ):
                continue
            row = metadata_row("Virtual environment metadata", path, aliases)
            if row:
                rows.append(row)


def markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_report(commit: str, rows: list[tuple[str, ...]]) -> str:
    rows = sorted(set(rows), key=lambda row: (row[0].casefold(), row[1].casefold()))
    present = sum(row[2] == "present" for row in rows)
    missing = sum(row[2] == "missing" for row in rows)
    lines = [
        "# SEC-001B - Private live-host inventory",
        "",
        f"Source commit at scan time: `{commit}`",
        "",
        "## Safety boundary",
        "",
        "This report is stored outside the source repository with mode `0600`. The "
        "collector records path names and filesystem metadata only. It never opens "
        "runtime JSON, JSONL, environment files, credentials, databases, logs, media, "
        "archives, Matter storage, virtual-environment configuration, or package files.",
        "",
        "Systemd units receive one narrow inspection: only `EnvironmentFile=` path "
        "directives are retained. `Environment=` directives and environment-file "
        "contents are never captured. Known roots are aliased, and account names are "
        "replaced with numeric owner/group IDs.",
        "",
        "## Summary",
        "",
        f"- Present entries: `{present}`",
        f"- Missing expected locations: `{missing}`",
        f"- Other statuses: `{len(rows) - present - missing}`",
        "",
        "## Path and permission metadata",
        "",
        "| Category | Path | Status | Type | Mode | Owner | Group | Symlink target | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        values = list(row)
        values[1] = f"`{values[1]}`"
        if values[7] != "-":
            values[7] = f"`{values[7]}`"
        lines.append("| " + " | ".join(markdown(value) for value in values) + " |")
    lines.extend(
        (
            "",
            "## SEC-001B.1 collector gate",
            "",
            "- [c] Ignored/untracked runtime-looking source paths are inventoried.",
            "- [c] systemd units, drop-ins, and environment-file names are inventoried.",
            "- [c] Data, configuration, logs, media, backups, caches, and Matter storage are inventoried.",
            "- [c] Virtual-environment activation, interpreter symlink, `.pth`, and configuration paths are inventoried.",
            "- [c] Type, numeric owner/group, mode, and symlink metadata are recorded without runtime contents.",
            "",
            "Do not check off SEC-001B until SEC-001B.2 and SEC-001B.3 are complete.",
            "",
        )
    )
    return "\n".join(lines)


def write_private_report(report_path: Path, report: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8", newline="\n")
    if os.name != "nt":
        os.chmod(report_path.parent, 0o700)
        os.chmod(temporary, 0o600)
    os.replace(temporary, report_path)
    if os.name != "nt":
        os.chmod(report_path, 0o600)


def main() -> int:
    data_root = build_runtime_paths(SOURCE_ROOT).data_root
    aliases = path_aliases(data_root)
    rows: list[tuple[str, ...]] = []
    add_git_paths(rows, aliases)
    add_source_paths(rows, aliases)
    add_systemd(rows, aliases)
    add_venv(rows, aliases)
    add_tree(rows, "KotiBot external data", data_root, aliases, include_missing=True)
    for category, path in HOST_ROOTS:
        add_tree(rows, category, path, aliases, include_missing=True)
    home = Path.home()
    for category, path in (
        ("Per-user cache", home / ".cache" / "kotibot"),
        ("Per-user configuration", home / ".config" / "kotibot"),
        ("Per-user state", home / ".local" / "state" / "kotibot"),
    ):
        add_tree(rows, category, path, aliases, include_missing=True)

    report = render_report(
        git_output("rev-parse", "HEAD").decode("ascii").strip(),
        rows,
    )
    report_path = data_root / "audit" / REPORT_NAME
    write_private_report(report_path, report)
    print("SEC-001B private report written to <data-root>/audit/" + REPORT_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
