"""Connector panel, the credential-free public data path and file import
(iteration 0014 Phase D).

Three surfaces, one isolation contract: nothing here ever writes into
the seeded tree.

- **Connector panel** (`GET/POST /api/demo/connectors`): explicit
  diagnostics for fixture/demo (always ok), Hyperliquid public data
  (credential-free read-only testnet fetch — the one end-to-end path),
  Moomoo OpenD simulated access (a real local probe), and the
  Polymarket/Kalshi market-data adapters (honestly reported as not
  wired in this release, with the reason). Probe results are session
  state: they carry real wall-clock latency and never enter the
  provenance contract.
- **Public data path** (`POST /api/demo/datalink/fetch`): read-only
  Hyperliquid testnet l2Book snapshots (ADR-0007 pins the transport to
  testnet and refuses any other base URL; nothing here can reach
  mainnet or place an order). Payloads are cached under
  ``<root>/.datalink/hyperliquid/`` with a fetched_at label, and every
  failure — missing vendored SDK, network error, rate limit — degrades
  to the seeded fixture book labeled ``synthetic`` with
  ``fallback_of`` and the reason. The fallback is deterministic: an
  unreachable venue shows the demo book, never a blank page.
- **File import** (`POST /api/demo/import` + `/commit`): CSV / JSON /
  Parquet with preview, field mapping, per-row validation with
  rejection reasons, and dataset-manifest creation through the
  existing lake + ``ManifestWriter`` machinery into
  ``<root>/market/lake``. Import refuses to open an existing dataset,
  so the seeded state is never mutated; a reset wipes imported
  datasets together with the rest of the demo root.

Import sessions are ephemeral server state: the two-step flow
(upload → map → commit) must happen in one server session, and a
reset clears them.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from quantmesh.api.workstation import _json_guard_origin
from quantmesh.data.lake import Lake
from quantmesh.data.layout import validate_dataset_name, validate_symbol
from quantmesh.data.manifest import (
    MANIFEST_NAME,
    DatasetClass,
    DatasetManifest,
    ManifestWriter,
)
from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import (
    HyperliquidError,
    HyperliquidSDKMissingError,
)
from quantmesh.hyperliquid.rest import RestTransport, SdkRestTransport

# Import guardrails: instructive refusals, never an OOM or a hung parse.
MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_IMPORT_ROWS = 100_000
MAX_REJECTIONS_REPORTED = 20

_DATALINK_ROOT = ".datalink"
_PUBLIC_CACHE = "hyperliquid"
_IMPORT_SESSION = "imports"

REQUIRED_FIELDS = ("timestamp", "open", "high", "low", "close")
OPTIONAL_FIELDS = ("volume",)
CANONICAL_FIELDS = (*REQUIRED_FIELDS, *OPTIONAL_FIELDS)

# The canonical bar fields an imported column may map onto.
_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "ts", "date", "datetime", "dt"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c", "last"),
    "volume": ("volume", "vol", "v", "qty", "quantity"),
}

_RATE_LIMIT_MARKERS = ("429", "rate limit", "ratelimit", "too many requests")


class ConnectorState(BaseModel):
    """One row of the connector panel."""

    venue: str
    kind: str  # fixture | public-data | execution-sim | unwired
    mode: str  # fixture | sandbox | read-only-testnet
    credentials_required: bool
    read_only: bool
    wired: bool
    state: str  # ok | degraded | unavailable | unwired
    detail: str
    last_checked_at: str | None = None
    latency_ms: float | None = None


class ImportPreview(BaseModel):
    """The parse result: columns with samples, the first rows, mapping hints."""

    session_id: str
    filename: str
    format: str
    rows: int
    columns: list[dict[str, object]]
    preview: list[dict[str, object]]
    suggested_mapping: dict[str, str]


class _CommitBody(BaseModel):
    session_id: str
    dataset: str
    interval: str
    venue: str
    symbol: str
    instrument_type: str = "equity"
    license: str = "operator-import"
    mapping: dict[str, str]  # canonical field -> imported column


class _FetchBody(BaseModel):
    symbols: list[str] = Field(min_length=1)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _coin_of(symbol: str) -> str:
    """Demo universe symbol -> Hyperliquid coin code (``SOL-USD`` -> ``SOL``)."""
    if symbol.endswith("-USD"):
        return symbol[: -len("-USD")]
    return symbol


def _parse_timestamp(value: object) -> datetime:
    """Import timestamps: aware ISO strings or epoch seconds/millis.

    Naive ISO strings are interpreted as UTC (the lake is UTC-normalized);
    epoch numbers are seconds below 1e12 and milliseconds from there.
    Anything else raises ValueError with the offending value.
    """
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise ValueError(f"timestamp {value!r} is not a finite number")
        seconds = number / 1000 if number >= 1e12 else number
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError) as error:
            raise ValueError(f"timestamp {value!r} is out of range") from error
    if isinstance(value, datetime):  # pandas/duckdb hand over real instants
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("timestamp is an empty string")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"timestamp {text!r} is not an ISO-8601 instant") from error
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    raise ValueError(f"timestamp of type {type(value).__name__} is not supported")


def _parse_number(value: object, field_name: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} {value!r} is not a number") from error
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} {value!r} is not finite")
    return number


def _rate_limited(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def _suggest_mapping(columns: list[str]) -> dict[str, str]:
    """Case-insensitive column-name hints -> the canonical field map."""
    by_lower = {column.lower(): column for column in columns}
    suggested: dict[str, str] = {}
    for canonical, hints in _FIELD_HINTS.items():
        for hint in hints:
            if hint in by_lower:
                suggested[canonical] = by_lower[hint]
                break
    return suggested


def _infer_dtype(column: pd.Series) -> str:
    sample = column.dropna()
    if sample.empty:
        return "empty"
    if pd.api.types.is_datetime64_any_dtype(column):
        return "datetime"
    value = sample.iloc[0]
    if isinstance(value, str):
        try:
            _parse_timestamp(value)
            return "datetime"
        except ValueError:
            pass
        try:
            float(value)
            return "numeric-string"
        except ValueError:
            return "text"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return type(value).__name__


def _native(value: object) -> object:
    """JSON-safe preview value: pandas/numpy scalars and timestamps
    become float/int/str/None so the preview serializes cleanly."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number:
        return None
    return int(number) if number.is_integer() else number


