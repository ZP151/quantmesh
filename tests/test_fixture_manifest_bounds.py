"""Small JSON-only gates; these do not admit Parquet content or native execution."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from quantmesh.research import fixture_snapshot as snapshot
from quantmesh.research.jobs import DatasetRejected


def manifest():
    return dict(
        schema_version=1,
        dataset="equities",
        source="fixture",
        license="test",
        timezone="UTC",
        revision=1,
        generated_at="2026-01-05T00:00:00Z",
        coverage=[
            dict(
                interval="1h",
                venue="moomoo",
                symbol="AAA",
                rows=3,
                start="2026-01-05T00:00:00Z",
                end="2026-01-05T02:00:00Z",
            )
        ],
    )


def decode(value):
    parser = getattr(snapshot, "_parse_manifest", None)
    assert callable(parser), "bounded metadata decoder missing"
    return parser(json.dumps(value).encode())


def test_valid_manifest_preserves_declared_values():
    result = decode(manifest())
    assert result.dataset == "equities"
    assert result.coverage[0].rows == 3


@pytest.mark.parametrize(
    "field,value",
    [("revision", True), ("revision", "1"), ("schema_version", True), ("schema_version", "1")],
)
def test_numeric_manifest_scalars_are_not_coerced(field, value):
    value_manifest = manifest()
    value_manifest[field] = value
    with pytest.raises(DatasetRejected, match="fixture_snapshot_invalid"):
        decode(value_manifest)


@pytest.mark.parametrize("rows", [True, "3", 3.0, 0, -1, 1_000_001])
def test_declared_rows_are_exact_positive_bounded_integers(rows):
    value = manifest()
    value["coverage"][0]["rows"] = rows
    with pytest.raises(DatasetRejected):
        decode(value)


def test_declared_row_limit_is_cumulative(monkeypatch):
    monkeypatch.setattr(snapshot, "MAX_DECLARED_ROWS", 5, raising=False)
    value = manifest()
    value["coverage"].append(dict(value["coverage"][0], symbol="BBB"))
    with pytest.raises(DatasetRejected):
        decode(value)


@pytest.mark.parametrize("nested", [False, True])
def test_unknown_fields_are_rejected(nested):
    value = manifest()
    target = value["coverage"][0] if nested else value
    target["ignored_payload"] = {"unexpected": [1, 2, 3]}
    with pytest.raises(DatasetRejected):
        decode(value)


def test_deep_json_is_rejected_before_json_decoder(monkeypatch):
    parser = getattr(snapshot, "_parse_manifest", None)
    assert callable(parser), "bounded metadata decoder missing"

    def forbidden(*args, **kwargs):
        pytest.fail("JSON decoder reached before depth rejection")

    monkeypatch.setattr(snapshot.json, "loads", forbidden)
    with pytest.raises(DatasetRejected):
        parser(b"[" * 17 + b"0" + b"]" * 17)


def test_brackets_inside_escaped_strings_do_not_count_as_depth():
    value = manifest()
    value["source"] = 'literal [ { \\" ' + "]" * 20
    assert decode(value).source == value["source"]


def test_node_budget_precedes_model_validation(monkeypatch):
    monkeypatch.setattr(snapshot, "MAX_JSON_NODES", 5, raising=False)
    monkeypatch.setattr(
        snapshot.DatasetManifest,
        "model_validate",
        lambda *a, **kw: pytest.fail("model reached before node budget rejection"),
    )
    with pytest.raises(DatasetRejected):
        decode(manifest())


def test_string_budget_is_enforced():
    value = manifest()
    value["source"] = "x" * 513
    with pytest.raises(DatasetRejected):
        decode(value)


def test_byte_budget_is_enforced_before_decoding(monkeypatch):
    monkeypatch.setattr(snapshot, "MAX_MANIFEST_BYTES", 10)
    with pytest.raises(DatasetRejected):
        decode(manifest())


@pytest.mark.parametrize(
    "raw", [b'{"coverage":[],"coverage":[]}', b'{"value":NaN}', b'{"value":1e999}', b"\xff", b"{"]
)
def test_bad_json_uses_sanitized_failure(raw):
    parser = getattr(snapshot, "_parse_manifest", None)
    assert callable(parser), "bounded metadata decoder missing"
    with pytest.raises(DatasetRejected, match="^dataset rejected: fixture_snapshot_invalid$"):
        parser(raw)


def test_manifest_limit_accepts_exact_boundary(monkeypatch):
    value = manifest()
    raw = json.dumps(value).encode()
    monkeypatch.setattr(snapshot, "MAX_MANIFEST_BYTES", len(raw))
    monkeypatch.setattr(snapshot, "MAX_DECLARED_ROWS", 3)
    monkeypatch.setattr(snapshot, "MAX_COVERAGE", 1)
    assert snapshot._parse_manifest(raw).coverage[0].rows == 3
    value["coverage"].append(dict(value["coverage"][0], symbol="BBB", rows=1))
    with pytest.raises(DatasetRejected):
        decode(value)


@pytest.mark.parametrize(
    "field,value", [("source", 123), ("generated_at", 0), ("data_class", {}), ("coverage", {})]
)
def test_manifest_field_types_are_not_coerced(field, value):
    metadata = manifest()
    metadata[field] = value
    with pytest.raises(DatasetRejected):
        decode(metadata)


@pytest.mark.parametrize("fault", ["metadata", "universe"])
def test_snapshot_refuses_declaration_or_request_before_shard_pin(tmp_path, monkeypatch, fault):
    """Scripted byte-copy boundary only, independent of native/POSIX admission."""
    value = manifest()
    if fault == "metadata":
        value["coverage"][0]["rows"] = True
    raw = json.dumps(value).encode()
    ref = SimpleNamespace(
        dataset_id="equities",
        permission_class="fixture",
        manifest_digest=hashlib.sha256(raw).hexdigest(),
        revision=1,
    )
    job = SimpleNamespace(
        request=SimpleNamespace(dataset=ref, budget=SimpleNamespace(timeout_seconds=1))
    )
    if fault == "universe":
        request = shape_job(tuple("AAA" for _ in range(65))).request
        request.dataset = ref
        request.budget = job.request.budget
        job = SimpleNamespace(request=request)

    class ByteSource:
        def __init__(self, *args):
            pass

        def stream(self, *args, **kwargs):
            return ref.manifest_digest, (), raw

        def pin(self, *args):
            pytest.fail("shard pin reached before metadata rejection")

        def __exit__(self):
            pass

    monkeypatch.setattr(snapshot, "require_snapshot_profile", lambda: None)
    monkeypatch.setattr(snapshot, "_Copy", ByteSource)
    with pytest.raises(DatasetRejected):
        snapshot.copy_fixture_snapshot(job, tmp_path / "source", tmp_path / "target")


def shape_job(symbols=("AAA",), train=2, test=1, step=1):
    return SimpleNamespace(
        request=SimpleNamespace(
            interval="1h",
            universe=[
                SimpleNamespace(venue=SimpleNamespace(value="moomoo"), symbol=s) for s in symbols
            ],
            window_spec=SimpleNamespace(train_bars=train, test_bars=test, step_bars=step),
        )
    )


def request_shape(job, metadata):
    guard = getattr(snapshot, "_validate_request_shape", None)
    assert callable(guard), "request allocation guard missing"
    guard(job, snapshot._parse_manifest(json.dumps(metadata).encode()))


def test_valid_request_shape_requires_no_allocated_windows():
    request_shape(shape_job(), manifest())


def test_request_universe_limit_precedes_series_matching():
    with pytest.raises(DatasetRejected):
        request_shape(shape_job(tuple("AAA" for _ in range(65))), manifest())


@pytest.mark.parametrize("symbol", ["BBB", "missing"])
def test_missing_selected_series_refuses(symbol):
    with pytest.raises(DatasetRejected):
        request_shape(shape_job((symbol,)), manifest())


def test_window_budget_is_calculated_without_test_starts():
    value = manifest()
    value["coverage"][0]["rows"] = 4099
    with pytest.raises(DatasetRejected):
        request_shape(shape_job(), value)
    value["coverage"][0]["rows"] = 4098
    request_shape(shape_job(), value)


def test_selected_series_counts_must_align_before_copy():
    value = manifest()
    value["coverage"].append(dict(value["coverage"][0], symbol="BBB", rows=4))
    with pytest.raises(DatasetRejected):
        request_shape(shape_job(("AAA", "BBB")), value)


def test_request_requires_a_complete_test_window():
    with pytest.raises(DatasetRejected):
        request_shape(shape_job(train=3, test=1), manifest())
