"""Synthetic snapshot bytes exercise import, qualification and immutable reopen."""

import csv
import hashlib
import importlib
import io
import json
import stat
import struct
import zipfile
from datetime import UTC, datetime

import pytest

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
YAHOO = "raw/yahoo-SPY-20150101-20261016.body"


def backend():
    assert importlib.util.find_spec("quantmesh.research.realdata_snapshots") is not None, (
        "P1 snapshot catalog is not implemented"
    )
    return importlib.import_module("quantmesh.research.realdata_snapshots")


def package(*, bars=None, mutate=None, manifest_mutate=None, extras=()):
    """Hand-authored two-day fixture, never copied market bytes."""
    bars = (
        bars
        if bars is not None
        else [
            ["2026-10-15", 100, 102, 99, 101, 1000, "2026-10-15 13:30:00+00:00", 0],
            ["2026-10-16", 101, 103, 100, 102, 1100, "2026-10-16 13:30:00+00:00", 0.5],
        ]
    )
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow("date,open,high,low,close,volume,timestamp_utc,dividend".split(","))
    writer.writerows(bars)
    yahoo = {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "symbol": "SPY",
                        "currency": "USD",
                        "exchangeTimezoneName": "America/New_York",
                    },
                    "timestamp": [1792071000, 1792157400],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100, 101],
                                "high": [102, 103],
                                "low": [99, 100],
                                "close": [101, 102],
                                "volume": [1000, 1100],
                            }
                        ]
                    },
                    "events": {"dividends": {"1792157400": {"date": 1792157400, "amount": 0.5}}},
                }
            ],
        }
    }
    files = {
        "normalized-bars.csv": stream.getvalue().encode(),
        "normalized-distributions.json": json.dumps(
            [{"ex_date": "2026-10-16", "pay_date": "2026-10-30", "amount": 0.5}]
        ).encode(),
        "calendar-sessions.csv": (
            b",open,break_start,break_end,close\n"
            b"2026-10-15,2026-10-15 13:30:00+00:00,,,2026-10-15 20:00:00+00:00\n"
            b"2026-10-16,2026-10-16 13:30:00+00:00,,,2026-10-16 20:00:00+00:00\n"
        ),
        "data-quality.json": b'{"status":"PASS"}',
        YAHOO: json.dumps(yahoo).encode(),
        "raw/issuer-distribution-history.body": b"synthetic unparsed issuer xlsx",
        "raw/issuer-SPY-nav-history.body": b"synthetic unparsed nav xlsx",
    }
    if mutate:
        mutate(files)
    manifest = {
        "schema_id": "qm.spy-daily.snapshot.v1",
        "symbol": "SPY",
        "evidence_kind": "fixture",
        "required_start": "2026-10-15",
        "required_end": "2026-10-16",
        "source": {
            "provider": "Yahoo public chart",
            "feed": "vendor_daily_unverified",
            "url": "https://example.test/SPY",
            "received_at": "2026-10-18T12:00:00Z",
            "license_scope": "local_research_unverified",
            "license_evidence": "unknown",
            "price_unit": "USD/share",
            "volume_unit": "shares",
            "session_semantics": "unverified",
            "pit_status": "unknown",
        },
        "files": {path: hashlib.sha256(value).hexdigest() for path, value in files.items()},
    }
    if manifest_mutate:
        manifest_mutate(manifest)
    files["manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, value in list(files.items()) + list(extras):
            archive.writestr(path, value)
    return output.getvalue()


def test_import_preserves_archive_deduplicates_and_reopens(tmp_path):
    mod = backend()
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    archive = package()
    report = catalog.import_archive(archive)
    assert report["snapshot_id"] == hashlib.sha256(archive).hexdigest()
    assert report["coverage"] == {
        "rows": 2,
        "first_date": "2026-10-15",
        "last_date": "2026-10-16",
        "expected_sessions": 2,
        "missing_sessions": [],
        "unexpected_sessions": [],
    }
    assert report["qualification"]["status"] == "INSUFFICIENT"
    assert report["qualification"]["allowed_use"] == ["engineering_only"]
    assert report["qualification"]["structural_status"] == "PASS"
    assert catalog.import_archive(archive) == report
    reopened = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    assert reopened.get(report["snapshot_id"]) == report
    assert len(reopened.list()) == 1
    assert reopened.archive_bytes(report["snapshot_id"]) == archive
    pinned = reopened.report_bytes(report["snapshot_id"])
    assert hashlib.sha256(pinned).hexdigest() == report["report_digest"]
    assert json.loads(pinned)["freshness"]["status"] == "CURRENT"
    assert len(report["lineage"]["files"]) == 8


@pytest.mark.parametrize(
    "mutator",
    [
        lambda m: m.update(schema_id="unsupported"),
        lambda m: m.update(extra="forbidden"),
        lambda m: m["source"].update(received_at="2026-10-18T12:00:00"),
        lambda m: m["files"].update({YAHOO: "0" * 64}),
    ],
)
def test_schema_and_hash_errors_are_fixed_safe_errors(tmp_path, mutator):
    mod = backend()
    with pytest.raises(mod.SnapshotInputError, match="^snapshot_invalid$"):
        mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
            package(manifest_mutate=mutator)
        )
    assert mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).list() == []


