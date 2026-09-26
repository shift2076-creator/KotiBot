"""Exact Git exports and root-owned Python environment copies."""
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile


def command(*args, **kwargs):
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=300, **kwargs)
    return result.stdout


def git(source, *args):
    return command('git', '-c', f'safe.directory={source}', '-C', str(source), *args)


def export_source(source, head, destination):
    """Export only the selected commit; never copy ignored files or Git history."""
    if git(source, 'rev-parse', 'HEAD').decode().strip() != head:
        raise ValueError('Source commit differs from the requested commit')
    payload = git(source, 'archive', '--format=tar', head)
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        members = archive.getmembers()
        names = set()
        for member in members:
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or '..' in relative.parts
                    or member.name in names or not (member.isfile() or member.isdir())):
                raise ValueError('Source archive contains an unsafe entry')
            names.add(member.name)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    target.write_bytes(stream.read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def tree_digest(root):
    """Content/type inventory; reject special files and do not follow symlinks."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode):
                result[relative] = ['link', os.readlink(path)]
            elif stat.S_ISDIR(before.st_mode):
                result[relative] = ['directory']
            elif stat.S_ISREG(before.st_mode):
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                        after.st_size, after.st_mtime_ns, after.st_ino):
                    raise ValueError('Environment changed during copying')
                result[relative] = ['file', digest.hexdigest()]
            else:
                raise ValueError('Environment contains a special file')
    return result


def root_owned(path):
    """The complete path must resist writes by non-root identities."""
    path = path.resolve(strict=True)
    for component in (path, *path.parents):
        info = component.stat()
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError('Production path is writable by a non-root identity')


def freeze(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in files + dirs:
            path = Path(directory) / name
            if path.is_symlink():
                target = path.resolve(strict=True)
                if not target.is_relative_to(root):
                    root_owned(target)
                os.lchown(path, 0, 0)
                continue
            info = path.stat()
            os.chown(path, 0, 0)
            path.chmod(0o755 if path.is_dir() or info.st_mode & 0o111 else 0o644)
    os.chown(root, 0, 0)
    root.chmod(0o755)


def copy_environment(source, destination):
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Expected a regular production virtual-environment directory')
    before = tree_digest(source)
    shutil.copytree(source, destination, symlinks=True)
    if before != tree_digest(source) or before != tree_digest(destination):
        raise ValueError('Copied Python environment does not match the original')
