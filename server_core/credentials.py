"""Protected runtime credential loading for KotiBot.

Credentials are read from systemd's runtime credential directory, an explicit
KotiBot credential directory, or the Windows OS-native credential location.
Runtime consumers never fall back to environment variables or source files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any


DEFAULT_MAX_CREDENTIAL_BYTES = 1024 * 1024


class CredentialMissingError(RuntimeError):
    """Raised when a selected credential file does not exist."""


def _absolute_directory(value: str, variable_name: str) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        raise RuntimeError(f"{variable_name} must be an absolute path")

    return path


def default_credential_directory() -> Path:
    """Return the OS-native protected credential directory."""
    if os.name == "nt":
        program_data = str(os.environ.get("PROGRAMDATA", "")).strip()

        if program_data:
            return Path(program_data) / "KotiBot" / "credentials"

        app_data = str(os.environ.get("APPDATA", "")).strip()

        if app_data:
            return Path(app_data) / "KotiBot" / "credentials"

        return Path.home() / "AppData" / "Roaming" / "KotiBot" / "credentials"

    return Path("/etc/kotibot/credentials.d")


def credential_directories() -> tuple[Path, ...]:
    """Return credential roots in strict runtime precedence order."""
    roots: list[Path] = []
    systemd_root = str(os.environ.get("CREDENTIALS_DIRECTORY", "")).strip()
    configured_root = str(
        os.environ.get("KOTIBOT_CREDENTIALS_DIR", "")
    ).strip()

    if systemd_root:
        roots.append(
            _absolute_directory(systemd_root, "CREDENTIALS_DIRECTORY")
        )

    if configured_root:
        roots.append(
            _absolute_directory(
                configured_root,
                "KOTIBOT_CREDENTIALS_DIR",
            )
        )

    if os.name == "nt":
        roots.append(default_credential_directory())

    unique: list[Path] = []

    for root in roots:
        if root not in unique:
            unique.append(root)

    return tuple(unique)


def _credential_path(root: Path, credential_name: str) -> Path:
    name = str(credential_name or "").strip()

    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise RuntimeError("Credential name must be a single safe filename")

    return root / name


def _validate_selected_root(root: Path) -> bool:
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError(
            "Credential directory could not be inspected"
        ) from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(
            "Credential directory must not be a symbolic link"
        )

    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("Credential directory must be a directory")

    if os.name != "nt":
        mode = stat.S_IMODE(metadata.st_mode)

        if mode & 0o027:
            raise RuntimeError(
                "Credential directory permissions are not private"
            )

    return True


def _path_exists_without_following(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError(
            f"Credential path could not be inspected: {path.name}"
        ) from exc

    return True


def resolve_credential_file(
    credential_name: str,
) -> Path:
    """Select a protected credential path without a legacy fallback."""
    roots = credential_directories()

    for root in roots:
        if not _validate_selected_root(root):
            continue

        candidate = _credential_path(root, credential_name)

        if _path_exists_without_following(candidate):
            return candidate

    fallback_root = roots[0] if roots else default_credential_directory()
    return _credential_path(fallback_root, credential_name)


def _read_private_credential(
    path: Path,
    *,
    credential_name: str,
    max_bytes: int,
) -> bytes:
    path = Path(path)

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    if path.is_symlink():
        raise RuntimeError(
            f"Credential must not be a symbolic link: {credential_name}"
        )

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise CredentialMissingError(
            f"Credential is missing: {credential_name}"
        ) from None
    except OSError as exc:
        raise RuntimeError(
            f"Credential could not be opened: {credential_name}"
        ) from exc

    try:
        metadata = os.fstat(fd)

        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"Credential must be a regular file: {credential_name}"
            )

        if os.name != "nt":
            mode = stat.S_IMODE(metadata.st_mode)

            if mode & 0o037:
                raise RuntimeError(
                    "Credential permissions are not private: "
                    f"{credential_name}"
                )

        chunks: list[bytes] = []
        total = 0

        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))

            if not chunk:
                break

            chunks.append(chunk)
            total += len(chunk)

            if total > max_bytes:
                raise RuntimeError(
                    f"Credential is too large: {credential_name}"
                )

        return b"".join(chunks)
    finally:
        os.close(fd)


def read_binary_credential_file(
    path: Path,
    *,
    credential_name: str,
    max_bytes: int = DEFAULT_MAX_CREDENTIAL_BYTES,
) -> bytes:
    """Read one private credential without following its final symlink."""
    return _read_private_credential(
        path,
        credential_name=credential_name,
        max_bytes=max_bytes,
    )


def _validate_single_line_text(value: str, credential_name: str) -> str:
    value = value.strip()

    if not value:
        raise RuntimeError(f"Credential is empty: {credential_name}")

    if "\x00" in value or "\r" in value or "\n" in value:
        raise RuntimeError(
            f"Credential must contain one text line: {credential_name}"
        )

    return value


def read_text_credential(
    credential_name: str,
    *,
    required: bool = False,
    max_bytes: int = 65536,
) -> str:
    """Read a text credential only from protected credential storage."""
    for root in credential_directories():
        if not _validate_selected_root(root):
            continue

        candidate = _credential_path(root, credential_name)

        if not _path_exists_without_following(candidate):
            continue

        payload = _read_private_credential(
            candidate,
            credential_name=credential_name,
            max_bytes=max_bytes,
        )

        try:
            value = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"Credential is not valid UTF-8: {credential_name}"
            ) from exc

        return _validate_single_line_text(value, credential_name)

    if required:
        raise CredentialMissingError(
            f"Credential is missing: {credential_name}"
        )

    return ""


def read_json_credential_file(
    path: Path,
    *,
    credential_name: str,
    max_bytes: int = DEFAULT_MAX_CREDENTIAL_BYTES,
) -> dict[str, Any]:
    """Read a private JSON-object credential with redacted failures."""
    payload = _read_private_credential(
        path,
        credential_name=credential_name,
        max_bytes=max_bytes,
    )

    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Credential is not a valid JSON document: {credential_name}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Credential JSON must contain an object: {credential_name}"
        )

    return data


def read_json_credential(
    credential_name: str,
    *,
    required: bool = False,
    max_bytes: int = DEFAULT_MAX_CREDENTIAL_BYTES,
) -> dict[str, Any] | None:
    """Read an optional protected JSON-object credential by name."""
    for root in credential_directories():
        if not _validate_selected_root(root):
            continue

        candidate = _credential_path(root, credential_name)

        if not _path_exists_without_following(candidate):
            continue

        return read_json_credential_file(
            candidate,
            credential_name=credential_name,
            max_bytes=max_bytes,
        )

    if required:
        raise CredentialMissingError(
            f"Credential is missing: {credential_name}"
        )

    return None