@pytest.mark.parametrize("extras", [[("../escape", b"x")], [(YAHOO, b"duplicate")]])
def test_zip_never_extracts_or_accepts_unexpected_duplicate_members(tmp_path, extras):
    mod = backend()
    with pytest.raises(mod.SnapshotInputError):
        mod.SnapshotCatalog(tmp_path).import_archive(package(extras=extras))
    assert not (tmp_path.parent / "escape").exists()


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda b: b[1].__setitem__(0, "2026-10-15"), "bar_order"),
        (lambda b: b[0].__setitem__(1, "nan"), "bar_values"),
        (lambda b: b[0].__setitem__(2, 90), "bar_values"),
        (lambda b: b[0].__setitem__(5, -1), "bar_values"),
        (lambda b: b[0].__setitem__(6, "2026-10-15 13:30:00"), "bar_time"),
        (lambda b: b[0].__setitem__(4, 100.5), "yahoo_alignment"),
    ],
)
def test_semantically_bad_bars_are_retained_with_located_reject(tmp_path, change, code):
    mod = backend()
    bars = [
        ["2026-10-15", 100, 102, 99, 101, 1000, "2026-10-15 13:30:00+00:00", 0],
        ["2026-10-16", 101, 103, 100, 102, 1100, "2026-10-16 13:30:00+00:00", 0.5],
    ]
    change(bars)
    payload = package(bars=bars)
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_archive(payload)
    assert report["qualification"]["status"] == "REJECT"
    check = next(check for check in report["checks"] if check["code"] == code)
    assert check["status"] == "REJECT"
    assert check["locations"][0]["row"] is not None
    assert catalog.archive_bytes(report["snapshot_id"]) == payload


def test_missing_session_and_unfinished_bar_are_located(tmp_path):
    mod = backend()
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: datetime(2026, 10, 16, 19, tzinfo=UTC))
    report = catalog.import_archive(
        package(
            bars=[
                ["2026-10-16", 101, 103, 100, 102, 1100, "2026-10-16 13:30:00+00:00", 0.5],
            ]
        )
    )
    assert report["coverage"]["missing_sessions"] == ["2026-10-15"]
    assert {c["code"] for c in report["checks"] if c["status"] == "REJECT"} >= {
        "session_coverage",
        "unfinished_session",
        "yahoo_alignment",
    }


def test_conflict_unknown_rights_and_forged_quality_do_not_become_available(tmp_path):
    mod = backend()

    def mutate(files):
        files["normalized-distributions.json"] = (
            b'[{"ex_date":"2026-10-16","pay_date":"2026-10-30","amount":0.8}]'
        )
        files["normalized-bars.csv"] = files["normalized-bars.csv"].replace(
            b",0.5\r\n", b",0.8\r\n"
        )

    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
        package(mutate=mutate, manifest_mutate=lambda m: m.update(evidence_kind="real_snapshot"))
    )
    assert report["qualification"]["status"] == "INSUFFICIENT"
    assert report["corporate_actions"]["conflicts"] == ["2026-10-16"]
    assert report["corporate_actions"]["issuer_events"] == 1
    assert report["corporate_actions"]["yahoo_events"] == 1
    conflict = next(c for c in report["checks"] if c["code"] == "corporate_actions")
    assert "disagree" in conflict["message"].lower()
    assert "2026-10-16" in conflict["message"]
    assert conflict["message"] in report["qualification"]["reasons"]
    assert conflict["locations"] == [
        {"date": "2026-10-16", "row": None, "field": "amount", "expected": "0.8", "actual": "0.5"}
    ]
    assert report["qualification"]["R1"] == "INSUFFICIENT"
    assert report["qualification"]["R2"] == "INSUFFICIENT"
    assert {c["code"] for c in report["checks"] if c["status"] == "INSUFFICIENT"} >= {
        "source_rights",
        "point_in_time",
        "source_session",
        "issuer_lineage",
        "corporate_actions",
    }


