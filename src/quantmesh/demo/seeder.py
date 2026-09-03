"""The deterministic demo seeder (iteration 0014 Phase B).

``seed_demo_root`` writes one complete, labeled demo scenario into an
operator-chosen root: fixture files the real venue providers parse,
lake datasets the research registries pin against, JSONL ledgers every
domain service appends through its public API, and the paper account
replayed through real submits. Everything derives from the scenario's
fixed RNG seed and anchor — never the wall clock — so seeding the same
scenario twice produces byte-identical roots (the replay guarantee),
and every record carries the ``demo`` provenance label.

Isolation is enforced at the filesystem: a demo root must carry the
marker file written at seed time, and reset refuses to touch a root
that does not (the never-touches-non-demo-root guarantee). The seeder
never opens the operator's lake, orders, reports or any other
non-demo directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from quantmesh._fs import FilesystemIdentity, atomic_replace, filesystem_identity
from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.retrieval import Citation, DocumentIndex
from quantmesh.api.watchlist import WatchlistStore
from quantmesh.data.lake import Lake
from quantmesh.data.layout import SHARD_NAME, shards_in, validate_symbol
from quantmesh.data.manifest import (
    MANIFEST_NAME,
    DatasetClass,
    DatasetManifest,
    ManifestWriter,
)
from quantmesh.data.providers.hyperliquid import HyperliquidFixtureProvider
from quantmesh.data.providers.moomoo import MoomooFixtureProvider
from quantmesh.demo import generators
from quantmesh.demo.manifest import MARKER_NAME, DemoScenario
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
from quantmesh.domain.models import (
    Instrument,
    InstrumentType,
    OrderRequest,
    Quote,
    Side,
    Venue,
)
from quantmesh.events.forecast import (
    ForecastMarket,
    ForecastObservation,
    ForecastReport,
    ForecastReportRegistry,
    ForecastWindowSpec,
    _write_artifacts,
    forecast_report_id,
    run_forecast,
)
from quantmesh.events.mapping import (
    EventMappingReport,
    EventPairing,
    EvidenceKind,
    MappingEvidence,
    MappingLedger,
    MappingStatus,
    pair_key,
)
from quantmesh.events.models import EventMarket, EventVenue, Outcome, ResolutionRule
from quantmesh.execution.accounting import FeeModel, PaperAccount, PaperMatcher
from quantmesh.execution.journal import OrderJournal
from quantmesh.instruments.contracts import (
    CoverageSnapshot,
    DatasetBinding,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
)
from quantmesh.instruments.copilot import PacketCopilotStore
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.instruments.forecast import PriceForecastRegistry, run_price_forecast
from quantmesh.instruments.history import HistoryService
from quantmesh.instruments.monitoring import DecisionWatchStore
from quantmesh.instruments.proposals import ProposalLedger
from quantmesh.ops.enablement import ApprovalLedger
from quantmesh.research.drift import (
    AlertLedger,
    AlertRecord,
    PromotionEvidence,
    PromotionLedger,
    alert_id,
    promote_signal,
)
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.research.reports import (
    CostModel,
    ReportRegistry,
    StrategyReport,
    UniverseMember,
    WalkForwardSpec,
    WindowResult,
    report_id,
)
from quantmesh.runtime import build_workstation_stores

# The seeded commit every demo record pins: a fixed, deterministic
# identity instead of the working tree's git HEAD (which would make
# replay depend on checkout state). Hex-shaped to satisfy the
# registries' commit validators.
DEMO_COMMIT = "0a1e2d3c4b5a69788796a5b4c3d2e1f0deadbeef"
OWNERSHIP_NAME = "QUANTMESH_DEMO_OWNERSHIP.json"
RESET_LOCK_SUFFIX = ".quantmesh-demo-reset.lock"

# These seeded files are legitimately rewritten by public demo APIs. Their
# path and regular-file type remain ownership evidence, but their bytes cannot
# be pinned. All other seeded files are hash-pinned in the ownership manifest.
_MUTABLE_FILES = frozenset(
    {
        "account.json",
        "enablement/enablement.jsonl",
        "orders/journal.jsonl",
        "orders/proposals/.proposals.lock",
        "orders/proposals/proposals.jsonl",
        "decisions/copilot/packet-copilot-records.jsonl",
        "decisions/decisions.jsonl",
        "decisions/packets/.decision-packets.lock",
        "decisions/packets/decision-action-intents.jsonl",
        "decisions/packets/decision-packets.jsonl",
        "decisions/monitoring/.decision-watch.lock",
        "decisions/monitoring/watch-registrations.jsonl",
        "decisions/monitoring/watch-evaluations.jsonl",
        "watchlists/watchlist.jsonl",
    }
)

# One deterministic paper-order sequence: fills across venues plus one
# resting limit below the market (the "working order" state). Quantities
# keep the buys inside the $100k starting cash at seeded prices.
ORDER_SEQUENCE: tuple[tuple[str, str, Side, float, float | None], ...] = (
    ("moomoo", "AAPL", Side.BUY, 10, None),
    ("moomoo", "MSFT", Side.BUY, 5, None),
    ("hyperliquid", "BTC-USD", Side.BUY, 0.5, None),
    ("moomoo", "AAPL", Side.SELL, 4, None),
    ("moomoo", "NVDA", Side.BUY, 3, None),
    ("hyperliquid", "BTC-USD", Side.SELL, 0.2, None),
    ("hyperliquid", "ETH-USD", Side.BUY, 5, None),
    ("hyperliquid", "SOL-USD", Side.BUY, 10, 0.9),  # limit below touch: resting
)

_DOCUMENT_TEXT = {
    "filing": (
        "10-K filing (demo): the seeded universe's fundamentals are synthetic; "
        "no real company data is implied. Symbols: {}."
    ),
    "news": (
        "Market news (demo, synthetic): the crypto cluster factor moved with "
        "the shared shock; cross-market correlation is a seeded relationship."
    ),
    "note": (
        "Research note (demo): the deterministic scenario pins this document's "
        "content; provenance is labeled demo, never mistaken for real data."
    ),
}


class DemoRootError(ValueError):
    """A demo root is missing its marker, or refuses a requested op."""

    def __init__(self, message: str, *, retained_paths: tuple[Path, ...] = ()) -> None:
        super().__init__(message)
        self.retained_paths = retained_paths


class DemoProviders:
    """One real fixture provider per seeded symbol.

    The fixture adapters are symbol-scoped by design (one fixture file
    set per symbol), so the demo assembles one provider per symbol
    over its own fixture directory and serves the universe through the
    real provider pipeline — fetch_bars/order_books/trades with the
    same fail-closed guarantees as any venue. A request outside the
    seeded universe fails closed.
    """

    def __init__(
        self,
        providers: dict[tuple[str, str], MoomooFixtureProvider | HyperliquidFixtureProvider],
        kinds: dict[tuple[str, str], str],
    ) -> None:
        self._by_key = dict(providers)
        self._kinds = dict(kinds)

    def _provider(
        self, venue: str, symbol: str
    ) -> MoomooFixtureProvider | HyperliquidFixtureProvider:
        try:
            return self._by_key[(venue, symbol)]
        except KeyError as error:
            raise ValueError(
                f"no demo provider for {venue}:{symbol} — outside the seeded universe"
            ) from error

    def _instrument(self, venue: str, symbol: str) -> Instrument:
        return _instrument(symbol, venue, self._kinds[(venue, symbol)])

    def instrument(self, venue: str, symbol: str) -> Instrument:
        """The canonical instrument for one seeded (venue, symbol)."""
        return self._instrument(venue, symbol)

    def series(self, venue: str, symbol: str, *, interval: str = "1d") -> list[Bar]:
        """The seeded bar series, through the real adapter."""
        return self._provider(venue, symbol).fetch_bars(
            self._instrument(venue, symbol), interval=interval
        )

    def order_books(self, venue: str, symbol: str) -> list[OrderBook]:
        return self._provider(venue, symbol).fetch_order_books(self._instrument(venue, symbol))

    def trades(self, venue: str, symbol: str) -> list[TradeEvent]:
        return self._provider(venue, symbol).fetch_trades(self._instrument(venue, symbol))

    def universe(self) -> set[tuple[str, str]]:
        """Every (venue, symbol) the demo serves."""
        return set(self._by_key)


@dataclass(frozen=True)
class DemoSeeded:
    """Everything a workstation app needs, built from one demo root.

    All objects are bound to files under ``root``; ``account`` is the
    replayed paper account, ``marks`` the position-keyed mark map, and
    ``markets`` the venue -> symbol -> mark board the UI renders.
    """

    root: Path
    scenario: DemoScenario
    account: PaperAccount
    marks: dict[str, float]
    markets: dict[str, dict[str, float]]
    watchlist: WatchlistStore
    experiments: ExperimentRegistry
    promotions: PromotionLedger
    reports: ReportRegistry
    forecasts: ForecastReportRegistry
    alerts: AlertLedger
    journal: OrderJournal
    mappings: MappingLedger
    decisions: DecisionLog
    documents: DocumentIndex
    enablement: ApprovalLedger
    providers: DemoProviders
    history: HistoryService
    price_forecasts: PriceForecastRegistry
    proposal_ledger: ProposalLedger
    decision_packets: DecisionPacketStore
    packet_copilot: PacketCopilotStore
    packet_monitoring: DecisionWatchStore
    provenance: dict[str, object] = field(default_factory=dict)


def _marker(root: Path) -> Path:
    return root / MARKER_NAME


def _legacy_marker_text() -> str:
    return (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "format": "quantmesh-demo-root",
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _claim_marker_text() -> str:
    return (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "format": "quantmesh-demo-root",
                "state": "seeding",
                "version": 2,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _marker_text(ownership_sha256: str) -> str:
    return (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "format": "quantmesh-demo-root",
                "ownership_sha256": ownership_sha256,
                "version": 2,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return True
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_point)


def _walk_owned_tree(root: Path) -> dict[str, str] | None:
    """Walk without following links/reparse points; return relative path types."""
    found: dict[str, str] = {}
    stack = [root]
    try:
        while stack:
            directory = stack.pop()
            for path in sorted(directory.iterdir(), key=lambda item: item.name):
                relative = path.relative_to(root).as_posix()
                if relative in {MARKER_NAME, OWNERSHIP_NAME}:
                    continue
                if _is_link_or_junction(path):
                    return None
                if path.is_dir():
                    found[relative] = "directory"
                    stack.append(path)
                elif path.is_file():
                    found[relative] = "file"
                else:
                    return None
    except OSError:
        return None
    return found


def _ownership_text(root: Path) -> str:
    paths = _walk_owned_tree(root)
    if paths is None:
        raise DemoRootError(f"cannot inventory unsafe demo root {root}")
    entries: list[dict[str, str]] = []
    for relative, kind in sorted(paths.items()):
        entry = {"path": relative, "type": kind}
        if kind == "file" and relative not in _MUTABLE_FILES:
            entry["sha256"] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        entries.append(entry)
    return (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "entries": entries,
                "format": "quantmesh-demo-ownership",
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def build_demo_reset_archive(root: Path) -> bytes:
    """Capture a validated pristine demo tree as an in-memory reset image."""
    root = Path(root)
    paths = _walk_owned_tree(root)
    if paths is None or not is_demo_root(root):
        raise DemoRootError(f"cannot capture unsafe demo reset image from {root}")
    members = {
        MARKER_NAME: "file",
        OWNERSHIP_NAME: "file",
        **paths,
    }
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for relative, kind in sorted(members.items()):
            name = f"{relative}/" if kind == "directory" else relative
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 0
            archive.writestr(info, b"" if kind == "directory" else (root / relative).read_bytes())
    return payload.getvalue()


def build_trusted_demo_reset_image(scenario: DemoScenario) -> tuple[str, bytes]:
    """Independently generate the pristine ownership truth and reset image."""
    with tempfile.TemporaryDirectory(prefix="quantmesh-demo-reset-image-") as temp_dir:
        trusted_root = Path(temp_dir) / "demo"
        seed_demo_root(trusted_root, scenario)
        ownership_text = (trusted_root / OWNERSHIP_NAME).read_text(encoding="utf-8")
        return ownership_text, build_demo_reset_archive(trusted_root)


def _restore_demo_reset_archive(payload: bytes, root: Path) -> None:
    """Restore only the safe relative members emitted by our archive builder."""
    root = Path(root)
    if root.exists():
        raise DemoRootError(f"reset replacement {root} already exists")
    root.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename.rstrip("/") for info in infos]
            if len(names) != len(set(names)):
                raise DemoRootError("trusted demo reset image has duplicate members")
            for info, relative in zip(infos, names, strict=True):
                parts = Path(relative).parts
                if not relative or Path(relative).is_absolute() or ".." in parts:
                    raise DemoRootError("trusted demo reset image has an unsafe member")
                target = root.joinpath(*parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as handle:
                        handle.write(archive.read(info))
    except BaseException as error:
        retained = f"; partial tree retained at {root}" if root.exists() else ""
        raise DemoRootError(f"failed to restore trusted demo reset image{retained}") from error


def _operator_import_inventory(root: Path, dataset: str) -> dict[str, str] | None:
    lake_root = root / "market" / "lake"
    manifest_path = root / "market" / "lake" / dataset / MANIFEST_NAME
    if not manifest_path.is_file() or _is_link_or_junction(manifest_path):
        return None
    try:
        manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.dataset != dataset or manifest.source != "operator-import":
            return None
        Lake(lake_root).dataset(dataset)
    except (OSError, UnicodeDecodeError, ValueError):
        return None

    base = lake_root / dataset
    expected: dict[str, str] = {
        base.relative_to(root).as_posix(): "directory",
        manifest_path.relative_to(root).as_posix(): "file",
    }
    for coverage in manifest.coverage:
        interval = base / coverage.interval
        venue = interval / coverage.venue.value
        symbol = venue / coverage.symbol
        expected[interval.relative_to(root).as_posix()] = "directory"
        expected[venue.relative_to(root).as_posix()] = "directory"
        expected[symbol.relative_to(root).as_posix()] = "directory"
        try:
            shards = shards_in(symbol)
        except (OSError, ValueError):
            return None
        if not shards:
            return None
        for shard in shards:
            if shard.name != SHARD_NAME or _is_link_or_junction(shard):
                return None
            expected[shard.parent.relative_to(root).as_posix()] = "directory"
            expected[shard.relative_to(root).as_posix()] = "file"
    return expected


def _is_valid_datalink_cache(root: Path, relative: str) -> bool:
    path = root / relative
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if (
        not isinstance(record, dict)
        or set(record) != {"symbol", "coin", "source", "synthetic", "fetched_at", "payload"}
        or not isinstance(record["symbol"], str)
        or not isinstance(record["coin"], str)
        or not isinstance(record["fetched_at"], str)
    ):
        return False
    try:
        fetched_at = datetime.fromisoformat(record["fetched_at"])
        validate_symbol(path.stem)
        validate_symbol(record["symbol"])
    except ValueError:
        return False
    return (
        record["coin"] == path.stem
        and record["coin"]
        == (
            record["symbol"][: -len("-USD")]
            if record["symbol"].endswith("-USD")
            else record["symbol"]
        )
        and record["source"] == "hyperliquid-public"
        and record["synthetic"] is False
        and fetched_at.tzinfo is not None
        and isinstance(record["payload"], dict)
    )


def _valid_dynamic_paths(
    root: Path,
    paths: dict[str, str],
    unknown: set[str],
) -> bool:
    remaining = set(unknown)
    cache_paths = {relative for relative in remaining if Path(relative).parts[:1] == (".datalink",)}
    if cache_paths:
        for relative in cache_paths:
            parts = Path(relative).parts
            if parts == (".datalink",) and paths[relative] == "directory":
                continue
            if parts == (".datalink", "hyperliquid") and paths[relative] == "directory":
                continue
            if (
                len(parts) == 3
                and parts[:2] == (".datalink", "hyperliquid")
                and paths[relative] == "file"
                and parts[2].endswith(".json")
                and _is_valid_datalink_cache(root, relative)
            ):
                continue
            return False
        remaining -= cache_paths

    datasets = {
        Path(relative).parts[2]
        for relative in remaining
        if len(Path(relative).parts) >= 3 and Path(relative).parts[:2] == ("market", "lake")
    }
    for dataset in datasets:
        prefix = ("market", "lake", dataset)
        members = {relative for relative in remaining if Path(relative).parts[:3] == prefix}
        expected = _operator_import_inventory(root, dataset)
        if expected is None or members != set(expected):
            return False
        if any(paths.get(relative) != kind for relative, kind in expected.items()):
            return False
        remaining -= members

    return not remaining


def _valid_ownership_structure(
    root: Path,
    ownership_text: str,
    trusted_ownership_text: str,
) -> bool:
    if ownership_text != trusted_ownership_text:
        return False
    try:
        ownership = json.loads(ownership_text)
    except json.JSONDecodeError:
        return False
    if (
        ownership.get("format") != "quantmesh-demo-ownership"
        or ownership.get("version") != 1
        or ownership.get("commit") != DEMO_COMMIT
        or not isinstance(ownership.get("entries"), list)
    ):
        return False
    expected: dict[str, dict[str, str]] = {}
    for raw in ownership["entries"]:
        if not isinstance(raw, dict):
            return False
        relative = raw.get("path")
        kind = raw.get("type")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or kind not in {"file", "directory"}
            or relative in expected
        ):
            return False
        expected_keys = {"path", "type"}
        if kind == "file" and relative not in _MUTABLE_FILES:
            expected_keys.add("sha256")
        if set(raw) != expected_keys:
            return False
        expected_hash = raw.get("sha256")
        if expected_hash is not None and (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_hash)
        ):
            return False
        expected[relative] = raw
    actual = _walk_owned_tree(root)
    if actual is None:
        return False
    for relative, entry in expected.items():
        if actual.get(relative) != entry["type"]:
            return False
        expected_hash = entry.get("sha256")
        if expected_hash is not None:
            try:
                actual_hash = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            except OSError:
                return False
            if actual_hash != expected_hash:
                return False
    unknown = set(actual) - set(expected)
    return _valid_dynamic_paths(root, actual, unknown)


def is_demo_root(root: Path) -> bool:
    """Validate the versioned ownership record against seeded provenance."""
    root = Path(root)
    marker = _marker(root)
    provenance_path = root / "provenance.json"
    if (
        not root.is_dir()
        or _is_link_or_junction(root)
        or not marker.is_file()
        or _is_link_or_junction(marker)
        or not provenance_path.is_file()
        or _is_link_or_junction(provenance_path)
    ):
        return False
    try:
        marker_text = marker.read_text(encoding="utf-8")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    scenario = provenance.get("scenario")
    surfaces = provenance.get("surfaces")
    provenance_valid = (
        isinstance(scenario, dict)
        and scenario.get("commit") == DEMO_COMMIT
        and isinstance(surfaces, dict)
        and bool(surfaces)
    )
    if not provenance_valid:
        return False
    if marker_text == _legacy_marker_text():
        return True
    ownership_path = root / OWNERSHIP_NAME
    if not ownership_path.is_file() or _is_link_or_junction(ownership_path):
        return False
    try:
        marker_record = json.loads(marker_text)
        ownership_text = ownership_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    ownership_sha256 = hashlib.sha256(ownership_text.encode("utf-8")).hexdigest()
    return (
        marker_text == _marker_text(ownership_sha256)
        and marker_record.get("ownership_sha256") == ownership_sha256
    )


def _trusted_ownership_text(scenario: DemoScenario) -> str:
    with tempfile.TemporaryDirectory(prefix="quantmesh-demo-reset-trust-") as temp_dir:
        trusted_root = Path(temp_dir) / "demo"
        seed_demo_root(trusted_root, scenario)
        return (trusted_root / OWNERSHIP_NAME).read_text(encoding="utf-8")


def _has_reset_structure(
    root: Path,
    scenario: DemoScenario,
    *,
    trusted_ownership_text: str | None = None,
) -> bool:
    ownership_path = root / OWNERSHIP_NAME
    if not is_demo_root(root) or not ownership_path.is_file():
        return False
    try:
        ownership_text = ownership_path.read_text(encoding="utf-8")
        trusted_ownership_text = (
            trusted_ownership_text
            if trusted_ownership_text is not None
            else _trusted_ownership_text(scenario)
        )
    except (DemoRootError, OSError, UnicodeDecodeError):
        return False
    return _valid_ownership_structure(root, ownership_text, trusted_ownership_text)


@contextmanager
def _interprocess_reset_lock(root: Path) -> Iterator[None]:
    """Serialize reset callers using a stable lock outside the replaced root."""
    lock_path = root.parent / f".{root.name}{RESET_LOCK_SUFFIX}"
    if lock_path.exists() and (not lock_path.is_file() or _is_link_or_junction(lock_path)):
        raise DemoRootError(f"refusing unsafe demo reset lock {lock_path}")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _unused_reset_quarantine(root: Path) -> Path:
    """Reserve no path; merely choose a collision-resistant sibling name."""
    descriptor, name = tempfile.mkstemp(
        dir=root.parent,
        prefix=f".{root.name}.reset-quarantine-",
    )
    os.close(descriptor)
    os.unlink(name)
    return Path(name)


def retained_demo_reset_paths(root: Path) -> tuple[Path, ...]:
    """List retained reset siblings without claiming ownership or deleting them."""
    root = Path(root)
    prefix = f".{root.name}.reset-quarantine-"
    try:
        candidates = tuple(root.parent.iterdir())
    except OSError:
        return ()
    return tuple(sorted((path for path in candidates if path.name.startswith(prefix)), key=str))


def _require_demo_tree_identity(
    root: Path,
    scenario: DemoScenario,
    *,
    trusted_ownership_text: str,
    expected_identity: FilesystemIdentity | None = None,
    failure_message: str,
) -> FilesystemIdentity:
    """Bind trusted ownership validation to one filesystem object."""
    try:
        identity_before = filesystem_identity(root)
    except OSError as error:
        raise DemoRootError(
            f"{failure_message}: identity unavailable; preserving {root}"
        ) from error
    if expected_identity is not None and identity_before != expected_identity:
        raise DemoRootError(f"{failure_message}: identity changed; preserving {root}")
    if not _has_reset_structure(
        root,
        scenario,
        trusted_ownership_text=trusted_ownership_text,
    ):
        raise DemoRootError(
            f"{failure_message}: trusted ownership/structure validation failed; preserving {root}"
        )
    try:
        identity_after = filesystem_identity(root)
    except OSError as error:
        raise DemoRootError(
            f"{failure_message}: identity unavailable; preserving {root}"
        ) from error
    if identity_after != identity_before or (
        expected_identity is not None and identity_after != expected_identity
    ):
        raise DemoRootError(f"{failure_message}: identity changed; preserving {root}")
    return identity_after


def _restore_original_after_publish_mismatch(
    root: Path,
    quarantine: Path,
    scenario: DemoScenario,
    *,
    trusted_ownership_text: str,
    root_identity: FilesystemIdentity,
    published_identity: FilesystemIdentity | None,
) -> tuple[Path, ...]:
    """Retain an unexpected public object and restore the original demo.

    No path is recursively deleted. The unexpected occupant is moved to a new
    sibling and its observed identity is checked after the move before the
    identity-bound original quarantine is restored.
    """
    unexpected = _unused_reset_quarantine(root)
    retained = (unexpected,)
    try:
        atomic_replace(root, unexpected)
        if published_identity is None or filesystem_identity(unexpected) != published_identity:
            raise DemoRootError(
                "unexpected published object changed while it was quarantined",
                retained_paths=retained,
            )
        _require_demo_tree_identity(
            quarantine,
            scenario,
            trusted_ownership_text=trusted_ownership_text,
            expected_identity=root_identity,
            failure_message="original demo rollback quarantine failed identity validation",
        )
        if root.exists():
            raise DemoRootError(
                f"refusing to overwrite a new public-path occupant at {root}",
                retained_paths=retained,
            )
        atomic_replace(quarantine, root)
        _require_demo_tree_identity(
            root,
            scenario,
            trusted_ownership_text=trusted_ownership_text,
            expected_identity=root_identity,
            failure_message="restored demo failed identity validation",
        )
    except DemoRootError:
        raise
    except (OSError, ValueError) as error:
        raise DemoRootError(
            f"failed to restore original demo after publish mismatch; preserving {retained}",
            retained_paths=retained,
        ) from error
    return retained


def _write_account(root: Path, account: PaperAccount) -> None:
    descriptor, temp_name = tempfile.mkstemp(dir=root, prefix=".account.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(account.model_dump_json())
        atomic_replace(temp_name, root / "account.json")
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def persist_demo_account(root: Path, account: PaperAccount) -> None:
    """Atomically persist the mutable demo account under its owned root."""
    if not is_demo_root(root):
        raise DemoRootError(f"refusing to persist account outside a marked demo root: {root}")
    _write_account(root, account)


def _venue(name: str) -> Venue:
    return Venue(name)


def _instrument_type(kind: str) -> InstrumentType:
    if kind == "equity":
        return InstrumentType.EQUITY
    if kind == "crypto_perp":
        return InstrumentType.PERPETUAL
    if kind == "crypto_spot":
        return InstrumentType.SPOT
    return InstrumentType.EVENT_CONTRACT


def _instrument(symbol: str, venue: str, kind: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        venue=_venue(venue),
        instrument_type=_instrument_type(kind),
    )


def _provenance_rows(surfaces: dict[str, object], updated_at: datetime) -> dict[str, object]:
    """Every surface gets the uniform provenance shape."""
    labeled: dict[str, object] = {}
    for name, rows in surfaces.items():
        labeled[name] = {
            "source": "demo",
            "synthetic": True,
            "updated_at": updated_at.isoformat(),
            "rows": rows,
        }
    return labeled


def _seed_market_data(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    series: dict[str, dict[str, list[float]]],
) -> tuple[dict[str, int], DemoProviders, Path]:
    """Per-symbol fixture files the real venue providers parse, plus the
    demo lake the research registries pin against.

    One fixture directory per symbol (``market/fixtures/<venue>/<symbol>/``)
    holding the exact wire file names the adapters load; one real
    provider per symbol serves it. The provenance keys name the symbol
    and file, e.g. ``market:moomoo:AAPL:moomoo_bars.json``. ``series``
    is the single walk the caller's marks derive from — the fixture
    closes must be the same walk (see ``generators.fixture_files``).
    """
    fixture_root = root / "market" / "fixtures"
    files = generators.fixture_files(draw, scenario, series=series)
    rows: dict[str, int] = {}
    providers: dict[tuple[str, str], MoomooFixtureProvider | HyperliquidFixtureProvider] = {}
    for (venue, symbol), symbol_files in files.items():
        symbol_dir = fixture_root / venue / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        for name, file_rows in symbol_files.items():
            (symbol_dir / name).write_text(json.dumps(file_rows, indent=1), encoding="utf-8")
            rows[f"market:{venue}:{symbol}:{name}"] = len(file_rows)
        provider: MoomooFixtureProvider | HyperliquidFixtureProvider = (
            MoomooFixtureProvider(fixture_dir=symbol_dir)
            if venue == "moomoo"
            else HyperliquidFixtureProvider(fixture_dir=symbol_dir)
        )
        providers[(venue, symbol)] = provider
    kinds = {
        (spec.venue, spec.symbol): spec.kind for spec in (*scenario.equities, *scenario.crypto)
    }
    return rows, DemoProviders(providers, kinds), fixture_root


def _seed_lake(
    scenario: DemoScenario, series: dict[str, dict[str, list[float]]], root: Path
) -> tuple[Path, dict[str, int], tuple[DatasetBinding, ...]]:
    """One dataset per symbol: real shards + a manifest whose ``source``
    label is ``demo-synthetic`` (the lake's own provenance field)."""
    lake_root = root / "market" / "lake"
    lake = Lake(lake_root)
    fixture_times = generators.session_times(scenario)
    # One deterministic manifest stamp for the whole bulk seed: after the
    # last seeded session, before the paper replay (the timeline the UI
    # renders reads oldest-first across surfaces).
    generated_at = scenario.anchor - timedelta(minutes=5)
    datasets: dict[str, int] = {}
    bindings: list[DatasetBinding] = []
    for spec in (*scenario.equities, *scenario.crypto):
        closes = series[spec.venue][spec.symbol]
        rows_by_interval: dict[str, list[dict[str, object]]]
        if scenario.workspace_history and spec.kind == "equity" and spec.symbol in {"AAPL", "NVDA"}:
            rows_by_interval = generators.analytical_history(
                scenario,
                spec,
                target_close=closes[-1],
            )
            if spec.symbol == "AAPL":
                rows_by_interval = {"1d": rows_by_interval["1d"][-420:]}
        else:
            rows_by_interval = {
                "1d": [
                    {
                        "timestamp": time,
                        "interval": "1d",
                        "open": closes[index] * 0.998,
                        "high": closes[index] * 1.004,
                        "low": closes[index] * 0.996,
                        "close": closes[index],
                        "volume": 1_000_000.0,
                    }
                    for index, time in enumerate(fixture_times)
                ]
            }
        dataset = f"demo-{spec.venue}-{spec.symbol.lower()}"
        total = 0
        for interval, rows in rows_by_interval.items():
            bars = [
                Bar(
                    instrument=_instrument(spec.symbol, spec.venue, spec.kind),
                    timestamp=row["timestamp"],
                    interval=interval,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                for row in rows
            ]
            lake.write_bars(dataset, bars)
            total += len(bars)
            bindings.append(
                DatasetBinding(
                    dataset_id=dataset,
                    interval=interval,
                    venue=_venue(spec.venue),
                    symbol=spec.symbol,
                    calendar="XNYS" if spec.kind == "equity" else "24/7",
                    adjustment="unadjusted",
                )
            )
        ManifestWriter(lake_root).generate(
            dataset,
            source="demo-synthetic",
            license="QuantMesh deterministic demo",
            data_class=DatasetClass.SYNTHETIC,
            generated_at=generated_at,
        )
        datasets[dataset] = total
    return lake_root, datasets, tuple(bindings)


def _history_service(
    lake_root: Path,
    bindings: tuple[DatasetBinding, ...],
    *,
    scenario: DemoScenario,
) -> HistoryService:
    lake = Lake(lake_root)
    return HistoryService(
        bindings,
        dataset_loader=lake.dataset,
        now=lambda: scenario.anchor,
    )


def _history_bindings_from_lake(
    lake_root: Path,
    scenario: DemoScenario,
) -> tuple[DatasetBinding, ...]:
    lake = Lake(lake_root)
    bindings: list[DatasetBinding] = []
    for spec in (*scenario.equities, *scenario.crypto):
        dataset_id = f"demo-{spec.venue}-{spec.symbol.lower()}"
        dataset = lake.dataset(dataset_id)
        for coverage in dataset.manifest.coverage:
            bindings.append(
                DatasetBinding(
                    dataset_id=dataset_id,
                    interval=coverage.interval,
                    venue=coverage.venue,
                    symbol=coverage.symbol,
                    calendar="XNYS" if spec.kind == "equity" else "24/7",
                    adjustment="unadjusted",
                )
            )
    return tuple(bindings)


def _forecast_series(
    lake_root: Path,
    *,
    scenario: DemoScenario,
    symbol: str,
    sessions: int,
) -> HistoricalSeries:
    dataset_id = f"demo-moomoo-{symbol.lower()}"
    dataset = Lake(lake_root).dataset(dataset_id)
    observed = dataset.read_bars(
        interval="1d",
        venue=Venue.MOOMOO,
        symbol=symbol,
    )[-sessions:]
    coverage = next(
        item
        for item in dataset.manifest.coverage
        if item.interval == "1d" and item.venue is Venue.MOOMOO and item.symbol == symbol
    )
    bars = tuple(
        HistoricalBar(
            instrument=item.instrument,
            timestamp=item.timestamp,
            interval=item.interval,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
        )
        for item in observed
    )
    return HistoricalSeries(
        instrument=bars[0].instrument,
        range=HistoryRange.ONE_YEAR,
        as_of=scenario.anchor,
        bars=bars,
        dataset_id=dataset_id,
        dataset_revision=dataset.manifest.revision,
        source=dataset.manifest.source,
        license=dataset.manifest.license,
        generated_at=dataset.manifest.generated_at,
        interval="1d",
        calendar="XNYS",
        adjustment="unadjusted",
        coverage=CoverageSnapshot.model_validate(coverage.model_dump()),
        limitations=("Deterministic demo-synthetic analytical history.",),
    )


def _seed_price_forecasts(
    scenario: DemoScenario,
    root: Path,
    lake_root: Path,
    bindings: tuple[DatasetBinding, ...],
) -> PriceForecastRegistry:
    registry = PriceForecastRegistry(
        root / "research" / "price-forecasts",
        lake_root=lake_root,
        bindings=bindings,
    )
    for symbol, sessions in (("AAPL", 420), ("NVDA", 650)):
        series = _forecast_series(
            lake_root,
            scenario=scenario,
            symbol=symbol,
            sessions=sessions,
        )
        artifact = run_price_forecast(
            series,
            generated_at=scenario.anchor,
            model_version="demo-drift-conformal-v1",
        )
        registry.record(artifact)
    return registry


def _seed_account(
    scenario: DemoScenario, series: dict[str, dict[str, list[float]]], draw: generators._Draw
) -> tuple[PaperAccount, dict[str, float], dict[str, dict[str, float]], list[dict]]:
    """Replay the deterministic order sequence through real submits.

    Quotes derive from the same series the fixtures serve; order i is
    timestamped ``anchor - (n - i) * 5min`` so the whole replay sits
    inside the matcher's quote-age window and the timestamps are
    reproducible.
    """
    account = PaperAccount(
        cash=100_000.0,
        fee_model=FeeModel(fee_bps=10),
        matcher=PaperMatcher(slippage_bps=0.0),
    )
    # The full universe board: every seeded symbol carries a mark from
    # the same walk the fixtures serve, not only the traded ones. The
    # mark rounds like the fixture rows (2dp), so the board, the
    # providers' series and the P&L numbers agree exactly.
    marks = {
        f"{_venue(venue).value}:{symbol}": round(closes[-1], 2)
        for venue, symbols in series.items()
        for symbol, closes in symbols.items()
    }
    markets = {
        venue: {symbol: round(closes[-1], 2) for symbol, closes in symbols.items()}
        for venue, symbols in series.items()
    }
    quotes: list[dict] = []
    for index, (venue, symbol, side, quantity, limit_price) in enumerate(ORDER_SEQUENCE):
        kind = next(
            spec.kind
            for spec in (*scenario.equities, *scenario.crypto)
            if spec.venue == venue and spec.symbol == symbol
        )
        close = series[venue][symbol][-1]
        quote_time = scenario.anchor - timedelta(minutes=5 * (len(ORDER_SEQUENCE) - index))
        spread = close * 0.002
        quote = Quote(
            instrument=_instrument(symbol, venue, kind),
            timestamp=quote_time,
            bid=round(close - spread, 4),
            ask=round(close + spread, 4),
            last=round(close, 4),
            volume=1_000.0,
        )
        request = OrderRequest(
            instrument=quote.instrument,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
        )
        result = account.submit(request, quote, now=quote_time)
        account = result.account
        quotes.append(
            {
                "symbol": symbol,
                "side": side.value,
                "quantity": quantity,
                "limit_price": limit_price,
                "fill": result.rejection is None,
            }
        )
    return account, marks, markets, quotes


def _seed_research(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    lake_root: Path,
    series: dict[str, dict[str, list[float]]],
) -> dict[str, int]:
    """Experiments and strategy reports, pinned to the demo lake."""
    datasets = list(
        sorted(
            f"demo-{spec.venue}-{spec.symbol.lower()}"
            for spec in (*scenario.equities, *scenario.crypto)
        )
    )
    experiments = ExperimentRegistry(root=root / "research" / "experiments", lake_root=lake_root)
    for index in range(scenario.surface_counts["experiments"]):
        dataset = datasets[index % len(datasets)]
        parameters = {
            "window": 3 + draw.index(5),
            "entry": draw.choice(("close", "open")),
            "vol_filter": draw.index(2) == 0,
        }
        metrics = {
            "oos_mae": round(draw.uniform(0.2, 2.0), 4),
            "oos_rmse": round(draw.uniform(0.3, 3.0), 4),
            "n_windows": 1 + draw.index(3),
        }
        experiments.record(
            dataset=dataset,
            revision=1,
            commit=DEMO_COMMIT,
            parameters=parameters,
            metrics=metrics,
            # Earliest research surface: 8h..48h before anchor, before
            # the reports/promotions/alerts/decisions the UI reads later.
            created_at=scenario.anchor - timedelta(hours=8 * (index + 1)),
        )

    reports = ReportRegistry(root=root / "research" / "reports", lake_root=lake_root)
    strategies = ("momentum", "mean_reversion", "book_imbalance", "lightgbm")
    intervals = ("1d", "1d", "1d", "1d")
    universe_specs = (
        (scenario.equities,),
        (scenario.equities,),
        (scenario.crypto,),
        (scenario.crypto,),
    )
    for index, (strategy, interval, specs) in enumerate(zip(strategies, intervals, universe_specs)):
        universe = [
            UniverseMember(venue=_venue(spec.venue), symbol=spec.symbol) for spec in specs[0]
        ]
        window_spec = WalkForwardSpec(train_bars=3, test_bars=1, step_bars=1)
        costs = CostModel(fee_bps=10, half_spread_bps=5, slippage_bps=0)
        dataset = datasets[index % len(datasets)]
        report = StrategyReport(
            id=report_id(
                dataset=dataset,
                revision=1,
                commit=DEMO_COMMIT,
                strategy=strategy,
                interval=interval,
                universe=universe,
                window_spec=window_spec,
                costs=costs,
            ),
            dataset=dataset,
            revision=1,
            commit=DEMO_COMMIT,
            strategy=strategy,
            interval=interval,
            universe=universe,
            window_spec=window_spec,
            costs=costs,
            created_at=scenario.anchor - timedelta(hours=index + 1),
            metrics={
                "total_return": round(draw.normal() * 0.03, 4),
                "sharpe": round(draw.uniform(0.2, 2.4), 3),
                "max_drawdown": round(-draw.uniform(0.01, 0.08), 4),
            },
            evidence={
                "oos_return": round(draw.normal() * 0.02, 4),
                "n_trades": 10 + draw.index(40),
            },
            windows=[
                WindowResult(
                    index=0,
                    train_end=scenario.anchor - timedelta(days=2),
                    test_start=scenario.anchor - timedelta(days=1),
                    test_end=scenario.anchor,
                    window_return=round(draw.normal() * 0.02, 4),
                    turnover=round(draw.uniform(0.2, 0.9), 3),
                    cost=round(draw.uniform(0.001, 0.01), 5),
                    n_trades=1 + draw.index(6),
                )
            ],
        )
        reports.record(report)
    return {
        "experiments": scenario.surface_counts["experiments"],
        "reports": len(strategies),
    }


def _seed_forecasts(scenario: DemoScenario, draw: generators._Draw, root: Path) -> dict[str, int]:
    """Forecast reports over the prediction-market universe, through
    the real evaluation pipeline.

    The records are built manually (instead of ``run_forecast_report``)
    only so ``created_at`` derives from the scenario anchor: the
    pipeline's wall-clock stamp would break the byte-for-byte replay
    guarantee. Evaluation and artifacts are the real pipeline. The
    report count is the manifest contract; each report varies ``n_bins``
    so its content-addressed id is distinct.
    """
    registry = ForecastReportRegistry(root=root / "research" / "reports")
    markets: list[ForecastMarket] = []
    for venue, ticker, title, kind, base in scenario.prediction:
        rule_text = f"Resolved by the venue's official adjudication of: {title}"
        event = EventMarket(
            venue=EventVenue(venue),
            venue_market_id=ticker,
            event_ticker=ticker,
            title=title,
            category="Policy" if venue == "kalshi" else "Sports",
            start_at=scenario.open,
            expiry_at=scenario.anchor + timedelta(days=180),
            outcomes=[
                Outcome(name="Yes", venue_outcome_id="yes"),
                Outcome(name="No", venue_outcome_id="no"),
            ],
            resolution_rule=ResolutionRule.of(rule_text),
        )
        observations: list[ForecastObservation] = []
        probability = base
        for index in range(8):
            probability = min(0.95, max(0.05, probability + draw.normal() * 0.02))
            observations.append(
                ForecastObservation(
                    timestamp=scenario.anchor - timedelta(hours=8 - index),
                    probability=round(probability, 4),
                    liquidity_confidence=round(draw.uniform(0.4, 0.9), 3),
                )
            )
        markets.append(ForecastMarket(market=event, observations=observations))
    window_spec = ForecastWindowSpec(train_observations=5, test_observations=2, step_observations=2)
    universe = [entry.market for entry in markets]
    reports: list[ForecastReport] = []
    for index, n_bins in enumerate((4, 5, 3, 6)):
        metrics, per_market = run_forecast(markets, window_spec=window_spec, n_bins=n_bins)
        report = ForecastReport(
            id=forecast_report_id(
                commit=DEMO_COMMIT, universe=universe, window_spec=window_spec, n_bins=n_bins
            ),
            commit=DEMO_COMMIT,
            universe=universe,
            window_spec=window_spec,
            n_bins=n_bins,
            created_at=scenario.anchor - timedelta(hours=2 + index),
            metrics=metrics,
            markets=per_market,
        )
        _write_artifacts(registry.root, report)
        registry.record(report)
        reports.append(report)
    return {"forecasts": len(reports)}


def _seed_ledgers(
    scenario: DemoScenario,
    draw: generators._Draw,
    root: Path,
    report_ids: list[str],
    experiment_ids: list[str],
) -> dict[str, int]:
    """Promotions, alerts, mappings, decisions, documents — every ledger
    through its public append API, every id content-addressed."""
    promotions = PromotionLedger(root=root / "research" / "promotions")
    signal_names = ("momentum_equity_demo", "book_imbalance_crypto_demo", "lightgbm_equity_demo")
    for index, name in enumerate(signal_names):
        promote_signal(
            signal_name=name,
            evidence=PromotionEvidence(
                benchmark_ids=sorted(report_ids[:2]),
                ablation_ids=[report_ids[index % len(report_ids)]],
                oos_report_id=report_ids[(index + 1) % len(report_ids)],
            ),
            ledger=promotions,
            promoted_at=scenario.anchor - timedelta(hours=3 * (index + 1)),
        )

    alerts = AlertLedger(root=root / "alerts")
    alert_specs = (
        ("feature_drift", "demo:equity-features", "equity feature drift over the demo window"),
        (
            "prediction_drift",
            "demo:crypto-signals",
            "crypto signal distribution moved outside tolerance",
        ),
        (
            "staleness",
            "demo:market-board",
            "demo fixture feed reports no new sessions since anchor",
        ),
        ("failure", "demo:provider-probe", "a demo venue provider probe rejected a request"),
        (
            "reliability_limit",
            "demo:paper-matcher",
            "paper fills reached the seeded reliability limit",
        ),
    )
    for index, (kind, source, message) in enumerate(alert_specs):
        detected_at = scenario.anchor - timedelta(hours=2 * (index + 1))
        observed = {"value": round(draw.uniform(0.0, 1.0), 3)}
        alerts.record(
            AlertRecord(
                id=alert_id(kind=kind, source=source, detected_at=detected_at, observed=observed),
                kind=kind,
                source=source,
                detected_at=detected_at,
                message=message,
                observed=observed,
            )
        )

    mappings = MappingLedger(root=root / "mappings")
    pair_specs = (
        (
            "poly-fed-1",
            "kalshi-fed-1",
            MappingStatus.MATCHED,
            (
                ("title", "identical wording"),
                ("outcome_set", "Yes/No matches"),
            ),
        ),
        (
            "poly-fed-2",
            "kalshi-fed-2",
            MappingStatus.PENDING,
            (("title", "candidate wording"),),
        ),
        (
            "poly-fed-3",
            "kalshi-fed-3",
            MappingStatus.AMBIGUOUS,
            (
                ("title", "overlapping wording"),
                ("expiry", "expiry window overlaps"),
            ),
        ),
    )
    report = EventMappingReport(
        pairs=[
            EventPairing(
                pair_key=pair_key(poly, kalshi),
                polymarket_market_id=poly,
                kalshi_market_id=kalshi,
                status=status,
                evidence=sorted(
                    (
                        MappingEvidence(kind=EvidenceKind(kind), detail=detail)
                        for kind, detail in evidence
                    ),
                    key=lambda item: (item.kind.value, item.detail),
                ),
            )
            for poly, kalshi, status, evidence in pair_specs
        ]
    )
    mappings.record(
        report,
        commit=DEMO_COMMIT,
        recorded_at=scenario.anchor - timedelta(days=3),
    )

    decisions = DecisionLog(root=root / "decisions")
    # Content-addressed run ids: `hash()` is per-process randomized
    # (PYTHONHASHSEED), which would break the replay guarantee.
    run_ids = [
        hashlib.sha256(f"demo-run-{index}".encode()).hexdigest()[:16]
        for index in range(scenario.surface_counts["decisions"])
    ]

    class _VerdictOutput(BaseModel):
        verdict: str

    roles = ("analyst", "critic", "risk", "portfolio")
    for index, role in enumerate(roles):
        # Document ids are deterministic by construction (kind + order).
        document_id = (
            f"demo-{tuple(_DOCUMENT_TEXT)[index % len(_DOCUMENT_TEXT)]}-"
            f"{index % len(_DOCUMENT_TEXT) + 1}"
        )
        decisions.record(
            DecisionRecord.for_stage(
                run_id=run_ids[index],
                role=role,
                model=ModelMeta(name="demo-seeder", version="0.1.0", endpoint_kind="loopback"),
                prompt=f"Seeded {role} stage over the deterministic demo scenario (redacted).",
                schema_id="demo/verdict.v1",
                output=_VerdictOutput(verdict="pass" if role in ("critic", "risk") else "neutral"),
                citations=[
                    Citation(
                        source_kind="document",
                        source_id=document_id,
                        span=(0, 24),
                    ),
                    Citation(
                        source_kind="experiment",
                        source_id=experiment_ids[index % len(experiment_ids)],
                    ),
                ],
                recorded_at=scenario.anchor - timedelta(hours=index + 4),
            )
        )

    documents = DocumentIndex(root=root / "documents")
    source_dir = root / "documents" / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    for index, (kind, _template) in enumerate(_DOCUMENT_TEXT.items()):
        doc_id = f"demo-{kind}-{index + 1}"
        content = _DOCUMENT_TEXT[kind].format(", ".join(spec.symbol for spec in scenario.equities))
        path = source_dir / f"{doc_id}.txt"
        path.write_text(content, encoding="utf-8")
        # Before the decisions that cite them (4h..7h before anchor).
        # The relative reference is read against — and stored relative
        # to — the registry root, so the ledger bytes are the same in
        # any demo root (portable, byte-reproducible records).
        documents.ingest_file(
            Path("sources") / f"{doc_id}.txt",
            kind=kind,
            doc_id=doc_id,
            ingested_at=scenario.anchor - timedelta(hours=12 + 2 * index),
        )

    return {
        "promotions": len(signal_names),
        "alerts": len(alert_specs),
        "mappings": len(pair_specs),
        "decisions": len(roles),
        "documents": len(_DOCUMENT_TEXT),
    }


def seed_demo_root(root: Path, scenario: DemoScenario = DemoScenario()) -> DemoSeeded:
    """Seed one complete demo root, failing closed on a re-seed.

    A root that already carries the marker is refused — re-seeding is
    an explicit reset (``reset_demo_root``), never a silent overwrite.
    """
    root = Path(root)
    if is_demo_root(root):
        raise DemoRootError(
            f"demo root {root} is already seeded — use reset_demo_root "
            "(re-seeding is explicit, never silent)"
        )
    if root.exists():
        if not root.is_dir():
            raise DemoRootError(f"demo root {root} exists and is not a directory")
        if _is_link_or_junction(root):
            raise DemoRootError(f"demo root {root} is a link or junction")
        if any(root.iterdir()):
            raise DemoRootError(
                f"refusing to claim non-empty unmarked directory {root} as a demo root"
            )
    else:
        root.mkdir(parents=True, exist_ok=False)
    marker = _marker(root)
    with marker.open("x", encoding="utf-8") as handle:
        handle.write(_claim_marker_text())
    unexpected = [path for path in root.iterdir() if path != marker]
    if unexpected:
        marker.unlink()
        raise DemoRootError(f"demo root {root} changed while ownership was established")

    draw = generators._Draw(scenario.seed)
    series = generators.series_map(draw, scenario)

    fixture_rows, providers, _fixture_dir = _seed_market_data(scenario, draw, root, series)
    lake_root, dataset_rows, history_bindings = _seed_lake(scenario, series, root)
    history = _history_service(lake_root, history_bindings, scenario=scenario)
    price_forecasts = PriceForecastRegistry(
        root / "research" / "price-forecasts",
        lake_root=lake_root,
        bindings=history_bindings,
    )
    if scenario.workspace_history:
        price_forecasts = _seed_price_forecasts(
            scenario,
            root,
            lake_root,
            history_bindings,
        )
    proposal_ledger = ProposalLedger(root / "orders" / "proposals")
    account, marks, markets, order_quotes = _seed_account(scenario, series, draw)

    research_rows = _seed_research(scenario, draw, root, lake_root, series)
    forecast_rows = _seed_forecasts(scenario, draw, root)

    experiments = ExperimentRegistry(root=root / "research" / "experiments", lake_root=lake_root)
    reports = ReportRegistry(root=root / "research" / "reports", lake_root=lake_root)
    report_ids = [report.id for report in reports.all()]
    experiment_ids = [experiment.id for experiment in experiments.all()]
    forecasts = ForecastReportRegistry(root=root / "research" / "reports")

    # Documents must exist before decisions cite them.
    ledger_rows = _seed_ledgers(
        scenario, draw, root, report_ids=report_ids, experiment_ids=experiment_ids
    )

    # The paper journal snapshots the replayed orders (the audit trail).
    journal = OrderJournal(root=root / "orders")
    for order in account.orders.values():
        journal.record(order)

    watchlist = WatchlistStore(root=root / "watchlists")
    for venue, symbol in (
        (Venue.HYPERLIQUID, "BTC-USD"),
        (Venue.MOOMOO, "AAPL"),
        (Venue.MOOMOO, "NVDA"),
        (Venue.HYPERLIQUID, "SOL-USD"),
    ):
        watchlist.add(
            symbol,
            venue=venue,
            now=scenario.anchor - timedelta(hours=1),
        )

    enablement = ApprovalLedger(root=root / "enablement")
    enablement.request(
        Venue.MOOMOO,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=2),
    )
    enablement.request(
        Venue.HYPERLIQUID,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=2),
    )
    enablement.withdraw(
        Venue.HYPERLIQUID,
        actor="demo-operator",
        acted_at=scenario.anchor - timedelta(days=1),
    )

    rows = {
        **fixture_rows,  # keys already carry the market: provenance prefix
        **{f"lake:{name}": count for name, count in dataset_rows.items()},
        "history": sum(dataset_rows.values()),
        "price_forecasts": len(price_forecasts.all()),
        "paper_proposals": 0,
        "decision_packets": 0,
        "orders": len(order_quotes),
        **research_rows,
        **forecast_rows,
        **ledger_rows,
    }
    provenance = {
        "scenario": {
            "seed": scenario.seed,
            "workspace_history": scenario.workspace_history,
            "anchor": scenario.anchor.isoformat(),
            "open": scenario.open.isoformat(),
            "commit": DEMO_COMMIT,
        },
        "surfaces": _provenance_rows(rows, scenario.anchor),
    }
    (root / "provenance.json").write_text(json.dumps(provenance, indent=1), encoding="utf-8")
    _write_account(root, account)
    proposal_root = root / "orders" / "proposals"
    proposal_root.mkdir(parents=True, exist_ok=True)
    (proposal_root / ".proposals.lock").write_text("", encoding="utf-8")
    (proposal_root / "proposals.jsonl").write_text("", encoding="utf-8")
    decision_packet_root = root / "decisions" / "packets"
    decision_packet_root.mkdir(parents=True, exist_ok=True)
    (decision_packet_root / ".decision-packets.lock").write_text("", encoding="utf-8")
    (decision_packet_root / "decision-action-intents.jsonl").write_text("", encoding="utf-8")
    (decision_packet_root / "decision-packets.jsonl").write_text("", encoding="utf-8")
    packet_copilot_root = root / "decisions" / "copilot"
    packet_copilot_root.mkdir(parents=True, exist_ok=True)
    (packet_copilot_root / "packet-copilot-records.jsonl").write_text("", encoding="utf-8")
    packet_monitoring_root = root / "decisions" / "monitoring"
    packet_monitoring_root.mkdir(parents=True, exist_ok=True)
    (packet_monitoring_root / ".decision-watch.lock").write_text("", encoding="utf-8")
    (packet_monitoring_root / "watch-registrations.jsonl").write_text("", encoding="utf-8")
    (packet_monitoring_root / "watch-evaluations.jsonl").write_text("", encoding="utf-8")
    ownership_text = _ownership_text(root)
    (root / OWNERSHIP_NAME).write_text(ownership_text, encoding="utf-8")
    ownership_sha256 = hashlib.sha256(ownership_text.encode("utf-8")).hexdigest()
    marker.write_text(_marker_text(ownership_sha256), encoding="utf-8")

    return DemoSeeded(
        root=root,
        scenario=scenario,
        account=account,
        marks=marks,
        markets=markets,
        watchlist=watchlist,
        experiments=experiments,
        promotions=PromotionLedger(root=root / "research" / "promotions"),
        reports=reports,
        forecasts=forecasts,
        alerts=AlertLedger(root=root / "alerts"),
        journal=journal,
        mappings=MappingLedger(root=root / "mappings"),
        decisions=DecisionLog(root=root / "decisions"),
        documents=DocumentIndex(root=root / "documents"),
        enablement=enablement,
        providers=providers,
        history=history,
        price_forecasts=price_forecasts,
        proposal_ledger=proposal_ledger,
        decision_packets=DecisionPacketStore(decision_packet_root),
        packet_copilot=PacketCopilotStore(root / "decisions" / "copilot"),
        packet_monitoring=DecisionWatchStore(root / "decisions" / "monitoring"),
        provenance=provenance,
    )


