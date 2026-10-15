"""Opt-in local fixture experiment. Does not implement the production JobStore."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

_LOADED_ADAPTER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FIXTURE_SHA256 = "b27b6ed461cf58e9e1c3e4a40edb9e718feab6ace52cc29afb38ef6aa8f7dd96"
ENGINE_SHA256 = "934dcb4baefbc1e0e5f8736ee5b841b667c870e66648164101dfaf01fb25b026"
VERSIONS = {"vnpy": "4.5.0", "vnpy_ctastrategy": "1.4.1", "vnpy_sqlite": "1.1.3"}
STRATEGIES = {
    "DoubleMaStrategy": {
        "module": "double_ma_strategy",
        "sha256": "32f058bfaa616f294c62506fbac73c1063b517e86545c8ae412516c902fc258b",
        "parameters": {"fast_window": (10, 2, 80), "slow_window": (20, 3, 90)},
    },
    "AtrRsiStrategy": {
        "module": "atr_rsi_strategy",
        "sha256": "b45b421035eb69c5a571ad746c4b0930f3fea3f54ac981ac1085a6238de0ba46",
        "parameters": {
            "atr_length": (22, 2, 60),
            "atr_ma_length": (10, 2, 30),
            "rsi_length": (5, 2, 50),
            "rsi_entry": (16, 1, 40),
            "trailing_percent": (0.8, 0.01, 10),
            "fixed_size": (1, 1, 10),
        },
    },
}
TERMINAL = {"succeeded", "failed", "cancelled"}
SESSION_CLOSES = dict(
    zip(
        [f"2013-10-{day:02}" for day in range(7, 12)],
        [100.93, 103.57, 100.87, 101.83, 102.67],
        strict=True,
    )
)


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Costs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)
    fee_bps: float = Field(default=5, gt=0, le=100)
    half_spread_price: float = Field(default=0.005, gt=0, le=1)
    slippage_price: float = Field(default=0.005, gt=0, le=1)


class FixtureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    strategy_id: Literal["DoubleMaStrategy", "AtrRsiStrategy"] = "DoubleMaStrategy"
    parameters: dict[str, int | float] = Field(default_factory=dict)
    costs: Costs = Field(default_factory=Costs)

    @model_validator(mode="before")
    @classmethod
    def validate_parameters(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        spec = STRATEGIES.get(value.get("strategy_id", "DoubleMaStrategy"))
        if spec is None:
            raise ValueError("unknown strategy")
        supplied = value.get("parameters", {})
        if not isinstance(supplied, dict) or set(supplied) - set(spec["parameters"]):
            raise ValueError("unknown parameters")
        params = {}
        for key, (default, lower, upper) in spec["parameters"].items():
            item = supplied.get(key, default)
            if type(item) not in (int, float) or not lower <= item <= upper:
                raise ValueError("invalid parameter")
            if isinstance(default, int) and (not isinstance(item, int) or isinstance(item, bool)):
                raise ValueError("integer parameter required")
            params[key] = item
        if value.get("strategy_id", "DoubleMaStrategy") == "DoubleMaStrategy":
            if params["fast_window"] >= params["slow_window"]:
                raise ValueError("fast must be below slow")
        value["parameters"] = params
        return value


def options() -> dict:
    return {
        "schema_version": 1,
        "fixture_sha256": FIXTURE_SHA256,
        "fixture_label": "Synthetic SPY · 1 minute · 2013-10-07–11 · 1950 replay bars",
        "cost_units": {
            "fee_bps": "bps of turnover",
            "half_spread_price": "USD/unit/fill",
            "slippage_price": "USD/unit/fill",
        },
        "engine_versions": VERSIONS,
        "engine_sha256": ENGINE_SHA256,
        "strategies": [
            {
                "strategy_id": name,
                "source_sha256": spec["sha256"],
                "parameters": [
                    {
                        "name": key,
                        "default": values[0],
                        "minimum": values[1],
                        "maximum": values[2],
                        "integer": isinstance(values[0], int),
                    }
                    for key, values in spec["parameters"].items()
                ],
            }
            for name, spec in STRATEGIES.items()
        ],
    }


class FixtureManager:
    """One owned native attempt at a time; active state is explicitly non-durable."""

    def __init__(self, python: Path, fixture: Path, root: Path):
        self.python, self.fixture, self.root = python.resolve(), fixture.resolve(), root.resolve()
        self.runner = Path(__file__).with_name("vnpy_fixture_runner.py")
        self._admit()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._keys: dict[str, str] = {}
        self._threads: list[threading.Thread] = []
        self._inflight: set[str] = set()
        self._closed = False
        self._identity = {
            "fixture_sha256": FIXTURE_SHA256,
            "engine_sha256": ENGINE_SHA256,
            "versions": VERSIONS,
            "strategy_sources": {name: spec["sha256"] for name, spec in STRATEGIES.items()},
            "adapter_sha256": _LOADED_ADAPTER_SHA256,
            "runner_sha256": digest(self.runner),
            "cost_units": options()["cost_units"],
            "capital_usd": 100000,
            "contract_size": 1,
            "tick": 0.01,
            "annual_days": 252,
            "replay_period": ["2013-10-07", "2013-10-11"],
            "exchange_timezone": "America/New_York",
            "fixture_only": True,
        }

    def _admit(self):
        if not self.fixture.is_file() or digest(self.fixture) != FIXTURE_SHA256:
            raise ValueError("fixture integrity failed")
        if os.name != "nt" or sys.platform != "win32" or not self.python.is_file():
            raise ValueError("Windows external runtime required")
        site = self.python.parent.parent / "Lib/site-packages"
        for package, version in VERSIONS.items():
            metadata = site / f"{package}-{version}.dist-info/METADATA"
            if not metadata.is_file() or f"\nVersion: {version}\n" not in metadata.read_text(
                encoding="utf-8"
            ):
                raise ValueError("runtime version drift")
        cta = site / "vnpy_ctastrategy"
        if digest(cta / "backtesting.py") != ENGINE_SHA256:
            raise ValueError("engine source drift")
        for spec in STRATEGIES.values():
            if digest(cta / f"strategies/{spec['module']}.py") != spec["sha256"]:
                raise ValueError("strategy source drift")

    def submit(self, request: FixtureRequest, key: str) -> dict:
        UUID(key)
        # Revalidate even callers that used model_construct or mutated the inner dict.
        request = FixtureRequest.model_validate(request.model_dump())
        body = {"request": request.model_dump(), "identity": self._identity}
        request_digest = hashlib.sha256(canonical(body)).hexdigest()
        with self._lock:
            if key in self._keys:
                existing = self._jobs[self._keys[key]]
                if existing["request_digest"] != request_digest:
                    raise ValueError("idempotency_conflict")
                return self._public(existing)
            if self._closed:
                raise ValueError("service_closed")
            if (
                self._inflight
                or len(self._jobs) >= 32
                or any(j["state"] not in TERMINAL for j in self._jobs.values())
            ):
                raise ValueError("capacity_exceeded")
            self._check_adapter()
            self._admit()
            job_id = str(uuid4())
            job = {
                "schema_version": 1,
                "job_id": job_id,
                "request_digest": request_digest,
                **body,
                "state": "queued",
                "stage": "queued",
                "completed_bars": 0,
                "total_bars": 1950,
                "error_code": None,
                "report_sha256": None,
                "_cancel": threading.Event(),
            }
            self._jobs[job_id] = job
            self._keys[key] = job_id
            self._start(job)
            return self._public(job)

    def _check_adapter(self):
        if (
            digest(Path(__file__)) != self._identity["adapter_sha256"]
            or digest(self.runner) != self._identity["runner_sha256"]
        ):
            raise ValueError("adapter source drift")

    @staticmethod
    def _public(job: dict) -> dict:
        return json.loads(
            canonical({key: value for key, value in job.items() if not key.startswith("_")})
        )

    def _start(self, job):
        thread = threading.Thread(target=self._execute, args=(job,), daemon=True)
        self._inflight.add(job["job_id"])
        try:
            thread.start()
            self._threads.append(thread)
        except RuntimeError:
            self._inflight.discard(job["job_id"])
            job.update(state="failed", stage="failed", error_code="engine_or_report_failed")
            raise ValueError("service_closed") from None

    def _execute(self, job):
        from quantmesh.research.job_runner import _OwnedChild
        from quantmesh.research.jobs import RunBudget

        child = None
        directory = self.root / job["job_id"]
        try:
            directory.mkdir()
            (directory / "input.json").write_bytes(
                canonical(
                    {
                        "request": job["request"],
                        "identity": job["identity"],
                        "request_digest": job["request_digest"],
                        "fixture": str(self.fixture),
                    }
                )
            )
            with self._lock:
                if job["_cancel"].is_set():
                    return
                job.update(state="running", stage="loading_strategy")
            self._admit()
            self._check_adapter()
            command = [str(self.python), "-I", "-B", str(self.runner), str(directory)]
            child = _OwnedChild(
                command,
                RunBudget(timeout_seconds=120, memory_mib=1024, max_model_calls=0),
                directory,
            )
            deadline = monotonic() + 120
            while child.poll() is None:
                if job["_cancel"].is_set():
                    return
                if monotonic() > deadline:
                    raise TimeoutError
                progress = directory / "progress.json"
                if progress.is_file():
                    try:
                        value = json.loads(progress.read_bytes())
                        count = value["completed_bars"]
                        stage = value["stage"]
                        if (
                            type(count) is int
                            and 0 <= count <= 1950
                            and stage
                            in {
                                "loading_strategy",
                                "loading_data",
                                "warmup",
                                "replaying",
                                "reporting",
                            }
                        ):
                            with self._lock:
                                job.update(
                                    stage=stage, completed_bars=max(job["completed_bars"], count)
                                )
                    except (ValueError, KeyError, OSError):
                        pass
                time.sleep(0.05)
            if child.poll() != 0:
                raise ValueError("engine_failed")
            raw = (directory / "result.json").read_bytes()
            if len(raw) > 4_000_000:
                raise ValueError("report_invalid")
            result = json.loads(raw)
            self._validate_report(job, result)
            raw = canonical(result)
            report_sha = hashlib.sha256(raw).hexdigest()
            target = self.root / f"{report_sha}.json"
            if not target.exists():
                with target.open("xb") as stream:
                    stream.write(raw)
            if digest(target) != report_sha:
                raise ValueError("report_invalid")
            with self._lock:
                if not job["_cancel"].is_set():
                    job.update(
                        state="succeeded",
                        stage="complete",
                        completed_bars=1950,
                        report_sha256=report_sha,
                    )
        except Exception as exc:
            with self._lock:
                if not job["_cancel"].is_set():
                    job.update(
                        state="failed",
                        stage="failed",
                        error_code=(
                            "timeout"
                            if isinstance(exc, TimeoutError)
                            else "engine_or_report_failed"
                        ),
                    )
        finally:
            if child is not None:
                child.close()
            with self._lock:
                self._inflight.discard(job["job_id"])

    @staticmethod
    def _validate_report(job, result):
        if (
            result.get("schema_version") != 1
            or result.get("request_digest") != job["request_digest"]
            or result.get("request") != job["request"]
            or result.get("identity") != job["identity"]
            or result.get("lifecycle", {}).get("replay_bars") != 1950
            or result.get("lifecycle", {}).get("warmup_bars") != 2340
            or len(result.get("daily", [])) != 5
            or not isinstance(result.get("trades"), list)
            or not isinstance(result.get("statistics"), dict)
        ):
            raise ValueError("report_invalid")
        canonical(result)  # Refuse NaN/infinity anywhere.
        lifecycle = result["lifecycle"]
        if any(lifecycle.get(key) != 1 for key in ("on_init", "on_start", "on_stop")):
            raise ValueError("report_invalid")

        def finite(value):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("report_invalid")
            return value

        def equal(actual, expected):
            if not math.isclose(finite(actual), expected, abs_tol=1e-6, rel_tol=1e-12):
                raise ValueError("report_invalid")

        cash, position, fees, slippage, turnover = 100000.0, 0.0, 0.0, 0.0, 0.0
        trades = result["trades"]
        costs = job["request"]["costs"]
        index, previous_time, previous_balance = 0, None, 100000.0
        for day, (session, close) in zip(result["daily"], SESSION_CLOSES.items(), strict=True):
            if day.get("date") != session:
                raise ValueError("report_invalid")
            equal(day.get("close_price"), close)
            daily_fees, daily_slippage = 0.0, 0.0
            while index < len(trades):
                trade = trades[index]
                stamp = datetime.fromisoformat(trade["datetime"])
                if stamp.utcoffset() is None:
                    raise ValueError("report_invalid")
                stamp = stamp.astimezone(ZoneInfo("America/New_York"))
                if stamp.date().isoformat() > session:
                    break
                if (
                    stamp.date().isoformat() != session
                    or not ("09:30" <= stamp.strftime("%H:%M") <= "15:59")
                    or (previous_time is not None and stamp < previous_time)
                    or trade.get("direction") not in {"多", "空"}
                ):
                    raise ValueError("report_invalid")
                price, quantity = finite(trade.get("price")), finite(trade.get("volume"))
                if not 0 < price < 1000 or not 0 < quantity <= 10:
                    raise ValueError("report_invalid")
                signed = quantity if trade["direction"] == "多" else -quantity
                fee = price * quantity * costs["fee_bps"] / 10000
                slip = quantity * (costs["half_spread_price"] + costs["slippage_price"])
                cash -= signed * price + fee + slip
                position += signed
                fees += fee
                slippage += slip
                turnover += price * quantity
                daily_fees += fee
                daily_slippage += slip
                previous_time = stamp
                index += 1
            balance = cash + position * close
            equal(day.get("balance"), balance)
            equal(day.get("net_pnl"), balance - previous_balance)
            equal(day.get("commission"), daily_fees)
            equal(day.get("slippage"), daily_slippage)
            equal(day.get("end_pos"), position)
            previous_balance = balance
        if index != len(trades):
            raise ValueError("report_invalid")
        stats = result["statistics"]
        for key, expected in {
            "capital": 100000,
            "end_balance": previous_balance,
            "total_commission": fees,
            "total_slippage": slippage,
            "total_turnover": turnover,
            "total_trade_count": len(trades),
        }.items():
            equal(stats.get(key), expected)

    def get(self, job_id: str) -> dict:
        with self._lock:
            return self._public(self._jobs[job_id])

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs[job_id]
            if job["state"] not in TERMINAL:
                job["_cancel"].set()
                job.update(state="cancelled", stage="cancelled")
            return self._public(job)

    def report(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs[job_id]
            if job["state"] != "succeeded":
                raise ValueError("report_unavailable")
            sha = job["report_sha256"]
            raw = (self.root / f"{sha}.json").read_bytes()
            if hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError("report_invalid")
            self._validate_report(job, json.loads(raw))
            return {
                "schema_version": 1,
                "request_digest": job["request_digest"],
                "sha256": sha,
                "text": raw.decode("utf-8"),
            }

    def close(self):
        with self._lock:
            self._closed = True
            for job in self._jobs.values():
                self.cancel(job["job_id"])
        for thread in self._threads:
            thread.join(timeout=8)
