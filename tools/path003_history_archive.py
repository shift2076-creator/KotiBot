"""Private, non-overwriting recovery copies for PATH-003 legacy history cleanup."""
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile


def archive_path(destination):
    destination = Path(destination)
    return destination.with_name(destination.name + '.path003-legacy')


def _metadata(info, *, uid, gid, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != uid or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)):
        raise ValueError('History archive ownership, type or permissions are invalid')


def _check_path(path, uid, gid):
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('History archive path contains a symbolic link')
    _metadata(path.parent.stat(), uid=uid, gid=gid, directory=True)


def read_archive(path, *, uid, gid, limit):
    """Read a stable private regular archive, or return None if absent."""
    path = Path(path)
    _check_path(path, uid, gid)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        _metadata(before, uid=uid, gid=gid)
        if before.st_size > limit:
            raise ValueError('History archive exceeds the size limit')
        payload = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (len(payload) != before.st_size
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError('History archive changed while being read')
    return payload


def create_archive(path, payload, *, uid, gid, limit):
    """Atomically create once; an identical existing archive is a no-op."""
    path = Path(path)
    if len(payload) > limit:
        raise ValueError('History archive exceeds the size limit')
    existing = read_archive(path, uid=uid, gid=gid, limit=limit)
    if existing is not None:
        if existing != payload:
            raise ValueError('Existing history archive differs; refusing replacement')
        return False
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix='.path003-history-', delete=False) as stream:
            temporary = Path(stream.name)
            _metadata(os.fstat(stream.fileno()), uid=uid, gid=gid)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Unlike replace(), link() refuses an archive created concurrently.
        os.link(temporary, path, follow_symlinks=False)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if read_archive(path, uid=uid, gid=gid, limit=limit) != payload:
            raise ValueError('History archive verification failed')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True