def test_wrong_units_are_retained_as_reject(tmp_path):
    mod = backend()
    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
        package(manifest_mutate=lambda m: m["source"].update(price_unit="cents"))
    )
    assert report["qualification"]["status"] == "REJECT"
    assert next(c for c in report["checks"] if c["code"] == "units")["status"] == "REJECT"


def test_freshness_overlay_does_not_rewrite_pinned_report(tmp_path):
    mod = backend()
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_archive(package())
    pinned = catalog.report_bytes(report["snapshot_id"])
    later = mod.SnapshotCatalog(tmp_path, clock=lambda: datetime(2026, 10, 21, 12, tzinfo=UTC))
    current = later.get(report["snapshot_id"])
    assert current["freshness"]["status"] == "STALE"
    assert current["freshness"]["age_sessions"] == 2
    assert later.report_bytes(report["snapshot_id"]) == pinned
    assert current["report_digest"] == report["report_digest"]


def test_corruption_fails_closed_on_reopen_and_download(tmp_path):
    mod = backend()
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_archive(package())
    digest = report["lineage"]["normalized_sha256"]
    target = tmp_path / ".trusted-data-v2" / "objects" / "sha256" / digest[:2] / digest
    target.write_bytes(b"changed")
    for operation in (catalog.get, catalog.archive_bytes, catalog.report_bytes):
        with pytest.raises(mod.ObjectIntegrityError):
            operation(report["snapshot_id"])


def test_package_expansion_and_bar_count_are_bounded(tmp_path):
    mod = backend()
    huge = package(
        mutate=lambda files: files.update(
            {"raw/issuer-SPY-nav-history.body": b"x" * (16 * 1024 * 1024)}
        )
    )
    with pytest.raises(mod.SnapshotTooLarge, match="^snapshot_too_large$"):
        mod.SnapshotCatalog(tmp_path).import_archive(huge)
    rows = [["2026-10-15", 100, 102, 99, 101, 1000, "2026-10-15T13:30:00Z", 0]] * 10001
    with pytest.raises(mod.SnapshotInputError, match="^snapshot_invalid$"):
        mod.SnapshotCatalog(tmp_path).import_archive(package(bars=rows))


@pytest.mark.parametrize("mode", ["symlink", "encrypted"])
def test_symlink_and_encrypted_members_are_rejected_without_writes(tmp_path, mode):
    mod = backend()
    original = package()
    if mode == "symlink":
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, "w") as dest:
            for info in source.infolist():
                if info.filename == YAHOO:
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                dest.writestr(info, source.read(info))
        payload = output.getvalue()
    else:
        payload = bytearray(original)
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            position = payload.find(signature)
            flags = struct.unpack_from("<H", payload, position + offset)[0]
            struct.pack_into("<H", payload, position + offset, flags | 1)
        payload = bytes(payload)
    with pytest.raises(mod.SnapshotInputError, match="^snapshot_invalid$"):
        mod.SnapshotCatalog(tmp_path).import_archive(payload)
    assert not (tmp_path / "snapshots").exists()


def test_unexpected_old_date_is_reject_instead_of_malformed_request(tmp_path):
    mod = backend()
    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
        package(
            bars=[
                ["1990-01-02", 100, 102, 99, 101, 1000, "1990-01-02T14:30:00Z", 0],
            ]
        )
    )
    assert report["qualification"]["status"] == "REJECT"
    assert report["coverage"]["unexpected_sessions"] == ["1990-01-02"]


