"""Bounded local SPY snapshot preservation and independently recomputed checks.

This adapter never grants entitlement, point-in-time validity or order authority.
Issuer XLSX bytes are retained, not independently parsed or certified.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import tempfile
import threading
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.calendars import XNYS_REGULAR_VERSION, CalendarService, SessionPolicy
from quantmesh.data.objects import ObjectIntegrityError, ObjectRef, ObjectStore, is_reparse_point

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 16 * 1024 * 1024
MAX_BARS = 10000
YAHOO_PATH = "raw/yahoo-SPY-20150101-20261016.body"
MEMBERS = frozenset(
    {
        "manifest.json",
        "normalized-bars.csv",
        "normalized-distributions.json",
        "calendar-sessions.csv",
        "data-quality.json",
        YAHOO_PATH,
        "raw/issuer-distribution-history.body",
        "raw/issuer-SPY-nav-history.body",
    }
)
BAR_FIELDS = "date,open,high,low,close,volume,timestamp_utc,dividend".split(",")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class SnapshotInputError(ValueError):
    """Fixed public error code for a malformed or unsupported package."""


class SnapshotTooLarge(SnapshotInputError):
    """The compressed or expanded package exceeds its fixed size budget."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("UTC required")
    return parsed.astimezone(UTC)


def _date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("ISO date required")
    return parsed


class SnapshotSource(_Strict):
    provider: str = Field(min_length=1, max_length=4096)
    feed: str = Field(min_length=1, max_length=4096)
    url: str = Field(min_length=1, max_length=4096)
    received_at: str = Field(min_length=1, max_length=100)
    license_scope: str = Field(min_length=1, max_length=4096)
    license_evidence: str = Field(min_length=1, max_length=4096)
    price_unit: str = Field(min_length=1, max_length=100)
    volume_unit: str = Field(min_length=1, max_length=100)
    session_semantics: str = Field(min_length=1, max_length=4096)
    pit_status: str = Field(min_length=1, max_length=4096)

    @field_validator("received_at")
    @classmethod
    def received_is_utc(cls, value):
        _utc(value)
        return value


class _Manifest(_Strict):
    schema_id: Literal["qm.spy-daily.snapshot.v1"]
    symbol: Literal["SPY"]
    evidence_kind: Literal["real_snapshot", "fixture"]
    required_start: str
    required_end: str
    source: SnapshotSource
    files: dict[str, str]

    @model_validator(mode="after")
    def validate_contract(self):
        start, end = _date(self.required_start), _date(self.required_end)
        if not date(2000, 1, 3) <= start <= end <= date(2035, 12, 31):
            raise ValueError("unsupported range")
        if set(self.files) != MEMBERS - {"manifest.json"}:
            raise ValueError("unexpected members")
        if any(not _DIGEST.fullmatch(value) for value in self.files.values()):
            raise ValueError("invalid digest")
        return self


class _Index(_Strict):
    schema_version: Literal[1]
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive: ObjectRef
    members: dict[str, ObjectRef]
    report: ObjectRef

    @model_validator(mode="after")
    def refs_match(self):
        if self.snapshot_id != self.archive.digest or set(self.members) != MEMBERS:
            raise ValueError("invalid refs")
        return self


def _json(payload: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ValueError("nonfinite JSON")

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=nonfinite)


def _bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _unpack(payload: bytes) -> tuple[_Manifest, dict[str, bytes]]:
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise SnapshotTooLarge("snapshot_too_large")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) != 8 or {info.filename for info in infos} != MEMBERS:
                raise ValueError("unexpected members")
            total = 0
            files = {}
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.flag_bits & 1
                    or info.is_dir()
                    or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or info.external_attr & 0x10
                    or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                ):
                    raise ValueError("unsupported member")
                total += info.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise SnapshotTooLarge("snapshot_too_large")
                with archive.open(info) as stream:
                    value = stream.read(min(info.file_size + 1, MAX_EXPANDED_BYTES + 1))
                if len(value) != info.file_size:
                    raise ValueError("invalid length")
                files[info.filename] = value
        manifest = _Manifest.model_validate(_json(files["manifest.json"]))
        for path, digest in manifest.files.items():
            if hashlib.sha256(files[path]).hexdigest() != digest:
                raise ValueError("invalid hash")
        return manifest, files
    except SnapshotInputError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RuntimeError,
        EOFError,
        zipfile.BadZipFile,
        NotImplementedError,
        UnicodeError,
    ) as error:
        raise SnapshotInputError("snapshot_invalid") from error


