"""Utilities for reproducible input fingerprints and JSON reports."""
import hashlib
import json
from pathlib import Path
from src import config


def file_fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(config.HASH_CHUNK_BYTES), b""):
            digest.update(block)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
