"""Same-capture representation regression; no financial calculation or SDK."""

import copy
import hashlib
import json
import locale
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest

from quantmesh.data.objects import ObjectRef, ObjectStore
from quantmesh.research import spy_replay as replay
from tests.test_freeze_opend_spy_daily import AS_OF, payload, post_review
from tests.test_spy_policy_exception_freeze import authority as _authority
from tests.test_spy_policy_exception_freeze import consumed
from tools.research import freeze_opend_spy_daily as freezer

PROFILE = "opend_spy_cash_dividend_en_month_v1"
FORMAT = "english_month_abbrev_day_year"


def event_input():
    factors = [
        {"ex_div_date": "2026-09-18", "per_cash_div": 1.88883},
        {"ex_div_date": "2026-06-18", "per_cash_div": 1.90352},
    ]
    dividends = [
        {
            "ex_date": "Sep 18, 2026",
            "dividend_payable_date": "Oct 30, 2026",
            "statement": "Cash Dividend: 1.88883USD",
        },
        {
            "ex_date": "Jun 18, 2026",
            "dividend_payable_date": "Jul 31, 2026",
            "statement": "Cash Dividend: 1.90352USD",
        },
        {
            "ex_date": "Dec 20, 2024",
            "dividend_payable_date": "OUTSIDE_WINDOW_UNPARSED",
            "statement": "Cash Gain: NOT_A_SUPPORTED_CASH_SYNTAX",
        },
    ]
    return (
        {
            "adjustment_factors": {"code": "US.SPY", "rows": factors},
            "dividends": {"code": "US.SPY", "rows": dividends},
        },
        {"sessions": ["2026-06-18", "2026-09-18"], "score_start": "2026-09-28"},
        {"normalization_profile": PROFILE, "event_date_format": FORMAT},
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sep 18, 2026", "2026-09-18"),
        ("Jun 18, 2026", "2026-06-18"),
        ("Oct 30, 2026", "2026-10-30"),
        ("Jul 31, 2026", "2026-07-31"),
        ("Feb 29, 2024", "2024-02-29"),
    ],
)
def test_fixed_english_dates_do_not_depend_on_locale(text, expected, monkeypatch):
    def forbidden(*args):
        raise AssertionError("normalizer must not call locale")

    monkeypatch.setattr(locale, "setlocale", forbidden)
    assert freezer._event_day(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Sept 18, 2026",
        "SEP 18, 2026",
        "Sep 018, 2026",
        "Sep 18, 26",
        " Sep 18, 2026",
        "Sep 18, 2026 ",
        "Apr 31, 2026",
        "Feb 29, 2026",
        "Jun  18, 2026",
        "九月 18, 2026",
        "Sep 00, 2026",
        "Sep 18, 0000",
        True,
        42,
        {"date": "Sep 18, 2026"},
    ],
)
def test_unsupported_or_impossible_date_refuses(text):
    with pytest.raises(ValueError):
        freezer._event_day(text)


def test_derived_view_keeps_raw_and_both_warmup_pay_dates_and_filters_cash_gain():
    raw, window, review = event_input()
    before = copy.deepcopy(raw)
    derived = freezer._event_view(raw, window, review)
    assert raw == before and derived is not raw
    rows = derived["dividends"]["rows"]
    assert len(rows) == len(raw["dividends"]["rows"]) == 3
    assert [(r["ex_date"], r["dividend_payable_date"], r["statement"]) for r in rows[:2]] == [
        ("2026-09-18", "2026-10-30", "Cash Dividend: 1.88883 USD Per Share"),
        ("2026-06-18", "2026-07-31", "Cash Dividend: 1.90352 USD Per Share"),
    ]
    assert rows[2]["statement"] == before["dividends"]["rows"][2]["statement"]
    assert rows[2]["dividend_payable_date"] == "OUTSIDE_WINDOW_UNPARSED"
    assert all(row["ex_date"] < window["score_start"] for row in rows[:2])


