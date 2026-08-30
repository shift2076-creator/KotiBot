"""Fail-closed permissions for service-owned private runtime paths."""

from __future__ import annotations

import os
from pathlib import Path
import stat


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


class PrivatePathPermissionError(PermissionError):
    """Required private runtime ownership or mode could not be enforced."""


def _permission_error(kind: str) -> PrivatePathPermissionError:
    return PrivatePathPermissionError(
        f"Private {kind} ownership or permissions could not be enforced"
    )


def _verify_descriptor(fd: int, *, directory: bool) -> None:
    if os.name == "nt":
        return

    expected_mode = (
        PRIVATE_DIRECTORY_MODE
        if directory
        else PRIVATE_FILE_MODE
    )
    info = os.fstat(fd)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG

    if not expected_type(info.st_mode):
        raise _permission_error(
            "directory" if directory else "file"
        )

    if stat.S_IMODE(info.st_mode) != expected_mode:
        os.fchmod(fd, expected_mode)

    if (
        info.st_uid != os.geteuid()
        or info.st_gid != os.getegid()
    ):
        os.fchown(fd, os.geteuid(), os.getegid())
    secured = os.fstat(fd)

    if (
        stat.S_IMODE(secured.st_mode) != expected_mode
        or secured.st_uid != os.geteuid()
        or secured.st_gid != os.getegid()
    ):
        raise _permission_error(
            "directory" if directory else "file"
        )


def verify_private_descriptor(fd: int, *, directory: bool) -> None:
    """Apply and verify private metadata on an already-open descriptor."""
    try:
        _verify_descriptor(fd, directory=directory)
    except OSError:
        raise _permission_error(
            "directory" if directory else "file"
        ) from None


def ensure_private_directory(path: Path) -> Path:
    """Create or re-secure one service-owned private directory."""
    path = Path(path)

    try:
        missing = []
        current = path

        while not current.exists():
            if current.is_symlink():
                raise _permission_error("directory")

            missing.append(current)
            parent = current.parent

            if parent == current:
                break

            current = parent

        for directory in reversed(missing):
            directory.mkdir(
                exist_ok=True,
                mode=PRIVATE_DIRECTORY_MODE,
            )

        directories_to_secure = (
            tuple(reversed(missing))
            if missing
            else (path,)
        )

        for directory in directories_to_secure:
            if directory.is_symlink():
                raise _permission_error("directory")

            if os.name == "nt":
                continue

            flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            fd = os.open(directory, flags)

            try:
                verify_private_descriptor(fd, directory=True)
            finally:
                os.close(fd)
    except OSError:
        raise _permission_error("directory") from None

    return path


def ensure_private_file(path: Path) -> Path:
    """Re-secure one existing service-owned private regular file."""
    path = Path(path)

    if path.is_symlink():
        raise _permission_error("file")

    try:
        if os.name != "nt":
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            fd = os.open(path, flags)

            try:
                verify_private_descriptor(fd, directory=False)
            finally:
                os.close(fd)
    except OSError:
        raise _permission_error("file") from None

    return path


def ensure_private_tree(root: Path) -> Path:
    """Re-secure a private tree without reading any file contents."""
    root = ensure_private_directory(root)
    stack = [root]

    while stack:
        directory = stack.pop()

        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)

                    if entry.is_symlink():
                        raise _permission_error("tree")

                    if entry.is_dir(follow_symlinks=False):
                        ensure_private_directory(path)
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        ensure_private_file(path)
                    else:
                        raise _permission_error("tree")
        except OSError:
            raise _permission_error("tree") from None

    return root


def private_subprocess_options() -> dict[str, int]:
    """Return child-process options that make new runtime files private."""
    return {} if os.name == "nt" else {"umask": 0o077}
