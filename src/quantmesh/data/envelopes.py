"""Immutable provider-response envelopes for trusted-data ingestion."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.objects import ObjectRef, ObjectStore


class ProvenanceClass(StrEnum):
    """Whether captured bytes came from an external provider or a fixture."""

    REAL = "real"
    FIXTURE = "fixture"


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class RawEnvelope(BaseModel):
    """A content-addressed response plus event-time and knowledge-time metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    envelope_version: int = Field(default=1, ge=1, le=2)
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    endpoint: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    request_window_start: datetime
    request_window_end: datetime
    collection_window_start: datetime | None = None
    collection_window_end: datetime | None = None
    cursor: str | None = None
    canonical_instrument: CanonicalInstrumentId
    provider_symbol: str = Field(min_length=1)
    data_kind: DataKind
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    event_start: datetime
    event_end: datetime
    session_date: date
    provider_available_at: datetime | None = None
    received_at: datetime
    ingested_at: datetime
    raw_object: ObjectRef
    provider_version: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    source_rights_id: str = Field(min_length=1)
    entitlement: EntitlementState
    provenance: ProvenanceClass

    @classmethod
    def capture(
        cls,
        *,
        objects: ObjectStore,
        payload: bytes,
        content_type: str,
        **metadata: object,
    ) -> Self:
        """Store exact response bytes, then bind them to validated metadata."""
        raw_object = objects.put_bytes(content_type, payload)
        version = (
            2
            if metadata.get("collection_window_start") is not None
            or metadata.get("collection_window_end") is not None
            else 1
        )
        return cls.model_validate(
            {**metadata, "envelope_version": version, "raw_object": raw_object}
        )

    @field_validator(
        "request_window_start",
        "request_window_end",
        "collection_window_start",
        "collection_window_end",
        "event_start",
        "event_end",
        "provider_available_at",
        "received_at",
        "ingested_at",
    )
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None, info) -> datetime | None:
        if value is not None and not _is_utc(value):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @field_validator(
        "endpoint",
        "request_id",
        "provider_symbol",
        "provider_version",
        "adapter_version",
        "schema_version",
        "source_rights_id",
    )
    @classmethod
    def text_is_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("cursor")
    @classmethod
    def cursor_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("cursor must not be blank")
        return value

    @field_validator("source_event_ids")
    @classmethod
    def event_ids_are_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("source_event_ids must be unique and nonblank")
        return values

    @model_validator(mode="after")
    def temporal_and_provenance_contract_is_valid(self) -> Self:
        collection_fields = (
            self.collection_window_start,
            self.collection_window_end,
        )
        if self.envelope_version == 1 and any(item is not None for item in collection_fields):
            raise ValueError("version 1 envelopes cannot declare collection windows")
        if self.envelope_version == 2 and any(item is None for item in collection_fields):
            raise ValueError("version 2 envelopes require a complete collection window")
        if self.request_window_start > self.request_window_end:
            raise ValueError("request_window_start must not be after request_window_end")
        collection_start = self.collection_window_start or self.request_window_start
        collection_end = self.collection_window_end or self.request_window_end
        if collection_start > collection_end:
            raise ValueError("collection_window_start must not be after collection_window_end")
        if self.event_start > self.event_end:
            raise ValueError("event_start must not be after event_end")
        if self.event_start < self.request_window_start or self.event_end > self.request_window_end:
            raise ValueError("event coverage must be within the requested window")
        if self.session_date != self.event_start.date():
            raise ValueError("session_date must match the first event date")
        if self.provider_available_at is not None and self.provider_available_at > self.received_at:
            raise ValueError("provider_available_at must not be after received_at")
        if self.event_end > self.received_at:
            raise ValueError("event_end must not be after received_at")
        if self.ingested_at < self.received_at:
            raise ValueError("ingested_at must not be before received_at")
        if self.provenance is ProvenanceClass.FIXTURE:
            if not self.provider_id.startswith("fixture-"):
                raise ValueError("fixture provenance requires a fixture provider ID")
            if self.entitlement is not EntitlementState.NOT_REQUIRED:
                raise ValueError("fixture provenance requires not-required entitlement")
        elif self.provider_id.startswith("fixture-"):
            raise ValueError("real provenance cannot use a fixture provider ID")
        return self

    @property
    def knowledge_time(self) -> datetime:
        """The first instant at which this response was locally knowable."""
        return self.received_at

    @property
    def qualifies(self) -> bool:
        """Whether this response can contribute to real-provider evidence."""
        return self.provenance is ProvenanceClass.REAL and self.entitlement in (
            EntitlementState.AVAILABLE,
            EntitlementState.NOT_REQUIRED,
        )

    def canonical_bytes(self) -> bytes:
        """Return the canonical metadata representation used in raw lineage."""
        from quantmesh.data.artifacts import canonical_json_bytes

        exclude = {
            field
            for field in ("collection_window_start", "collection_window_end")
            if getattr(self, field) is None
        }
        return canonical_json_bytes(self.model_dump(mode="json", exclude=exclude))