@pytest.mark.parametrize(
    "statement",
    [
        "Cash Dividend: 1.88883EUR",
        "Cash Dividend: 1.88883USD, Cash Dividend: 0.1USD",
        "Cash Gain: 1.88883USD",
        "Special Dividend: 1.88883USD",
        "Cash Dividend: 1e0USD",
        "Cash Dividend: -1.88883USD",
        "Cash Dividend: 0USD",
        "Cash Dividend: 1.88883 USD",
        "Cash Dividend: 1.88883USD Per Share",
        "Cash Dividend: 1.888830000000001USD",
    ],
)
def test_compact_cash_is_single_exact_usd_dividend_only(statement):
    raw, window, review = event_input()
    raw["dividends"]["rows"][0]["statement"] = statement
    with pytest.raises(ValueError):
        freezer._event_view(raw, window, review)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "mismatch", "boolean"])
def test_exact_unique_same_ex_per_share_cross_proof_is_required(mutation):
    raw, window, review = event_input()
    rows = raw["adjustment_factors"]["rows"]
    if mutation == "missing":
        rows.pop(0)
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == "mismatch":
        rows[0]["per_cash_div"] = 1.8888300000000002
    else:
        rows[0]["per_cash_div"] = True
    with pytest.raises(ValueError):
        freezer._event_view(raw, window, review)


def test_warmup_missing_pay_rule_is_not_strengthened():
    raw, window, review = event_input()
    raw["dividends"]["rows"][0]["dividend_payable_date"] = None
    derived = freezer._event_view(raw, window, review)
    assert derived["dividends"]["rows"][0]["dividend_payable_date"] is None
    # Existing actions, not this representation helper, owns score-period pay gates.


def test_original_parsers_keep_original_acceptance_boundaries():
    assert freezer._day("2026-09-18") == "2026-09-18"
    assert freezer._cash_statement("Cash Dividend: 1.88883 USD Per Share") == 1.88883
    with pytest.raises(ValueError):
        freezer._day("Sep 18, 2026")
    with pytest.raises(ValueError):
        freezer._cash_statement("Cash Dividend: 1.88883USD")


@pytest.fixture
def compat_case(tmp_path, monkeypatch):
    # Test-only trust/cohort replacement; no public override and no real qualification.
    authority = _authority.__wrapped__(tmp_path, monkeypatch)
    root, _, binding = authority
    auth, marker = consumed(authority)
    base = payload(freezer.plan_window(AS_OF))
    event_raw, _, _ = event_input()
    factor_template = base["adjustment_factors"]["rows"][0]
    base["adjustment_factors"]["rows"] = [
        {**factor_template, **r} for r in event_raw["adjustment_factors"]["rows"]
    ]
    base["dividends"] = event_raw["dividends"]
    raw = {
        **base,
        "schema_version": 3,
        "authorization_sha256": freezer._digest(auth),
        "requested_at_utc": (AS_OF + timedelta(seconds=30)).isoformat(),
        "capture_intent_ref": marker,
    }
    cohort = {
        "capture_sha256": freezer._digest(raw),
        "authorization_sha256": freezer._digest(auth),
        "capture_intent_sha256": marker["digest"],
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "collector_sha256": "3" * 64,
        "source_code_sha256": dict(freezer._LOADED_SOURCES),
    }
    monkeypatch.setattr(freezer, "_EVENT_COHORT", cohort, raising=False)
    review = {
        **post_review(raw, auth),
        "schema_version": 3,
        "policy_exception": binding,
        "capture_intent_ref": marker,
        "normalization_profile": PROFILE,
        "event_date_format": FORMAT,
    }
    return root, raw, auth, review, binding, cohort


def freeze_case(case):
    root, raw, auth, review, _, _ = case
    return freezer.freeze_capture(
        raw,
        AS_OF,
        {"schema_version": 3, "authorization": auth, "review": review},
        root,
        frozen_at=AS_OF + timedelta(minutes=3),
    )