def _read_upload(filename: str, data: bytes) -> pd.DataFrame:
    """Parse an uploaded CSV / JSON / Parquet file into a DataFrame.

    Failures are instructive ``ValueError``s: an unparseable file names
    the format and the error, never a bare traceback. Parquet is read
    through duckdb (native reader — no pyarrow dependency).
    """
    if not data.strip():
        raise ValueError(f"file {filename!r} contains no rows")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            frame = pd.read_csv(__import__("io").BytesIO(data))
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
            raise ValueError(f"CSV is unreadable: {error}") from error
    elif suffix == ".json":
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"JSON is unreadable: {error}") from error
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ValueError(
                "JSON must be an array of objects (one row per object); "
                f"got {type(payload).__name__}"
            )
        frame = pd.DataFrame.from_records(payload)
    elif suffix == ".parquet":
        # duckdb cannot bind uploaded bytes to read_parquet; the bytes
        # are staged in a temp file, read, and removed again.
        import os
        import tempfile

        descriptor, temp_name = tempfile.mkstemp(suffix=".parquet")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            with duckdb.connect() as con:
                quoted = temp_name.replace("'", "''")
                frame = con.execute(f"SELECT * FROM read_parquet('{quoted}')").df()
        except duckdb.Error as error:
            raise ValueError(f"Parquet is unreadable: {error}") from error
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    else:
        raise ValueError(
            f"unsupported file type {suffix!r} — expected .csv, .json or .parquet"
        )
    if frame.empty:
        raise ValueError(f"file {filename!r} contains no rows")
    if len(frame) > MAX_IMPORT_ROWS:
        raise ValueError(
            f"file {filename!r} holds {len(frame)} rows; the import path accepts "
            f"at most {MAX_IMPORT_ROWS} rows"
        )
    return frame


