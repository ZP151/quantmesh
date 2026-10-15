"""Owned, content-addressed bytes; never fetch an artifact URL."""

import hashlib
import json
import os
import uuid
from pathlib import Path

from quantmesh.research.jobs import ArtifactRef


def verified_bytes(root: Path, job, ref: ArtifactRef) -> bytes:
    path = root / ref.object_key
    if (
        not ref.object_key.startswith(job.job_id + "/")
        or root.resolve() not in path.resolve().parents
        or any(p.is_symlink() for p in (path, *path.parents))
    ):
        raise ValueError("artifact invalid")
    raw = path.read_bytes()
    if len(raw) != ref.byte_size or hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise ValueError("artifact invalid")
    return raw


def archive(root: Path, job, output: dict) -> ArtifactRef:
    raw = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="analysis",
        sha256=digest,
        byte_size=len(raw),
        object_key=f"{job.job_id}/{digest}.json",
    )
    path = root / ref.object_key
    if root.resolve() not in path.resolve().parents or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise ValueError("artifact invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            verified_bytes(root, job, ref)
        else:
            os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    verified_bytes(root, job, ref)
    return ref