def _csv(payload: bytes, fields: list[str], limit=MAX_BARS):
    stream = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    if stream.fieldnames != fields:
        raise ValueError("invalid CSV columns")
    result = []
    for row in stream:
        if None in row or None in row.values() or len(result) >= limit:
            raise ValueError("invalid CSV rows")
        result.append(row)
    return result


def _location(day=None, row=None, field="", expected=None, actual=None):
    return {
        "date": day,
        "row": row,
        "field": field,
        "expected": str(expected)[:160] if expected is not None else None,
        "actual": str(actual)[:160] if actual is not None else None,
    }


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


class SnapshotCatalog:
    """Content-addressed packages and pinned initial reports, outside demo reset."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None):
        self.root = Path(root).absolute()
        self.objects = ObjectStore(self.root)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._calendar = None

    def _sessions(self, start: date, end: date):
        if self._calendar is None:
            self._calendar = CalendarService()
        return self._calendar.sessions("XNYS", start, end, policy=SessionPolicy.REGULAR)

    def _now(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise ValueError("snapshot clock must be UTC")
        return now.astimezone(UTC)

    def _index_path(self, snapshot_id):
        if not isinstance(snapshot_id, str) or not _DIGEST.fullmatch(snapshot_id):
            raise KeyError("snapshot_unknown")
        path = self.root / "snapshots" / f"{snapshot_id}.json"
        # ObjectStore applies the same no-reparse discipline to its own tree.
        for component in (self.root, path.parent, path):
            if is_reparse_point(component):
                raise ObjectIntegrityError("snapshot index is not a regular local path")
        return path

    def import_archive(self, payload: bytes) -> dict:
        manifest, files = _unpack(payload)
        snapshot_id = hashlib.sha256(payload).hexdigest()
        with self._lock:
            index_path = self._index_path(snapshot_id)
            if index_path.exists():
                return self.get(snapshot_id)
            now = self._now()
            try:
                report = self._qualify(manifest, files, now)
            except (
                ValueError,
                TypeError,
                KeyError,
                IndexError,
                AttributeError,
                csv.Error,
                UnicodeError,
                OverflowError,
                RecursionError,
            ) as error:
                raise SnapshotInputError("snapshot_invalid") from error
            refs = {
                path: self.objects.put_bytes("application/octet-stream", value)
                for path, value in files.items()
            }
            report.update(
                {
                    "schema_version": 1,
                    "snapshot_id": snapshot_id,
                    "imported_at": now.isoformat(),
                    "symbol": manifest.symbol,
                    "evidence_kind": manifest.evidence_kind,
                    "source": manifest.source.model_dump(),
                    "lineage": {
                        "archive_sha256": snapshot_id,
                        "files": [
                            {"path": path, "sha256": ref.digest, "bytes": ref.byte_length}
                            for path, ref in sorted(refs.items())
                        ],
                        "normalized_sha256": refs["normalized-bars.csv"].digest,
                        "calendar_id": "XNYS",
                        "calendar_version": XNYS_REGULAR_VERSION,
                        "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    },
                }
            )
            report_ref = self.objects.put_bytes("application/json", _bytes(report))
            archive_ref = self.objects.put_bytes("application/zip", payload)
            index = _Index(
                schema_version=1,
                snapshot_id=snapshot_id,
                archive=archive_ref,
                members=refs,
                report=report_ref,
            )
            index_path.parent.mkdir(parents=True, exist_ok=True)
            self._index_path(snapshot_id)
            descriptor, temporary = tempfile.mkstemp(dir=index_path.parent, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(index.model_dump_json().encode())
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, index_path)
                except FileExistsError:
                    pass  # Concurrent identical import preserves the first pinned receipt.
            finally:
                os.unlink(temporary)
            return self.get(snapshot_id)

    def _read(self, snapshot_id):
        path = self._index_path(snapshot_id)
        try:
            if path.stat().st_size > 65536 or not stat.S_ISREG(path.stat().st_mode):
                raise ObjectIntegrityError("snapshot index invalid")
            index = _Index.model_validate(_json(path.read_bytes()))
            if index.snapshot_id != snapshot_id:
                raise ObjectIntegrityError("snapshot index identity mismatch")
            archive = self.objects.get_bytes(index.archive)
            manifest, original = _unpack(archive)
            for name, ref in index.members.items():
                if self.objects.get_bytes(ref) != original[name]:
                    raise ObjectIntegrityError("snapshot member mismatch")
            report_bytes = self.objects.get_bytes(index.report)
            report = _json(report_bytes)
            lineage = report["lineage"]
            expected_files = [
                {"path": name, "sha256": ref.digest, "bytes": ref.byte_length}
                for name, ref in sorted(index.members.items())
            ]
            if (
                report["snapshot_id"] != snapshot_id
                or report["schema_version"] != 1
                or report["source"] != manifest.source.model_dump()
                or lineage["archive_sha256"] != snapshot_id
                or lineage["files"] != expected_files
                or lineage["normalized_sha256"] != index.members["normalized-bars.csv"].digest
            ):
                raise ObjectIntegrityError("snapshot report identity mismatch")
            return index, report, archive, report_bytes
        except FileNotFoundError as error:
            raise KeyError("snapshot_unknown") from error
        except ObjectIntegrityError:
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
            raise ObjectIntegrityError("snapshot index or objects invalid") from error

    def list(self) -> list[dict]:
        self._index_path("0" * 64)
        directory = self.root / "snapshots"
        if not directory.exists():
            return []
        return [self.get(path.stem) for path in sorted(directory.glob("*.json"))]

    def get(self, snapshot_id: str) -> dict:
        index, report, _, _ = self._read(snapshot_id)
        report["report_digest"] = index.report.digest
        report["freshness"] = self._freshness(report["coverage"]["last_date"], self._now())
        return report

    def archive_bytes(self, snapshot_id: str) -> bytes:
        return self._read(snapshot_id)[2]

    def report_bytes(self, snapshot_id: str) -> bytes:
        """The initial JSON omits its own digest; API metadata supplies that hash."""
        return self._read(snapshot_id)[3]

    def _freshness(self, last_day, now):
        result = {
            "as_of": now.isoformat(),
            "latest_complete_session": None,
            "last_session": last_day,
            "age_sessions": None,
            "status": "INSUFFICIENT",
        }
        if not date(2000, 1, 3) <= now.date() <= date(2035, 12, 31):
            return result
        start = max(date(2000, 1, 3), now.date() - timedelta(days=30))
        if last_day:
            start = max(date(2000, 1, 3), min(start, _date(last_day)))
        sessions = self._sessions(start, now.date())
        completed = [
            s.session_date.isoformat()
            for s in sessions
            if s.close_at + timedelta(minutes=30) <= now
        ]
        if not completed:
            return result
        latest = completed[-1]
        result["latest_complete_session"] = latest
        if last_day and last_day <= latest:
            age = sum(day > last_day for day in completed)
            result.update(age_sessions=age, status="CURRENT" if age == 0 else "STALE")
        return result

    def _qualify(self, manifest, files, now):
        rows = _csv(files["normalized-bars.csv"], BAR_FIELDS)
        retained_calendar = _csv(
            files["calendar-sessions.csv"], ["", "open", "break_start", "break_end", "close"]
        )
        historical = _json(files["data-quality.json"])
        if not isinstance(historical, dict):
            raise ValueError("quality evidence must be an object")
        issuer = _json(files["normalized-distributions.json"])
        if not isinstance(issuer, list) or len(issuer) > MAX_BARS:
            raise ValueError("invalid issuer events")
        issuer_events = {}
        for event in issuer:
            if not isinstance(event, dict) or set(event) != {"ex_date", "pay_date", "amount"}:
                raise ValueError("invalid issuer event schema")
            day = _date(event["ex_date"]).isoformat()
            pay = _date(event["pay_date"])
            amount = _number(event["amount"])
            if day in issuer_events or pay < _date(day) or amount is None or amount < 0:
                raise ValueError("invalid issuer event")
            issuer_events[day] = amount
        chart = _json(files[YAHOO_PATH])["chart"]
        if chart.get("error") is not None or len(chart["result"]) != 1:
            raise ValueError("invalid Yahoo chart")
        yahoo = chart["result"][0]
        meta = yahoo["meta"]
        quote = yahoo["indicators"]["quote"][0]
        timestamps = yahoo["timestamp"]
        if not isinstance(timestamps, list) or len(timestamps) > MAX_BARS:
            raise ValueError("invalid Yahoo timestamps")
        if any(
            not isinstance(quote[key], list) or len(quote[key]) != len(timestamps)
            for key in ("open", "high", "low", "close", "volume")
        ):
            raise ValueError("invalid Yahoo quote arrays")
        yahoo_by_date = {}
        yahoo_issues = []
        for position, timestamp in enumerate(timestamps):
            if isinstance(timestamp, bool) or not isinstance(timestamp, int):
                raise ValueError("invalid Yahoo timestamp")
            moment = datetime.fromtimestamp(timestamp, UTC)
            day = moment.date().isoformat()
            if day in yahoo_by_date:
                yahoo_issues.append(_location(day, field="timestamp", actual="duplicate"))
            yahoo_by_date[day] = (moment, {key: quote[key][position] for key in quote})
        dividends = yahoo.get("events", {}).get("dividends", {})
        if not isinstance(dividends, dict) or len(dividends) > MAX_BARS:
            raise ValueError("invalid Yahoo dividends")
        yahoo_events = {}
        for event in dividends.values():
            timestamp = event["date"]
            if isinstance(timestamp, bool) or not isinstance(timestamp, int):
                raise ValueError("invalid Yahoo event date")
            day = datetime.fromtimestamp(timestamp, UTC).date().isoformat()
            amount = _number(event["amount"])
            if amount is None or amount < 0 or day in yahoo_events:
                raise ValueError("invalid Yahoo event amount")
            yahoo_events[day] = amount
        sessions = self._sessions(_date(manifest.required_start), _date(manifest.required_end))
        schedule = {session.session_date.isoformat(): session for session in sessions}
        checks = []

        def check(code, message, locations=(), *, insufficient=False):
            checks.append(
                {
                    "code": code,
                    "status": "INSUFFICIENT"
                    if insufficient
                    else ("REJECT" if locations else "PASS"),
                    "count": len(locations),
                    "message": message,
                    "locations": list(locations),
                }
            )

        values, times, order, unfinished, alignment = [], [], [], [], yahoo_issues
        issuer_alignment = []
        dates = []
        bars = []
        previous = None
        for position, row in enumerate(rows, start=2):
            raw_day = row["date"]
            try:
                day = _date(raw_day).isoformat()
            except ValueError:
                day = None
                times.append(_location(None, position, "date", "ISO date", raw_day))
            if day is not None:
                dates.append(day)
                if previous is not None and day <= previous:
                    order.append(_location(day, position, "date", "strict increasing unique", day))
                previous = day
            numbers = {
                key: _number(row[key])
                for key in ("open", "high", "low", "close", "volume", "dividend")
            }
            for key, number in numbers.items():
                if (
                    number is None
                    or (key in {"open", "high", "low", "close"} and number <= 0)
                    or (key in {"volume", "dividend"} and number < 0)
                    or (key == "volume" and number != int(number))
                ):
                    values.append(_location(day, position, key, "finite valid unit", row[key]))
            if all(numbers[key] is not None for key in ("open", "high", "low", "close")):
                if (
                    not numbers["low"]
                    <= min(numbers["open"], numbers["close"])
                    <= max(numbers["open"], numbers["close"])
                    <= numbers["high"]
                ):
                    values.append(_location(day, position, "OHLC", "low<=open,close<=high"))
            try:
                timestamp = _utc(row["timestamp_utc"])
                if timestamp.date().isoformat() != day:
                    raise ValueError("date mismatch")
                if day in schedule and timestamp != schedule[day].open_at:
                    raise ValueError("open mismatch")
            except ValueError:
                timestamp = None
                times.append(
                    _location(day, position, "timestamp_utc", "XNYS UTC open", row["timestamp_utc"])
                )
            if day in schedule and schedule[day].close_at + timedelta(minutes=30) > now:
                unfinished.append(_location(day, position, "close_at", "completed +30min grace"))
            raw = yahoo_by_date.get(day)
            if raw is None:
                alignment.append(_location(day, position, "date", "retained Yahoo row"))
            else:
                if timestamp != raw[0]:
                    alignment.append(
                        _location(day, position, "timestamp_utc", raw[0], row["timestamp_utc"])
                    )
                for key in ("open", "high", "low", "close", "volume"):
                    expected = _number(raw[1][key])
                    actual = numbers[key]
                    if (
                        expected is None
                        or actual is None
                        or abs(expected - actual) > (0 if key == "volume" else 1e-8)
                    ):
                        alignment.append(_location(day, position, key, raw[1][key], row[key]))
            # The retained normalizer derives the dividend column from issuer
            # JSON. Yahoo is a separate comparison source at the 0.001 USD
            # corporate-action tolerance, never the CSV dividend authority.
            expected_dividend = issuer_events.get(day, 0)
            if numbers["dividend"] is None or abs(numbers["dividend"] - expected_dividend) > 1e-8:
                issuer_alignment.append(
                    _location(day, position, "dividend", expected_dividend, row["dividend"])
                )
            bars.append({"date": day, **numbers, "timestamp_utc": row["timestamp_utc"][:100]})
        for day in sorted(set(yahoo_by_date) - set(dates)):
            alignment.append(_location(day, field="date", expected="normalized Yahoo row"))
        if meta.get("symbol") != "SPY" or meta.get("currency") != "USD":
            alignment.append(_location(field="meta", expected="SPY/USD"))
        missing = sorted(set(schedule) - set(dates))
        unexpected = sorted(set(dates) - set(schedule))
        coverage = [
            _location(day, field="date", expected="required XNYS session") for day in missing
        ]
        coverage += [
            _location(day, field="date", actual="unexpected session") for day in unexpected
        ]
        if not rows:
            coverage.append(_location(field="rows", expected="nonempty daily bars", actual=0))
        calendar_issues = []
        retained_days = []
        for position, row in enumerate(retained_calendar, start=2):
            day = row[""]
            retained_days.append(day)
            session = schedule.get(day)
            try:
                if (
                    session is None
                    or _utc(row["open"]) != session.open_at
                    or _utc(row["close"]) != session.close_at
                    or row["break_start"]
                    or row["break_end"]
                ):
                    raise ValueError("calendar mismatch")
            except ValueError:
                calendar_issues.append(_location(day, position, "calendar", "pinned XNYS schedule"))
        if retained_days != sorted(schedule):
            calendar_issues.append(
                _location(field="calendar_sessions", expected="exact pinned sessions")
            )
        check("bar_values", "Prices, quantities and OHLC bounds recomputed.", values)
        check("bar_time", "UTC dates and XNYS session opens recomputed.", times)
        check("bar_order", "Daily rows must be unique and strictly chronological.", order)
        check("session_coverage", "Declared range compared with pinned XNYS sessions.", coverage)
        check(
            "unfinished_session",
            "Daily bars require session close plus 30 minute research grace.",
            unfinished,
        )
        check(
            "calendar_alignment",
            "Retained calendar compared independently with pinned XNYS.",
            calendar_issues,
        )
        check(
            "yahoo_alignment",
            "Normalized prices, UTC times and volume compared with retained Yahoo bytes.",
            alignment,
        )
        check(
            "issuer_alignment",
            "CSV dividends compared with retained issuer-derived JSON at 1e-8 USD tolerance; "
            "the raw issuer XLSX lineage remains unverified.",
            issuer_alignment,
        )
        unit_issues = []
        for field, expected in (("price_unit", "USD/share"), ("volume_unit", "shares")):
            if getattr(manifest.source, field) != expected:
                unit_issues.append(
                    _location(
                        field=field, expected=expected, actual=getattr(manifest.source, field)
                    )
                )
        check("units", "SPY requires USD/share prices and share quantities.", unit_issues)
        selected_issuer = {
            day: amount
            for day, amount in issuer_events.items()
            if manifest.required_start <= day <= manifest.required_end
        }
        selected_yahoo = {
            day: amount
            for day, amount in yahoo_events.items()
            if manifest.required_start <= day <= manifest.required_end
        }
        conflicts = sorted(
            day
            for day in set(selected_issuer) | set(selected_yahoo)
            if day not in selected_issuer
            or day not in selected_yahoo
            or abs(selected_issuer[day] - selected_yahoo[day]) > 0.001
        )
        check(
            "corporate_actions",
            (
                "Issuer-derived JSON and Yahoo events disagree on "
                + ", ".join(conflicts)
                + " at 0.001 USD tolerance."
                if conflicts
                else "Issuer-derived JSON and Yahoo events compared at 0.001 USD tolerance."
            ),
            [
                _location(
                    day,
                    field="amount",
                    expected=selected_issuer.get(day),
                    actual=selected_yahoo.get(day),
                )
                for day in conflicts
            ],
            insufficient=bool(conflicts),
        )
        for code, message in (
            (
                "source_rights",
                "Source license assertions are retained; "
                "usage rights are not independently verified.",
            ),
            (
                "point_in_time",
                "Historical available-at timestamps and revision history "
                "are not independently verified.",
            ),
            (
                "source_session",
                "Pinned XNYS alignment does not independently verify "
                "vendor daily-session semantics.",
            ),
            (
                "issuer_lineage",
                "Raw issuer XLSX bytes retained; derived JSON lineage is asserted, "
                "not independently re-parsed official validation.",
            ),
        ):
            check(code, message, insufficient=True)
        if manifest.evidence_kind == "fixture":
            check(
                "fixture_scope",
                "Synthetic fixture is engineering-only evidence.",
                insufficient=True,
            )
        rejected = any(item["status"] == "REJECT" for item in checks)
        return {
            "coverage": {
                "rows": len(rows),
                "first_date": min(dates) if dates else None,
                "last_date": max(dates) if dates else None,
                "expected_sessions": len(schedule),
                "missing_sessions": missing,
                "unexpected_sessions": unexpected,
            },
            "freshness": self._freshness(max(dates) if dates else None, now),
            "qualification": {
                "status": "REJECT" if rejected else "INSUFFICIENT",
                "structural_status": "REJECT" if rejected else "PASS",
                "allowed_use": (
                    ["engineering_only"]
                    if manifest.evidence_kind == "fixture"
                    else ["inspect_evidence_only"]
                ),
                "R1": "INSUFFICIENT",
                "R2": "INSUFFICIENT",
                "reasons": [item["message"] for item in checks if item["status"] != "PASS"],
            },
            "checks": checks,
            "corporate_actions": {
                "issuer_events": len(selected_issuer),
                "yahoo_events": len(selected_yahoo),
                "conflicts": conflicts,
            },
            "preview": {"head": bars[:5], "tail": bars[-5:]},
        }
