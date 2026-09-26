"""Resolve the explicit source checkout and verify the audited source bytes."""
import argparse
import hashlib
import json
from pathlib import Path


def source_root():
    parser = argparse.ArgumentParser(description='Run isolated audit reproductions against the audited KotiBot source.')
    parser.add_argument('--source', required=True, type=Path, help='Path to a checkout of edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a')
    root = parser.parse_args().source.resolve(strict=True)
    manifest = json.loads(Path(__file__).with_name('probe-source-hashes.json').read_text())
    for relative, expected in manifest.items():
        path = root / relative
        if not path.is_file():
            parser.error(f'Missing audited source file: {relative}')
        data = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != expected:
            parser.error(f'Audited source differs: {relative}; these probes require the original audited implementation')
    return root