def test_profile_freeze_keeps_capture_origin_separate_from_new_normalizer(compat_case):
    root, raw, _, review, _, cohort = compat_case
    before = freezer._canonical(raw)
    frozen = freeze_case(compat_case)
    reopened = freezer.reopen_freeze(root, frozen["freeze_digest"], policy_exception=True)
    protocol = reopened["protocol"]
    assert protocol["normalization"] == {
        "profile": PROFILE,
        "profile_version": 1,
        "capture_origin": cohort,
    }
    assert (
        protocol["normalizer_sha256"]
        == hashlib.sha256(Path(freezer.__file__).read_bytes()).hexdigest()
    )
    assert protocol["normalizer_sha256"] != cohort["collector_sha256"]
    store = ObjectStore(root)
    assert (
        store.get_bytes(ObjectRef.model_validate(frozen["members"]["raw-capture.json"])) == before
    )
    assert (
        json.loads(store.get_bytes(ObjectRef.model_validate(frozen["members"]["post-review.json"])))
        == review
    )
    warmup = json.loads(
        store.get_bytes(ObjectRef.model_validate(frozen["members"]["warmup-distributions.json"]))
    )
    assert len(warmup) == 2 and {x["pay_date"] for x in warmup} == {"2026-07-31", "2026-10-30"}
    assert (
        json.loads(
            store.get_bytes(
                ObjectRef.model_validate(frozen["members"]["normalized-distributions.json"])
            )
        )
        == []
    )


@pytest.mark.parametrize("key", ["capture_sha256", "authorization_sha256", "capture_intent_ref"])
def test_profile_cannot_be_used_for_a_different_cohort(compat_case, key):
    review = copy.deepcopy(compat_case[3])
    if key == "capture_intent_ref":
        review[key]["digest"] = "f" * 64
    else:
        review[key] = "f" * 64
    with pytest.raises(ValueError):
        freezer._normalization_metadata(review)


def test_profile_is_not_a_legacy_schema_or_unqualified_field_escape(compat_case):
    review = copy.deepcopy(compat_case[3])
    with pytest.raises(ValueError):
        freezer._typed_record(freezer.PostReview, {**review, "schema_version": 2}, (), "invalid")
    review["normalization_profile"] = "unreviewed_profile"
    with pytest.raises(ValueError):
        freezer._post_review_v3(review)
    review["normalization_profile"] = PROFILE
    review["volume_unit"] = "lots"
    with pytest.raises(ValueError):
        freezer._post_review_v3(review)


def test_no_profile_v3_retains_original_record_and_protocol_field_set(compat_case):
    _, _, _, review, binding, _ = compat_case
    record = {k: v for k, v in review.items() if k != "normalization_profile"}
    record["event_date_format"] = "%Y/%m/%d"
    assert freezer._post_review_v3(record) == record
    assert freezer._normalization_metadata(record) is None
    protocol = freezer._protocol_v3(
        freezer.plan_window(AS_OF), binding, review["capture_intent_ref"]
    )
    assert "normalization" not in protocol
    record["event_date_format"] = FORMAT
    with pytest.raises(ValueError):
        freezer._post_review_v3(record)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("noncash", "noncash_action_unsupported"),
        ("observation_pay_missing", "payment_date_missing_or_invalid"),
        ("duplicate", "duplicate_dividend"),
    ],
)
def test_derived_view_still_passes_through_original_action_refusals(compat_case, mutation, code):
    _, raw, _, review, _, _ = compat_case
    raw = {key: copy.deepcopy(raw[key]) for key in freezer._PAYLOAD_KEYS}
    window = freezer.plan_window(AS_OF)
    if mutation == "noncash":
        raw["adjustment_factors"]["rows"][0]["split_ratio"] = 2
    elif mutation == "observation_pay_missing":
        # This standalone actions vector makes the existing score-period guard observable.
        window = {**window, "score_start": "2026-06-01"}
        raw["dividends"]["rows"][0]["dividend_payable_date"] = None
    else:
        raw["dividends"]["rows"].append(copy.deepcopy(raw["dividends"]["rows"][0]))
    derived = freezer._event_view(raw, window, review)
    with pytest.raises(ValueError, match=code):
        freezer._actions(derived, window, {**review, "event_date_format": "%Y-%m-%d"})