def load_demo_root(root: Path, scenario: DemoScenario = DemoScenario()) -> DemoSeeded:
    """Rebuild the in-memory assembly from an existing demo root.

    The ledgers read their files lazily; the account comes from the
    persisted snapshot; marks/markets are re-derived from the same
    deterministic walk (identical by construction). Nothing is
    rewritten — a restart is a read, not a re-seed.
    """
    root = Path(root)
    if not is_demo_root(root):
        raise DemoRootError(
            f"{root} is not a demo root — it has no {MARKER_NAME} marker; "
            "reset and re-seed never touch a root that lacks it"
        )
    scenario = _load_scenario(root, scenario)
    draw = generators._Draw(scenario.seed)
    series = generators.series_map(draw, scenario)
    fixture_root = root / "market" / "fixtures"
    providers = DemoProviders(
        {
            (spec.venue, spec.symbol): (
                MoomooFixtureProvider(fixture_dir=fixture_root / spec.venue / spec.symbol)
                if spec.kind == "equity"
                else HyperliquidFixtureProvider(fixture_dir=fixture_root / spec.venue / spec.symbol)
            )
            for spec in (*scenario.equities, *scenario.crypto)
        },
        {(spec.venue, spec.symbol): spec.kind for spec in (*scenario.equities, *scenario.crypto)},
    )
    account = PaperAccount.model_validate_json((root / "account.json").read_text(encoding="utf-8"))
    marks = {
        f"{_venue(venue).value}:{symbol}": round(closes[-1], 2)
        for venue, symbols in series.items()
        for symbol, closes in symbols.items()
    }
    markets = {
        venue: {symbol: round(closes[-1], 2) for symbol, closes in symbols.items()}
        for venue, symbols in series.items()
    }
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    lake_root = root / "market" / "lake"
    history_bindings = _history_bindings_from_lake(lake_root, scenario)
    history = _history_service(
        lake_root,
        history_bindings,
        scenario=scenario,
    )
    stores = build_workstation_stores(root=root, lake_root=lake_root)
    return DemoSeeded(
        root=root,
        scenario=scenario,
        account=account,
        marks=marks,
        markets=markets,
        watchlist=stores.watchlist,
        experiments=stores.experiments,
        promotions=stores.promotions,
        reports=stores.reports,
        forecasts=stores.forecasts,
        alerts=stores.alerts,
        journal=stores.journal,
        mappings=stores.mappings,
        decisions=stores.decisions,
        documents=stores.documents,
        enablement=stores.enablement,
        providers=providers,
        history=history,
        price_forecasts=PriceForecastRegistry(
            root / "research" / "price-forecasts",
            lake_root=lake_root,
            bindings=history_bindings,
        ),
        proposal_ledger=ProposalLedger(root / "orders" / "proposals"),
        decision_packets=stores.decision_packets,
        packet_copilot=stores.packet_copilot,
        packet_monitoring=stores.packet_monitoring,
        provenance=provenance,
    )


