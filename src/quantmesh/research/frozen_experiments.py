"""Inspect one retained historical experiment; never execute its code or economics."""

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
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.objects import ObjectIntegrityError, ObjectRef, ObjectStore, is_reparse_point
from quantmesh.research.realdata_snapshots import MEMBERS as SNAPSHOT_MEMBERS
from quantmesh.research.realdata_snapshots import SnapshotCatalog

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_ROWS = 10000
EXPERIMENT_ID = "QM-REAL-ETF-001-D-20261018"
CASES = (
    "final-base5bps",
    "final-stress10bps",
    "final-delay1session5bps",
    "final-gross0bps",
    "development2020-base5bps",
    "validation2022-base5bps",
    "validation2023-base5bps",
    "validation2024-base5bps",
)
_CASE_WINDOWS = {
    **{name: ("2025-01-02", "2026-10-16") for name in CASES[:4]},
    "development2020-base5bps": ("2020-01-02", "2020-12-31"),
    "validation2022-base5bps": ("2022-01-03", "2022-12-30"),
    "validation2023-base5bps": ("2023-01-03", "2023-12-29"),
    "validation2024-base5bps": ("2024-01-02", "2024-12-31"),
}
INPUTS = SNAPSHOT_MEMBERS - {"manifest.json"}
CODE = frozenset({"engine.py", "data_io.py", "xlsx_rows.py", "run_experiment.py", "test_engine.py"})
DOWNLOADS = {
    "protocol": "protocol.json",
    "receipt": "freeze-receipt.json",
    "result": "run-1/result.json",
    "report": "report.md",
    "timeline": "local-timeline.json",
    "review": "review.md",
    "verification": "verification.json",
    "manifest": "manifest.json",
}
MEMBERS = (
    INPUTS
    | CODE
    | frozenset(DOWNLOADS.values())
    | {
        "checks-red.log",
        "checks-green.log",
    }
    | {
        f"run-1/{case}-{suffix}"
        for case in CASES
        for suffix in ("strategy.csv", "benchmark.csv", "trades.json")
    }
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_METRICS = frozenset(
    (
        "sessions terminal_equity net_profit_usd total_return cagr max_drawdown "
        "max_underwater_sessions annualized_volatility naive_sharpe_rf_zero sortino_target_zero "
        "calmar worst_day historical_es_95 es_tail_observations fills long_entries friction_usd "
        "dividend_earned_usd dividend_paid_usd terminal_receivable "
        "gross_traded_notional_over_initial_capital capacity_clipped_sessions terminal_shares"
    ).split()
)
_INFERENCE = frozenset(
    (
        "block_sessions resamples seed observations mean_daily_difference one_sided_95_lower_daily "
        "one_sided_95_upper_daily annualized_arithmetic_difference"
    ).split()
)
_MISSING = [
    "PIT availability/revision history",
    "historical executable09:35 NBBO/size and costs",
    "trading/product data entitlement",
    "pristine blind holdout and full prior trial ledger",
    "unresolved2021 dividend source discrepancy",
    "user investment utility/risk budget",
]


class FrozenExperimentInputError(ValueError):
    """Unsupported or inconsistent original evidence, with a fixed public code."""


class FrozenExperimentTooLarge(FrozenExperimentInputError):
    """Fixed import budget exceeded."""


class FrozenSnapshotMissing(FrozenExperimentInputError):
    """Import the separately preserved P1 snapshot first."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _Manifest(_Strict):
    schema_id: Literal["qm.frozen-spy-experiment.v1"]
    experiment_id: Literal["QM-REAL-ETF-001-D-20261018"]
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: dict[str, str]


class _Index(_Strict):
    schema_version: Literal[1]
    package_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    imported_at: str
    archive: ObjectRef
    members: dict[str, ObjectRef]
    receipt: ObjectRef


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json(payload):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = value
        return output

    def invalid(_value):
        raise ValueError("nonfinite")

    result = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid)

    def bounded(value, depth=0):
        if depth > 24:
            raise ValueError("deep JSON")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite")
        if isinstance(value, (list, dict)):
            if len(value) > MAX_ROWS:
                raise ValueError("too many values")
            for item in value.values() if isinstance(value, dict) else value:
                bounded(item, depth + 1)

    bounded(result)
    return result


def _unpack(payload):
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise FrozenExperimentTooLarge("frozen_experiment_too_large")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if len(infos) != 46 or {i.filename for i in infos} != MEMBERS:
            raise ValueError("unexpected members")
        files = {}
        total = 0
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
                raise FrozenExperimentTooLarge("frozen_experiment_too_large")
            with archive.open(info) as stream:
                value = stream.read(min(info.file_size + 1, MAX_EXPANDED_BYTES + 1))
            if len(value) != info.file_size:
                raise ValueError("member length")
            files[info.filename] = value
    manifest = _Manifest.model_validate(_json(files["manifest.json"]))
    if set(manifest.files) != MEMBERS - {"manifest.json"} or any(
        not _DIGEST.fullmatch(digest) or _sha(files[name]) != digest
        for name, digest in manifest.files.items()
    ):
        raise ValueError("member digest")
    # Only parse data. Python, Markdown, spreadsheet and log bytes remain inert.
    for name, payload in files.items():
        if name.endswith(".json"):
            _json(payload)
        elif name.endswith(".csv"):
            reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
            for number, _ in enumerate(reader):
                if number > MAX_ROWS:
                    raise ValueError("too many CSV rows")
    return manifest, files


def _number(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError("numeric or null required")


def _text(value, limit=4096):
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise ValueError("text required")
    return value


def _utc(value):
    moment = datetime.fromisoformat(_text(value, 100))
    if moment.tzinfo is None or moment.utcoffset().total_seconds() != 0:
        raise ValueError("UTC required")
    return value


def _validate(manifest, files, snapshots):
    protocol = _json(files["protocol.json"])
    result = _json(files["run-1/result.json"])
    receipt = _json(files["freeze-receipt.json"])
    if (
        protocol["experiment_id"] != EXPERIMENT_ID
        or result["experiment_id"] != EXPERIMENT_ID
        or result["protocol_sha256"] != _sha(files["protocol.json"])
        or receipt["protocol_sha256"] != _sha(files["protocol.json"])
        or receipt["input_files"] != 7
        or receipt["code_files"] != 5
        or type(receipt["created_before_results"]) is not bool
        or receipt["frozen_at_utc"] != protocol["frozen_at_utc"]
    ):
        raise ValueError("protocol identity")
    _utc(protocol["frozen_at_utc"])
    for key, expected in (("inputs", INPUTS), ("code", CODE)):
        refs = protocol[key]
        if set(refs) != expected or any(refs[name] != _sha(files[name]) for name in expected):
            raise ValueError("protocol reference")
    try:
        source = snapshots.get(manifest.snapshot_id)
        source_archive = snapshots.archive_bytes(manifest.snapshot_id)
    except KeyError as error:
        raise FrozenSnapshotMissing("frozen_experiment_snapshot_required") from error
    with zipfile.ZipFile(io.BytesIO(source_archive)) as archive:
        if any(archive.read(name) != files[name] for name in INPUTS):
            raise ValueError("snapshot inputs differ")
    if source["qualification"]["status"] != "INSUFFICIENT":
        raise ValueError("unsupported source qualification")
    exposure = protocol["exposure_and_trials"]
    if (
        type(exposure["current_empirical_trial"]) is not int
        or exposure["current_empirical_trial"] != 1
        or type(exposure["parameter_variants_searched"]) is not int
        or exposure["parameter_variants_searched"] != 0
        or exposure["source_discovery_exposed_some_2026_SPY_prices"] is not True
        or exposure["pristine_blind_or_prospective_test"] is not False
        or type(exposure["no_strategy_results_evaluated_before_this_freeze"]) is not bool
        or not _text(exposure["historical_external_research_trials"]).startswith("unknown;")
    ):
        raise ValueError("unsafe trial claim")
    costs = protocol["costs"]
    for key, expected in (
        ("single_side_proxy_bps", 5),
        ("stress_bps", 10),
        ("gross_diagnostic_bps", 0),
        ("extra_delay_stress_sessions", 1),
    ):
        if type(costs[key]) not in (float, int) or costs[key] != expected:
            raise ValueError("unsupported cost")
    if costs["actual_nbbo_and_costs_verified"] is not False:
        raise ValueError("unsafe execution claim")
    _text(costs["fee_spread_slippage_breakdown"])
    strategy = protocol["strategy"]
    if (
        strategy["symbol"] != "SPY"
        or type(strategy["lookback"]) is not int
        or strategy["lookback"] != 100
        or strategy["short_allowed"] is not False
        or strategy["leverage"] is not False
    ):
        raise ValueError("unsupported strategy")
    # This case schema preserves one fixed signal and execution assumption.
    # Recomputing its linkage hashes cannot turn another rule into this case.
    if strategy["comparison"] != (
        "causal total-return close > trailing100-session mean, "
        "including current completed close; equal=>cash"
    ) or strategy["execution"] != (
        "next-session raw DAILY OPEN proxy; not original09:35 execution"
    ):
        raise ValueError("unsupported strategy assumptions")
    capital = protocol["accounting"]["capital_usd"]
    if type(capital) not in (float, int) or capital != 100000:
        raise ValueError("unsupported capital")
    window = protocol["splits"]["final"]
    if window != ["2025-01-02", "2026-10-16"]:
        raise ValueError("unsupported final window")
    conflict = protocol["data"]["secondary_source_conflict"]
    if protocol["data"]["license"] != (
        "public research access observed; no redistribution/live entitlement verified"
    ):
        raise ValueError("unsupported source rights claim")
    if (
        conflict["date"] != "2021-12-17"
        or conflict["yahoo_usd"] != 1.633
        or conflict["issuer_usd"] != 1.636431
        or not _text(conflict["resolution"]).startswith("unresolved;")
    ):
        raise ValueError("unsafe conflict claim")
    verdict = result["verdict"]
    if protocol["rules"] != {
        "proxy_economic_pass": (
            "net profit>0 AND main/sensitivity95% lower bounds>0 "
            "AND stress net profit>0 AND no capacity clipping"
        ),
        "proxy_reject": (
            "net profit<=0 OR mean paired daily difference<=0; "
            "if mean>0 but lower bound<=0 => INSUFFICIENT"
        ),
        "formal_R1_R2": (
            "all data/PIT/license/execution/selection gates required; "
            "unresolved hard evidence=>INSUFFICIENT regardless proxy arithmetic"
        ),
        "R3": "NOT_AUTHORIZED; no forward sample, user risk budget or live approval",
    }:
        raise ValueError("inconsistent protocol authority")
    if verdict != {
        "proxy_economic_criterion": "REJECT",
        "formal_research_R1": "INSUFFICIENT",
        "formal_tradeable_candidate_R2": "INSUFFICIENT",
        "R3": "NOT_AUTHORIZED",
        "hard_missing_evidence": _MISSING,
    }:
        raise ValueError("unsafe verdict")
    if set(result) != {"experiment_id", "protocol_sha256", "cases", "verdict"} or set(
        result["cases"]
    ) != set(CASES):
        raise ValueError("unexpected result schema")
    for name, case in result["cases"].items():
        if set(case) != {
            "strategy",
            "benchmark",
            "cash_benchmark_total_return",
            "net_total_return_difference",
            "inference",
        }:
            raise ValueError("unexpected case schema")
        for side in ("strategy", "benchmark"):
            metrics = case[side]
            if set(metrics) != _METRICS | {"start", "end"}:
                raise ValueError("unexpected metrics")
            for key in _METRICS:
                _number(metrics[key])
            for key in ("start", "end"):
                if date.fromisoformat(metrics[key]).isoformat() != metrics[key]:
                    raise ValueError("invalid metric date")
            if (metrics["start"], metrics["end"]) != _CASE_WINDOWS[name]:
                raise ValueError("case window differs from fixed protocol role")
        for key in ("cash_benchmark_total_return", "net_total_return_difference"):
            _number(case[key])
        if not isinstance(case["inference"], list) or len(case["inference"]) > 3:
            raise ValueError("invalid inference")
        for inference in case["inference"]:
            if set(inference) != _INFERENCE | {"method", "not_a_probability_of_skill"}:
                raise ValueError("invalid inference schema")
            _text(inference["method"])
            if inference["not_a_probability_of_skill"] is not True:
                raise ValueError("unsafe confidence claim")
            for key in _INFERENCE:
                _number(inference[key])
    return protocol, result, source


class FrozenExperimentCatalog:
    """Immutable archive/member associations, with verified P1 lineage on every read."""

    def __init__(
        self, root: Path, snapshots: SnapshotCatalog, *, clock: Callable[[], datetime] | None = None
    ):
        self.root = Path(root).absolute()
        self.snapshots = snapshots
        self.objects = ObjectStore(self.root)
        self.clock = clock or (lambda: datetime.now(UTC))

    def _path(self, package_id):
        if not isinstance(package_id, str) or not _DIGEST.fullmatch(package_id):
            raise KeyError("frozen_experiment_unknown")
        path = self.root / "experiments" / f"{package_id}.json"
        for component in (path, *path.parents):
            if is_reparse_point(component):
                raise ObjectIntegrityError("invalid experiment local path")
        return path

    def _parse(self, payload):
        try:
            manifest, files = _unpack(payload)
            protocol, result, source = _validate(manifest, files, self.snapshots)
            return manifest, files, protocol, result, source
        except (FrozenExperimentInputError, ObjectIntegrityError):
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
            AttributeError,
            IndexError,
            OverflowError,
            RecursionError,
            csv.Error,
        ) as error:
            raise FrozenExperimentInputError("frozen_experiment_invalid") from error

    def import_archive(self, payload: bytes):
        manifest, files, _, _, _ = self._parse(payload)
        package_id = _sha(payload)
        path = self._path(package_id)
        if path.exists():
            return self.get(package_id)
        now = self.clock()
        imported_at = _utc(now.isoformat())
        receipt = {
            "schema_version": 1,
            "package_id": package_id,
            "imported_at": imported_at,
            "archive": self.objects.put_bytes("application/zip", payload).model_dump(),
            "members": {
                name: self.objects.put_bytes("application/octet-stream", value).model_dump()
                for name, value in files.items()
            },
        }
        receipt_ref = self.objects.put_bytes(
            "application/json", json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        )
        index = _Index.model_validate({**receipt, "receipt": receipt_ref})
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path(package_id)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(index.model_dump_json().encode())
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass  # Identical concurrent import preserves the first receipt.
        finally:
            os.unlink(temporary)
        return self.get(package_id)

    def _read(self, package_id):
        path = self._path(package_id)
        try:
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 32768:
                raise ObjectIntegrityError("invalid experiment index")
            index = _Index.model_validate(_json(path.read_bytes()))
            if (
                index.package_id != package_id
                or index.archive.digest != package_id
                or set(index.members) != MEMBERS
            ):
                raise ObjectIntegrityError("experiment identity mismatch")
            _utc(index.imported_at)
            if _json(self.objects.get_bytes(index.receipt)) != index.model_dump(
                exclude={"receipt"}
            ):
                raise ObjectIntegrityError("experiment receipt mismatch")
            payload = self.objects.get_bytes(index.archive)
            parsed = self._parse(payload)
            files = parsed[1]
            for name, ref in index.members.items():
                if self.objects.get_bytes(ref) != files[name]:
                    raise ObjectIntegrityError("experiment member mismatch")
            return index, payload, parsed
        except FileNotFoundError as error:
            raise KeyError("frozen_experiment_unknown") from error
        except (ObjectIntegrityError, FrozenSnapshotMissing):
            raise
        except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
            raise ObjectIntegrityError("experiment stored associations invalid") from error

    def get(self, package_id):
        index, _, (manifest, files, protocol, result, source) = self._read(package_id)
        return {
            "schema_version": 1,
            "package_id": package_id,
            "experiment_id": EXPERIMENT_ID,
            "snapshot_id": manifest.snapshot_id,
            "imported_at": index.imported_at,
            "verification": {
                "identities": "VERIFIED",
                "economics": "IMPORTED_NOT_RECOMPUTED",
                "chronology": "UNVERIFIED",
            },
            "proxy_verdict": "REJECT",
            "formal_verdict": {"R1": "INSUFFICIENT", "R2": "INSUFFICIENT", "R3": "NOT_AUTHORIZED"},
            "oos": {"state": "CONSUMED", "pristine_blind": False},
            "trials": {"current": 1, "searched": 0, "prior": None, "source_exposure": True},
            "protocol": {
                "sha256": _sha(files["protocol.json"]),
                "frozen_at_claimed": protocol["frozen_at_utc"],
                "created_before_results_claimed": _json(files["freeze-receipt.json"])[
                    "created_before_results"
                ],
                "symbol": "SPY",
                "lookback": 100,
                "comparison": protocol["strategy"]["comparison"],
                "execution": protocol["strategy"]["execution"],
                "final_window": protocol["splits"]["final"],
                "capital_usd": protocol["accounting"]["capital_usd"],
                "costs": protocol["costs"],
            },
            "data": {
                "qualification": "INSUFFICIENT",
                "evidence_kind": source["evidence_kind"],
                "rights": "UNVERIFIED",
                "pit": "UNVERIFIED",
                "execution": "UNVERIFIED",
                "dividend_conflict": protocol["data"]["secondary_source_conflict"],
            },
            "missing_evidence": result["verdict"]["hard_missing_evidence"],
            "cases": [
                {"case_id": name, "primary": name == CASES[0], **result["cases"][name]}
                for name in CASES
            ],
            "lineage": [
                {"path": name, "sha256": ref.digest, "bytes": ref.byte_length}
                for name, ref in sorted(index.members.items())
            ],
            "downloads": [
                {
                    "kind": "archive",
                    "sha256": index.archive.digest,
                    "bytes": index.archive.byte_length,
                },
                *[
                    {
                        "kind": kind,
                        "sha256": index.members[name].digest,
                        "bytes": index.members[name].byte_length,
                    }
                    for kind, name in DOWNLOADS.items()
                ],
            ],
        }

    def list(self):
        self._path("0" * 64)
        directory = self.root / "experiments"
        if not directory.exists():
            return []
        return [self.get(path.stem) for path in sorted(directory.glob("*.json"))]

    def artifact_bytes(self, package_id, kind):
        if kind != "archive" and kind not in DOWNLOADS:
            raise KeyError("frozen_experiment_unknown")
        _, payload, (_, files, _, _, _) = self._read(package_id)
        return payload if kind == "archive" else files[DOWNLOADS[kind]]