def test_retained_calendar_and_yahoo_metadata_are_independently_checked(tmp_path):
    mod = backend()

    def mutate(files):
        files["calendar-sessions.csv"] = files["calendar-sessions.csv"].replace(
            b"20:00:00", b"21:00:00"
        )
        source = json.loads(files[YAHOO])
        source["chart"]["result"][0]["meta"]["currency"] = "EUR"
        files[YAHOO] = json.dumps(source).encode()

    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(package(mutate=mutate))
    assert {c["code"] for c in report["checks"] if c["status"] == "REJECT"} >= {
        "calendar_alignment",
        "yahoo_alignment",
    }


def test_source_claims_do_not_prove_rights_pit_or_official_issuer_lineage(tmp_path):
    mod = backend()

    def forged(m):
        m["evidence_kind"] = "real_snapshot"
        m["source"].update(
            license_evidence="verified",
            license_scope="unlimited",
            session_semantics="verified",
            pit_status="verified",
        )

    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
        package(manifest_mutate=forged)
    )
    assert report["qualification"]["status"] == "INSUFFICIENT"
    assert report["qualification"]["allowed_use"] == ["inspect_evidence_only"]


def test_malformed_index_and_report_reference_fail_closed(tmp_path):
    mod = backend()
    catalog = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW)
    report = catalog.import_archive(package())
    path = tmp_path / "snapshots" / f"{report['snapshot_id']}.json"
    index = json.loads(path.read_bytes())
    index["unexpected"] = "malformed"
    path.write_text(json.dumps(index))
    with pytest.raises(mod.ObjectIntegrityError):
        catalog.get(report["snapshot_id"])


def test_research_grace_handles_current_session_before_and_after_close(tmp_path):
    mod = backend()
    before = mod.SnapshotCatalog(tmp_path, clock=lambda: datetime(2026, 10, 16, 20, 29, tzinfo=UTC))
    report = before.import_archive(package())
    assert (
        next(c for c in report["checks"] if c["code"] == "unfinished_session")["status"] == "REJECT"
    )
    after = mod.SnapshotCatalog(tmp_path, clock=lambda: datetime(2026, 10, 16, 20, 30, tzinfo=UTC))
    assert after.get(report["snapshot_id"])["freshness"]["status"] == "CURRENT"
    assert after.get(report["snapshot_id"])["qualification"]["status"] == "REJECT"


def test_empty_bars_are_reject_and_nonfinite_json_is_malformed(tmp_path):
    mod = backend()
    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(package(bars=[]))
    assert report["qualification"]["status"] == "REJECT"
    with pytest.raises(mod.SnapshotInputError):
        mod.SnapshotCatalog(tmp_path).import_archive(
            package(mutate=lambda files: files.update({"data-quality.json": b'{"unsafe":NaN}'}))
        )


@pytest.mark.parametrize("amount,conflicts", [(0.5005, []), (0.503431, ["2026-10-16"])])
def test_csv_dividend_tracks_issuer_normalization_not_yahoo(tmp_path, amount, conflicts):
    mod = backend()

    def mutate(files):
        files["normalized-distributions.json"] = json.dumps(
            [{"ex_date": "2026-10-16", "pay_date": "2026-10-30", "amount": amount}]
        ).encode()
        files["normalized-bars.csv"] = files["normalized-bars.csv"].replace(
            b",0.5\r\n", f",{amount}\r\n".encode()
        )

    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(package(mutate=mutate))
    assert report["qualification"]["structural_status"] == "PASS"
    assert report["qualification"]["status"] == "INSUFFICIENT"
    assert report["corporate_actions"]["conflicts"] == conflicts
    assert next(c for c in report["checks"] if c["code"] == "yahoo_alignment")["status"] == "PASS"


def test_corrupt_csv_dividend_is_reject_against_retained_issuer_json(tmp_path):
    mod = backend()
    report = mod.SnapshotCatalog(tmp_path, clock=lambda: NOW).import_archive(
        package(
            mutate=lambda files: files.update(
                {
                    "normalized-bars.csv": files["normalized-bars.csv"].replace(
                        b",0.5\r\n", b",0.7\r\n"
                    )
                }
            )
        )
    )
    assert report["qualification"]["status"] == "REJECT"
    check = next(c for c in report["checks"] if c["code"] == "issuer_alignment")
    assert check["status"] == "REJECT"
    assert check["locations"][0] == {
        "date": "2026-10-16",
        "row": 3,
        "field": "dividend",
        "expected": "0.5",
        "actual": "0.7",
    }
