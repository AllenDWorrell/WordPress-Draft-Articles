"""Verify bundled executable and font SHA-256 checksums."""
import hashlib
import json
from pathlib import Path


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root):
    root=Path(root).resolve()
    resources=[
        root/'tools'/'indd.exe',
        *sorted((root/'fonts').glob('*.ttf')),
    ]
    return {str(path.relative_to(root)):sha256(path) for path in resources if path.is_file()}


if __name__=='__main__':
    manifest=verify(Path(__file__).resolve().parent)
    print(json.dumps(manifest,indent=2,sort_keys=True))