@dataclass
class DatalinkService:
    """Session-scoped Phase D surfaces over one demo root.

    ``rest`` is injectable so tests drive the public path with the
    scripted transport; the production default is the testnet-pinned
    ``SdkRestTransport`` (ADR-0007). Probe results and import sessions
    live in memory; the public-data cache is the only disk state, under
    ``<root>/.datalink`` and labeled with real wall-clock fetches — the
    seeded tree and its provenance contract are never touched.
    """

    root: Path
    rest: RestTransport = field(default_factory=SdkRestTransport)
    _probes: dict[str, ConnectorState] = field(default_factory=dict)
    _last_fetch: dict[str, object] | None = None
    _sessions: dict[str, dict[str, object]] = field(default_factory=dict)

    # -- connector panel ----------------------------------------------------

    def panel(self) -> list[ConnectorState]:
        states: list[ConnectorState] = [
            ConnectorState(
                venue="demo",
                kind="fixture",
                mode="fixture",
                credentials_required=False,
                read_only=False,
                wired=True,
                state="ok",
                detail=(
                    "The deterministic demo session: seeded books, orders and "
                    "research through the real fixture providers, labeled "
                    "synthetic. Always available."
                ),
            ),
            ConnectorState(
                venue="hyperliquid",
                kind="public-data",
                mode="read-only-testnet",
                credentials_required=False,
                read_only=True,
                wired=True,
                state="unprobed",
                detail=(
                    "Credential-free, read-only Hyperliquid testnet market data "
                    "(ADR-0007: testnet pinned, mainnet refused). Unreachable or "
                    "rate-limited fetches fall back to the seeded demo book, "
                    "labeled synthetic."
                ),
            ),
            ConnectorState(
                venue="moomoo",
                kind="execution-sim",
                mode="sandbox",
                credentials_required=True,
                read_only=False,
                wired=False,
                state="unprobed",
                detail=(
                    "Optional local OpenD simulated access (probe when a local "
                    "OpenD process is running). Requires the py-moomoo-api SDK "
                    "and an operator-provided simulated account — never wired "
                    "by default."
                ),
            ),
            ConnectorState(
                venue="polymarket",
                kind="unwired",
                mode="fixture",
                credentials_required=False,
                read_only=True,
                wired=False,
                state="unwired",
                detail=(
                    "The Polymarket adapter is fixture-only in this release; "
                    "the live market-data path is not wired into the "
                    "workstation. Forecast surfaces serve the seeded reports."
                ),
            ),
            ConnectorState(
                venue="kalshi",
                kind="unwired",
                mode="fixture",
                credentials_required=False,
                read_only=True,
                wired=False,
                state="unwired",
                detail=(
                    "The Kalshi adapter is fixture-only in this release; the "
                    "live market-data path is not wired into the workstation. "
                    "Forecast surfaces serve the seeded reports."
                ),
            ),
        ]
        for index, state in enumerate(states):
            if state.venue in self._probes:
                states[index] = self._probes[state.venue]
        return states

    def probe_hyperliquid(self) -> ConnectorState:
        start = time.perf_counter()
        try:
            payload = self.rest.l2_book("BTC", at=_utc_now())
        except HyperliquidSDKMissingError as error:
            state = ConnectorState(
                venue="hyperliquid",
                kind="public-data",
                mode="read-only-testnet",
                credentials_required=False,
                read_only=True,
                wired=False,
                state="degraded",
                detail=f"Missing software: {error}",
                last_checked_at=_utc_now().isoformat(),
            )
        except HyperliquidError as error:
            state = ConnectorState(
                venue="hyperliquid",
                kind="public-data",
                mode="read-only-testnet",
                credentials_required=False,
                read_only=True,
                wired=True,
                state="degraded",
                detail=(
                    f"Unreachable: {error}. The fetch falls back to the seeded "
                    "demo book, labeled synthetic."
                ),
                last_checked_at=_utc_now().isoformat(),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        else:
            state = ConnectorState(
                venue="hyperliquid",
                kind="public-data",
                mode="read-only-testnet",
                credentials_required=False,
                read_only=True,
                wired=True,
                state="ok",
                detail=(
                    "Testnet answers; l2Book for BTC carries "
                    f"{len(payload.get('levels', []))} level arrays."
                ),
                last_checked_at=_utc_now().isoformat(),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        self._probes["hyperliquid"] = state
        return state

    def probe_moomoo(self) -> ConnectorState:
        from quantmesh.moomoo.opend import (
            OpenDAuthRequiredError,
            OpenDSdkMissingError,
            OpenDUnavailableError,
            SdkTransport,
        )
        from quantmesh.settings import settings

        start = time.perf_counter()
        transport = SdkTransport(
            host=settings.moomoo_opend_host,
            port=settings.moomoo_opend_port,
            connect_timeout_s=settings.moomoo_opend_connect_timeout_s,
            request_timeout_s=settings.moomoo_opend_request_timeout_s,
        )
        try:
            report = transport.probe()
        except OpenDSdkMissingError as error:
            state = ConnectorState(
                venue="moomoo",
                kind="execution-sim",
                mode="sandbox",
                credentials_required=True,
                read_only=False,
                wired=False,
                state="degraded",
                detail=f"Missing software: {error}",
                last_checked_at=_utc_now().isoformat(),
            )
        except (OpenDUnavailableError, OpenDAuthRequiredError) as error:
            state = ConnectorState(
                venue="moomoo",
                kind="execution-sim",
                mode="sandbox",
                credentials_required=True,
                read_only=False,
                wired=False,
                state="unavailable",
                detail=f"OpenD unreachable or refused: {error}",
                last_checked_at=_utc_now().isoformat(),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        else:
            capabilities = ", ".join(name for name, value in report.items() if value)
            state = ConnectorState(
                venue="moomoo",
                kind="execution-sim",
                mode="sandbox",
                credentials_required=True,
                read_only=False,
                wired=True,
                state="ok",
                detail=f"Local OpenD answers: {capabilities}.",
                last_checked_at=_utc_now().isoformat(),
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        self._probes["moomoo"] = state
        return state

    def probe_all(self) -> list[ConnectorState]:
        self.probe_hyperliquid()
        self.probe_moomoo()
        return self.panel()

    # -- credential-free public data path -----------------------------------

    def fetch_public(self, symbols: list[str]) -> dict[str, object]:
        """Read-only testnet l2Book snapshots, cached with provenance.

        Each symbol yields one row: a live snapshot labeled
        ``hyperliquid-public`` (cached under ``<root>/.datalink``), or
        the seeded fixture book labeled ``fixture-fallback`` with
        ``fallback_of`` and the reason — an unreachable venue degrades
        deterministically, never into a blank page. A rate-limited
        answer is retried once with a short backoff before falling back.
        """
        rows: list[dict[str, object]] = []
        for symbol in symbols:
            coin = _coin_of(symbol)
            try:
                payload = self._fetch_with_retry(coin)
            except HyperliquidSDKMissingError as error:
                rows.append(
                    self._fallback_row(
                        symbol,
                        reason=f"Missing software: {error}",
                        degraded="missing-software",
                    )
                )
                continue
            except HyperliquidError as error:
                rows.append(
                    self._fallback_row(
                        symbol,
                        reason=f"Unreachable: {error}",
                        degraded="rate-limited" if _rate_limited(str(error)) else "network",
                    )
                )
                continue
            bids = payload.get("levels", [{}])[0] if payload.get("levels") else []
            asks = payload.get("levels", [{}])[1] if len(payload.get("levels", [])) > 1 else []
            best_bid = float(bids[0]["px"]) if bids else None
            best_ask = float(asks[0]["px"]) if asks else None
            cache_path = self._cache_public(coin, symbol, payload)
            rows.append(
                {
                    "symbol": symbol,
                    "coin": coin,
                    "source": "hyperliquid-public",
                    "synthetic": False,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "levels": sum(len(levels) for levels in payload.get("levels", [])),
                    "fetched_at": _utc_now().isoformat(),
                    "cache": cache_path,
                    "reason": None,
                }
            )
        report: dict[str, object] = {
            "venue": "hyperliquid",
            "read_only": True,
            "synthetic": False,
            "rows": rows,
            "cached_entries": self.cache_manifest(),
            "fetched_at": _utc_now().isoformat(),
        }
        self._last_fetch = report
        return report

    def _fetch_with_retry(self, coin: str) -> dict:
        try:
            return self.rest.l2_book(coin, at=_utc_now())
        except HyperliquidError as error:
            if not _rate_limited(str(error)):
                raise
            time.sleep(1.0)  # one bounded retry for rate limits
            return self.rest.l2_book(coin, at=_utc_now())

    def _fallback_row(
        self, symbol: str, *, reason: str, degraded: str
    ) -> dict[str, object]:
        return {
            "symbol": symbol,
            "coin": _coin_of(symbol),
            "source": "fixture-fallback",
            "synthetic": True,
            "fallback_of": "hyperliquid-public",
            "degraded": degraded,
            "best_bid": None,
            "best_ask": None,
            "levels": 0,
            "fetched_at": _utc_now().isoformat(),
            "cache": None,
            "reason": reason,
        }

    def _cache_public(self, coin: str, symbol: str, payload: dict) -> str:
        directory = self.root / _DATALINK_ROOT / _PUBLIC_CACHE
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{coin}.json"
        entry = {
            "symbol": symbol,
            "coin": coin,
            "source": "hyperliquid-public",
            "synthetic": False,
            "fetched_at": _utc_now().isoformat(),
            "payload": payload,
        }
        descriptor, temp_name = __import__("tempfile").mkstemp(
            dir=directory, prefix=".", suffix=".tmp"
        )
        try:
            with __import__("os").fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(entry, handle)
            __import__("os").replace(temp_name, path)
        finally:
            if Path(temp_name).exists():
                Path(temp_name).unlink()
        return str(path.relative_to(self.root))

    def cache_manifest(self) -> list[dict[str, object]]:
        """The on-disk cache: per-coin source/fetched_at summaries."""
        directory = self.root / _DATALINK_ROOT / _PUBLIC_CACHE
        if not directory.is_dir():
            return []
        entries: list[dict[str, object]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # a torn cache entry is re-fetched, never fatal
            entries.append(
                {
                    "coin": path.stem,
                    "symbol": entry.get("symbol"),
                    "source": entry.get("source"),
                    "synthetic": entry.get("synthetic"),
                    "fetched_at": entry.get("fetched_at"),
                    "cache": str(path.relative_to(self.root)),
                }
            )
        return entries

    # -- file import ---------------------------------------------------------

    def parse_upload(self, filename: str, data: bytes) -> ImportPreview:
        if len(data) > MAX_IMPORT_BYTES:
            raise ValueError(
                f"file {filename!r} is {len(data) / 1024 / 1024:.1f} MiB; the import "
                f"path accepts at most {MAX_IMPORT_BYTES / 1024 / 1024:.0f} MiB"
            )
        frame = _read_upload(filename, data)
        session_id = uuid.uuid4().hex[:12]
        columns = [
            {
                "name": column,
                "inferred": _infer_dtype(frame[column]),
                "samples": [
                    _native(frame[column].iloc[index])
                    for index in range(min(3, len(frame)))
                    if not pd.isna(frame[column].iloc[index])
                ],
            }
            for column in frame.columns
        ]
        preview = [
            {column: _native(frame[column].iloc[index]) for column in frame.columns}
            for index in range(min(5, len(frame)))
        ]
        result = ImportPreview(
            session_id=session_id,
            filename=filename,
            format=Path(filename).suffix.lstrip(".").upper(),
            rows=len(frame),
            columns=columns,
            preview=preview,
            suggested_mapping=_suggest_mapping(list(frame.columns)),
        )
        self._sessions[session_id] = {
            "filename": filename,
            "frame": frame,
        }
        return result

    def commit_import(self, body: _CommitBody) -> dict[str, object]:
        """Validate every row, write the accepted bars, create the manifest.

        Refuses to open an existing dataset: imports may only create new
        datasets under ``<root>/market/lake``, never touch seeded state.
        Returns accepted/rejected counts with the rejection reasons and
        the fresh manifest's coverage.
        """
        session = self._sessions.get(body.session_id)
        if session is None:
            raise ValueError(
                "import session not found — upload the file again (sessions are "
                "ephemeral and reset clears them)"
            )
        frame = session["frame"]  # type: ignore[assignment]
        try:
            validate_dataset_name(body.dataset)
            validate_symbol(body.symbol)
            venue = Venue(body.venue)
            interval_to_timedelta(body.interval)
            instrument_type = InstrumentType(body.instrument_type)
        except ValueError as error:
            raise ValueError(f"import refused: {error}") from error

        missing = [field for field in REQUIRED_FIELDS if field not in body.mapping]
        if missing:
            raise ValueError(
                f"import refused: no column mapped for {', '.join(missing)}"
            )
        unknown = [
            canonical for canonical in body.mapping if canonical not in CANONICAL_FIELDS
        ]
        if unknown:
            raise ValueError(
                f"import refused: {', '.join(unknown)} is not a canonical field"
            )
        for canonical, column in body.mapping.items():
            if column not in frame.columns:
                raise ValueError(
                    f"import refused: mapped column {column!r} for {canonical} "
                    "does not exist in the file"
                )

        # The existing-dataset gate: imports never overwrite seeded state.
        lake = Lake(self.root / "market" / "lake")
        if (lake.root / body.dataset / MANIFEST_NAME).exists():
            raise ValueError(
                f"import refused: dataset {body.dataset!r} already exists — "
                "imports create new datasets and never overwrite seeded state"
            )

        bars: list[Bar] = []
        rejections: list[dict[str, object]] = []
        records = frame.to_dict("records")
        for row_index, row in enumerate(records):
            try:
                timestamp = _parse_timestamp(row[body.mapping["timestamp"]])
                open_ = _parse_number(row[body.mapping["open"]], "open")
                high = _parse_number(row[body.mapping["high"]], "high")
                low = _parse_number(row[body.mapping["low"]], "low")
                close = _parse_number(row[body.mapping["close"]], "close")
                volume = (
                    _parse_number(row[body.mapping["volume"]], "volume")
                    if "volume" in body.mapping
                    else 0.0
                )
            except ValueError as error:
                rejections.append({"row": row_index + 2, "reason": str(error)})
                continue
            if low > high:
                rejections.append(
                    {"row": row_index + 2, "reason": f"low {low} exceeds high {high}"}
                )
                continue
            bars.append(
                Bar(
                    instrument=Instrument(
                        symbol=body.symbol,
                        venue=venue,
                        instrument_type=instrument_type,
                        currency="USD",
                    ),
                    timestamp=timestamp,
                    interval=body.interval,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )

        if not bars:
            raise ValueError(
                "import refused: no row survived validation — fix the file or the "
                "mapping and upload again"
            )
        lake.write_bars(body.dataset, bars)
        manifest = ManifestWriter(lake.root).generate(
            body.dataset,
            source="operator-import",
            license=body.license,
            data_class=DatasetClass.OBSERVED,
            generated_at=_utc_now(),
        )
        return {
            "dataset": manifest.dataset,
            "source": manifest.source,
            "license": manifest.license,
            "revision": manifest.revision,
            "generated_at": manifest.generated_at.isoformat(),
            "accepted": len(bars),
            "rejected": len(rejections),
            "rejections": rejections[:MAX_REJECTIONS_REPORTED],
            "coverage": [
                {
                    "interval": entry.interval,
                    "venue": entry.venue.value,
                    "symbol": entry.symbol,
                    "rows": entry.rows,
                    "start": entry.start.isoformat(),
                    "end": entry.end.isoformat(),
                }
                for entry in manifest.coverage
            ],
        }

    def imports(self) -> list[dict[str, object]]:
        """Committed operator imports: manifest summaries under the lake."""
        lake = Lake(self.root / "market" / "lake")
        if not lake.root.is_dir():
            return []
        result: list[dict[str, object]] = []
        for manifest_path in sorted(lake.root.glob(f"*/{MANIFEST_NAME}")):
            try:
                manifest = DatasetManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception:  # noqa: BLE001 - a torn manifest is listed, never fatal
                continue
            if manifest.source != "operator-import":
                continue
            result.append(
                {
                    "dataset": manifest.dataset,
                    "source": manifest.source,
                    "license": manifest.license,
                    "revision": manifest.revision,
                    "generated_at": manifest.generated_at.isoformat(),
                    "series": len(manifest.coverage),
                    "rows": sum(entry.rows for entry in manifest.coverage),
                    "start": (
                        min(entry.start for entry in manifest.coverage).isoformat()
                        if manifest.coverage
                        else None
                    ),
                    "end": (
                        max(entry.end for entry in manifest.coverage).isoformat()
                        if manifest.coverage
                        else None
                    ),
                }
            )
        return result

    def reset(self) -> None:
        """Clear session state; a demo reset also wipes the datalink cache."""
        self._probes.clear()
        self._last_fetch = None
        self._sessions.clear()
        cache = self.root / _DATALINK_ROOT
        if cache.is_dir():
            for path in sorted(cache.rglob("*"), reverse=True):
                try:
                    path.unlink() if path.is_file() else path.rmdir()
                except OSError:
                    pass


def _require_runtime(request: Request) -> DatalinkService:
    service = getattr(request.app.state, "datalink", None)
    if not isinstance(service, DatalinkService):
        raise HTTPException(status_code=404, detail="no demo runtime is attached")
    return service


def datalink_router() -> APIRouter:
    """The Phase D surface: connector panel, public fetch, imports.

    Mounted under ``/api`` only (the SPA's surface); every write is
    origin-guarded like the other JSON POSTs.
    """
    router = APIRouter()

    @router.get("/demo/connectors")
    def connectors(request: Request) -> list[ConnectorState]:
        return _require_runtime(request).panel()

    @router.post("/demo/connectors/probe")
    def connectors_probe(request: Request) -> list[ConnectorState]:
        service = _require_runtime(request)
        _json_guard_origin(request, "connector probe")
        return service.probe_all()

    @router.post("/demo/datalink/fetch")
    def datalink_fetch(request: Request, body: _FetchBody) -> dict[str, object]:
        service = _require_runtime(request)
        _json_guard_origin(request, "public data fetch")
        try:
            return service.fetch_public(body.symbols)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/demo/datalink/cache")
    def datalink_cache(request: Request) -> list[dict[str, object]]:
        return _require_runtime(request).cache_manifest()

    @router.post("/demo/import")
    def demo_import(
        request: Request, file: UploadFile = File(...)
    ) -> ImportPreview:
        service = _require_runtime(request)
        _json_guard_origin(request, "file import")
        data = file.file.read()
        try:
            return service.parse_upload(file.filename or "upload", data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/demo/import/commit")
    def demo_import_commit(request: Request, body: _CommitBody) -> dict[str, object]:
        service = _require_runtime(request)
        _json_guard_origin(request, "import commit")
        try:
            return service.commit_import(body)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/demo/imports")
    def demo_imports(request: Request) -> list[dict[str, object]]:
        return _require_runtime(request).imports()

    return router
