"""Restore the compressed, checksummed catalogue shipped in a source checkout."""
from __future__ import annotations
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path


def ensure_baseline(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        return path
    archive = path.with_suffix(path.suffix + '.gz')
    manifest = path.with_name('catalogue_seed.json')
    if not archive.is_file() or not manifest.is_file():
        return path
    expected = json.loads(manifest.read_text('utf-8'))
    expected_size = int(expected['uncompressed_bytes'])
    digest = hashlib.sha256()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='catalogue-', suffix='.tmp', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            total = 0
            with gzip.open(archive, 'rb') as source:
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > expected_size:
                        raise ValueError('Bundled catalogue exceeds its recorded size')
                    digest.update(block)
                    output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if total != expected_size or digest.hexdigest() != expected['sha256']:
            raise ValueError('Bundled catalogue integrity check failed')
        with temporary.open('rb') as source:
            if source.read(16) != b'SQLite format 3\x00':
                raise ValueError('Bundled catalogue is not a SQLite database')
        temporary.replace(path)
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
