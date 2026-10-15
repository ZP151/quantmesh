"""Backend-only private research transport and local authoritative-store adapter."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from quantmesh.research.job_artifacts import _canonical, _contained, _validate_result
from quantmesh.research.job_options import ResearchJobOptions, job_options
from quantmesh.research.job_store import JobStore, _identifier
from quantmesh.research.jobs import (
    ArtifactRef,
    DatasetRejected,
    IdempotencyConflict,
    JobRecord,
    ResearchJobRequest,
    StoreUnavailable,
    canonical_request_digest,
)

JSON_LIMIT = 1024 * 1024
ARTIFACT_LIMIT = 16 * 1024 * 1024


class ArtifactInvalid(ValueError):
    """Fixed public code only; never include artifact bytes or paths."""


def _job(value, operator_id, *, job_id=None, request=None, key=None) -> JobRecord:
    job = JobRecord.model_validate(value)
    if (
        job.operator_id != operator_id
        or canonical_request_digest(job.request) != job.request_digest
        or (job_id is not None and job.job_id != job_id)
        or (key is not None and job.idempotency_key != key)
        or (request is not None and job.request_digest != canonical_request_digest(request))
    ):
        raise StoreUnavailable("service_unavailable")
    refs = job.artifacts + (
        [job.analysis.output_artifact] if job.analysis and job.analysis.output_artifact else []
    )
    if any(
        ref.object_key.split("/")[0] != job.job_id
        or ref.byte_size > ARTIFACT_LIMIT
        or ref.artifact_id != ref.sha256
        for ref in refs
    ):
        raise StoreUnavailable("service_unavailable")
    reports = [ref for ref in job.artifacts if ref.kind == "report"]
    if job.state == "succeeded" and len(reports) != 1:
        raise StoreUnavailable("service_unavailable")
    if job.analysis and (
        job.analysis.job_id != job.job_id
        or len(reports) != 1
        or job.analysis.report_digest != reports[0].sha256
        or any(ref not in job.artifacts for ref in job.analysis.citations)
        or job.analysis.state != job.analysis_state
    ):
        raise StoreUnavailable("service_unavailable")
    return job


def _ref(job: JobRecord, artifact_id: str) -> ArtifactRef:
    refs = job.artifacts + (
        [job.analysis.output_artifact] if job.analysis and job.analysis.output_artifact else []
    )
    ref = next((ref for ref in refs if ref.artifact_id == artifact_id), None)
    if ref is None:
        raise KeyError("not_found")
    return ref


def _verified(job: JobRecord, ref: ArtifactRef, raw: bytes) -> bytes:
    try:
        if len(raw) > ARTIFACT_LIMIT or len(raw) != ref.byte_size:
            raise ValueError("invalid size")
        if hashlib.sha256(raw).hexdigest() != ref.sha256 or ref.schema_version != 1:
            raise ValueError("invalid digest")
        data = json.loads(raw)
        if ref.kind == "report":
            if (
                not isinstance(data, dict)
                or set(data)
                != {"schema_version", "request_digest", "implementation_digest", "result"}
                or data["schema_version"] != 1
                or data["request_digest"] != job.request_digest
                or data["implementation_digest"] != job.implementation_digest
            ):
                raise ValueError("invalid report")
            _validate_result(job, _canonical(data["result"]))
        elif ref.kind == "analysis":
            if (
                not isinstance(data, dict)
                or data.get("job_id") != job.job_id
                or not job.analysis
                or data.get("report_digest") != job.analysis.report_digest
            ):
                raise ValueError("invalid analysis")
        return raw
    except (ValueError, TypeError, KeyError):
        raise ArtifactInvalid("artifact_invalid") from None


class LocalResearchClient:
    """Admission/status only. HTTP never starts a worker or computes a baseline."""

    def __init__(
        self,
        store: JobStore,
        *,
        operator_id: str,
        lake_root: Path,
        configured_dataset_ids: tuple[str, ...],
    ):
        self.store = store
        self.operator_id = _identifier(operator_id)
        authoritative_root = getattr(store, "lake_root", None)
        if (
            authoritative_root is None
            or Path(authoritative_root).resolve() != Path(lake_root).resolve()
        ):
            raise ValueError("worker_inputs_mismatch")
        self.lake_root = Path(authoritative_root)
        self.configured_dataset_ids = configured_dataset_ids

    def options(self) -> ResearchJobOptions:
        return job_options(self.lake_root, self.configured_dataset_ids)

    def submit(self, request: ResearchJobRequest, key: str) -> JobRecord:
        _identifier(key)
        # Existing same-key requests remain replayable even when input choices change.
        # Store.submit performs authoritative pin validation and idempotency conflict checks.
        if request.dataset.dataset_id not in self.configured_dataset_ids:
            raise DatasetRejected("no_qualified_inputs")
        job = self.store.submit(self.operator_id, key, request)
        return _job(job.model_dump(mode="json"), self.operator_id, request=request, key=key)

    def get(self, job_id: str) -> JobRecord:
        _identifier(job_id)
        return _job(
            self.store.get(self.operator_id, job_id).model_dump(mode="json"),
            self.operator_id,
            job_id=job_id,
        )

    def cancel(self, job_id: str) -> JobRecord:
        _identifier(job_id)
        return _job(
            self.store.request_cancel(self.operator_id, job_id).model_dump(mode="json"),
            self.operator_id,
            job_id=job_id,
        )

    def artifact(self, job_id: str, artifact_id: str) -> bytes:
        job = self.get(job_id)
        ref = _ref(job, artifact_id)
        try:
            path = self.store.artifact_root / ref.object_key
            _contained(self.store.artifact_root, path)
            with path.open("rb") as source:
                raw = source.read(ARTIFACT_LIMIT + 1)
        except (ValueError, OSError):
            raise ArtifactInvalid("artifact_invalid") from None
        return _verified(job, ref, raw)


class ResearchServiceClient:
    """Fixed private HTTPS origin; no redirects, fallback endpoints or implicit retries."""

    def __init__(
        self,
        *,
        endpoint: str,
        allowed_endpoints: tuple[str, ...],
        operator_id: str,
        token: SecretStr,
        transport=None,
    ):
        parsed = urlsplit(endpoint)
        host = parsed.hostname or ""
        try:
            address = ipaddress.ip_address(host)
            private = address.is_private and not address.is_unspecified
        except ValueError:
            private = host.endswith(".ts.net") or host.endswith(".internal")
        if (
            endpoint not in allowed_endpoints
            or parsed.scheme != "https"
            or not private
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("fixed TLS private endpoint required")
        if not isinstance(token, SecretStr) or len(token.get_secret_value()) < 16:
            raise ValueError("private authentication required")
        self.operator_id = _identifier(operator_id)
        self._client = httpx.Client(
            base_url=endpoint.rstrip("/"),
            headers={"Authorization": "Bearer " + token.get_secret_value()},
            timeout=httpx.Timeout(5.0, connect=2.0),
            follow_redirects=False,
            verify=True,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._client.close()

    def _read(self, method, path, *, limit=JSON_LIMIT, **kwargs) -> bytes:
        try:
            with self._client.stream(method, path, **kwargs) as response:
                if response.status_code == 409:
                    raise IdempotencyConflict("idempotency_conflict")
                if response.status_code == 404:
                    raise KeyError("not_found")
                if response.status_code == 422:
                    raise DatasetRejected("invalid_request")
                if response.status_code != 200:
                    raise StoreUnavailable("service_unavailable")
                declared = response.headers.get("Content-Length")
                if declared is not None and (int(declared) < 0 or int(declared) > limit):
                    raise StoreUnavailable("service_unavailable")
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > limit:
                        raise StoreUnavailable("service_unavailable")
                return bytes(raw)
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, (IdempotencyConflict, DatasetRejected, StoreUnavailable)):
                raise
            raise StoreUnavailable("service_unavailable") from None

    def _json(self, method, path, **kwargs):
        try:
            return json.loads(self._read(method, path, **kwargs))
        except (IdempotencyConflict, DatasetRejected, StoreUnavailable):
            raise
        except (ValueError, TypeError):
            raise StoreUnavailable("service_unavailable") from None

    def options(self) -> ResearchJobOptions:
        try:
            return ResearchJobOptions.model_validate(self._json("GET", "/v1/options"))
        except ValueError:
            raise StoreUnavailable("service_unavailable") from None

    def submit(self, request: ResearchJobRequest, key: str) -> JobRecord:
        _identifier(key)
        value = self._json(
            "POST",
            "/v1/jobs",
            json=request.model_dump(mode="json"),
            headers={"Idempotency-Key": key},
        )
        return self._validate_job(value, request=request, key=key)

    def _validate_job(self, value, **kwargs):
        try:
            return _job(value, self.operator_id, **kwargs)
        except ValueError:
            raise StoreUnavailable("service_unavailable") from None

    def get(self, job_id: str) -> JobRecord:
        _identifier(job_id)
        return self._validate_job(self._json("GET", f"/v1/jobs/{job_id}"), job_id=job_id)

    def cancel(self, job_id: str) -> JobRecord:
        _identifier(job_id)
        return self._validate_job(self._json("POST", f"/v1/jobs/{job_id}/cancel"), job_id=job_id)

    def artifact(self, job_id: str, artifact_id: str) -> bytes:
        job = self.get(job_id)
        ref = _ref(job, artifact_id)
        return _verified(
            job,
            ref,
            self._read("GET", f"/v1/jobs/{job_id}/artifacts/{artifact_id}", limit=ARTIFACT_LIMIT),
        )