def _load_scenario(root: Path, default: DemoScenario) -> DemoScenario:
    """Reconstruct the scenario the root was seeded with, so a restart
    with a different default never misreads a mismatched root."""
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    scenario = provenance.get("scenario", {})
    return DemoScenario(
        seed=int(scenario.get("seed", default.seed)),
        workspace_history=bool(scenario.get("workspace_history", default.workspace_history)),
        anchor=datetime.fromisoformat(scenario["anchor"]),
        open=datetime.fromisoformat(scenario["open"]),
    )


def reset_demo_root(
    root: Path,
    scenario: DemoScenario = DemoScenario(),
    *,
    trusted_ownership_text: str | None = None,
    trusted_reset_archive: bytes | None = None,
) -> DemoSeeded:
    """Atomically replace a demo root and retain the old tree for recovery.

    The marker is the isolation contract: without it the root is not a
    demo root and reset refuses to touch it — a non-demo directory can
    never be replaced by the demo runtime. Reset never recursively deletes
    a runtime path because an external process could swap that path after
    validation.
    """
    root = Path(root)
    with _interprocess_reset_lock(root):
        # Build the independent expected inventory once. Both the public-path
        # check and the identity-bound quarantine check compare against this
        # same immutable truth; regenerating it twice adds no safety property
        # and makes full-history resets exceed the operator timeout.
        trusted_ownership_text = (
            trusted_ownership_text
            if trusted_ownership_text is not None
            else (_trusted_ownership_text(scenario) if is_demo_root(root) else None)
        )
        try:
            root_identity = filesystem_identity(root)
        except OSError:
            root_identity = None
        if (
            trusted_ownership_text is None
            or root_identity is None
            or not _has_reset_structure(
                root,
                scenario,
                trusted_ownership_text=trusted_ownership_text,
            )
        ):
            marker_note = (
                f"no {MARKER_NAME} marker"
                if not _marker(root).is_file()
                else "no valid demo ownership record and complete seeded structure"
            )
            raise DemoRootError(
                f"refusing to reset {root}: {marker_note} — "
                "the demo runtime never touches a non-demo root"
            )
        try:
            if filesystem_identity(root) != root_identity:
                raise DemoRootError(
                    f"refusing to reset {root}: filesystem identity changed during "
                    "trusted ownership validation"
                )
        except OSError as error:
            raise DemoRootError(
                f"refusing to reset {root}: filesystem identity unavailable after "
                "trusted ownership validation"
            ) from error

        # Construct the replacement before moving the served root. This keeps
        # the public demo available during deterministic generation and turns
        # publication into two bounded atomic renames. The sibling
        # starts empty and unmarked, so ``seed_demo_root`` retains ownership of
        # every byte it creates.
        replacement = _unused_reset_quarantine(root)
        try:
            if trusted_reset_archive is None:
                seed_demo_root(replacement, scenario)
            else:
                _restore_demo_reset_archive(trusted_reset_archive, replacement)
                load_demo_root(replacement, scenario)
        except BaseException as error:
            if replacement.exists():
                raise DemoRootError(
                    f"reset replacement could not establish trusted ownership; "
                    f"preserving {replacement}"
                ) from error
            raise
        replacement_identity = _require_demo_tree_identity(
            replacement,
            scenario,
            trusted_ownership_text=trusted_ownership_text,
            failure_message="reset replacement failed identity validation",
        )

        # Move the exact directory object away from the public path first,
        # then validate the quarantined object again. Runtime reset never
        # recursively deletes the quarantine or replacement: path identity
        # cannot stay bound between a completed validation and path-based
        # recursive deletion. Every leftover is retained for operator recovery.
        quarantine = _unused_reset_quarantine(root)
        try:
            atomic_replace(root, quarantine)
            _require_demo_tree_identity(
                quarantine,
                scenario,
                trusted_ownership_text=trusted_ownership_text,
                expected_identity=root_identity,
                failure_message=(
                    f"demo root {root} changed after it was quarantined; "
                    "preserving paths because identity or ownership changed"
                ),
            )
            atomic_replace(replacement, root)
            try:
                published_identity = filesystem_identity(root)
            except OSError:
                published_identity = None
            if published_identity != replacement_identity:
                retained = _restore_original_after_publish_mismatch(
                    root,
                    quarantine,
                    scenario,
                    trusted_ownership_text=trusted_ownership_text,
                    root_identity=root_identity,
                    published_identity=published_identity,
                )
                raise DemoRootError(
                    "published replacement identity did not match the validated replacement; "
                    f"restored the original demo and retained {retained}",
                    retained_paths=retained,
                )
            try:
                _require_demo_tree_identity(
                    root,
                    scenario,
                    trusted_ownership_text=trusted_ownership_text,
                    expected_identity=replacement_identity,
                    failure_message="published reset replacement failed identity validation",
                )
            except DemoRootError as error:
                retained = _restore_original_after_publish_mismatch(
                    root,
                    quarantine,
                    scenario,
                    trusted_ownership_text=trusted_ownership_text,
                    root_identity=root_identity,
                    published_identity=published_identity,
                )
                raise DemoRootError(
                    "published replacement failed trusted structure validation; "
                    f"restored the original demo and retained {retained}",
                    retained_paths=retained,
                ) from error
            try:
                seeded = load_demo_root(root, scenario)
            except BaseException as error:
                retained = _restore_original_after_publish_mismatch(
                    root,
                    quarantine,
                    scenario,
                    trusted_ownership_text=trusted_ownership_text,
                    root_identity=root_identity,
                    published_identity=published_identity,
                )
                raise DemoRootError(
                    "published replacement failed final load; "
                    f"restored the original demo and retained {retained}",
                    retained_paths=retained,
                ) from error
        except BaseException:
            if not root.exists() and quarantine.exists():
                try:
                    quarantine_is_original = filesystem_identity(quarantine) == root_identity
                except OSError:
                    quarantine_is_original = False
                if quarantine_is_original:
                    atomic_replace(quarantine, root)
            raise

        # Return the assembly loaded inside the rollback boundary. The old
        # identity-validated tree remains at ``quarantine`` for an operator to
        # inspect and remove outside the running reset boundary.
        return seeded