@pytest.mark.parametrize("mutation", ["source_hash", "profile_version"])
def test_reopen_refuses_self_declared_profile_lineage(compat_case, mutation):
    frozen = freeze_case(compat_case)
    store = ObjectStore(compat_case[0])
    protocol = json.loads(store.get_bytes(ObjectRef.model_validate(frozen["protocol_ref"])))
    if mutation == "source_hash":
        protocol["normalization"]["capture_origin"]["collector_sha256"] = "f" * 64
    else:
        protocol["normalization"]["profile_version"] = 2
    ref = store.put_bytes("application/json", freezer._canonical(protocol))
    manifest = {k: v for k, v in frozen.items() if k not in {"freeze_digest", "freeze_ref"}}
    manifest["protocol_ref"] = ref.model_dump(mode="json")
    changed = store.put_bytes("application/json", freezer._canonical(manifest))
    with pytest.raises(ValueError, match="protocol_setup_invalid"):
        freezer.reopen_freeze(compat_case[0], changed.digest, policy_exception=True)


def descriptor_for(case, frozen):
    root, _, auth, review, binding, _ = case
    store = ObjectStore(root)
    acceptance = {
        "schema_version": 3,
        "status": "accepted_for_policy_exception_historical_diagnostic",
        "scope": "US.SPY/1d/private_research",
        "snapshot_digest": frozen["freeze_digest"],
        "protocol_digest": frozen["protocol_ref"]["digest"],
        "use_document_sha256": binding["policy_document_ref"]["digest"],
        "independent_input_review_sha256": "e" * 64,
        "authorization_sha256": freezer._digest(auth),
        "post_review_sha256": freezer._digest(review),
        "policy_exception": binding,
        "capture_intent_ref": review["capture_intent_ref"],
        "reviewed_at_utc": (AS_OF + timedelta(minutes=4)).isoformat(),
    }
    ref = store.put_bytes("application/json", freezer._canonical(acceptance))
    path = root / "controlled-descriptor.json"
    path.write_bytes(
        freezer._canonical(
            {
                "schema_version": 3,
                "freeze_root": str(root),
                "freeze_digest": frozen["freeze_digest"],
                "acceptance": ref.model_dump(mode="json"),
            }
        )
    )
    return path


def test_profile_job_and_cold_reopen_bind_original_profile_without_current_input(
    compat_case, tmp_path, monkeypatch
):
    frozen = freeze_case(compat_case)
    value = replay.ReplayInput.from_descriptor(descriptor_for(compat_case, frozen))
    calls = []

    def sentinel(*args):
        calls.append(1)
        return {"controlled_test_seam": "NO_FINANCIAL_COMPUTATION"}

    monkeypatch.setattr(replay.engine, "calculate", sentinel)
    request = replay.ReplayRequest(
        snapshot_digest=value.snapshot_digest, protocol_digest=replay.digest(value.protocol_bytes)
    )
    key, target = compat_case[4]["job_idempotency_key"], tmp_path / "jobs"
    with closing(replay.ReplayService(target, replay_input=value)) as service:
        job, _ = service.submit(request, key)
        assert job.state == "succeeded" and calls == [1]
        saved = service.artifact(key)
    with closing(replay.ReplayService(target)) as cold:
        assert cold.artifact(key) == saved and calls == [1]
        assert cold.options().configured is False
    # The cold verifier must derive expected origin from the trusted profile/cohort,
    # rather than blessing whatever source hashes the saved protocol says.
    altered = {**compat_case[5], "collector_sha256": "f" * 64}
    monkeypatch.setattr(freezer, "_EVENT_COHORT", altered)
    with pytest.raises(replay.ReplayError, match="artifact_invalid"):
        replay.ReplayService(target)
