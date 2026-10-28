"""Only the sample evidence delta; no native data or old suite selection."""

import base64
import csv
import io
import json
import platform
import re
import zlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from quantmesh.data.objects import ObjectRef, ObjectStore
from quantmesh.research import spy_replay as replay
from tests.native_daily_legacy_fixtures import seed_archive
from tests.test_spy_replay import descriptor_fixture, request_for, synthetic_input
from tests.test_spy_replay_api import BASE, app


def flat_input(*, named=False):
    value = synthetic_input()
    rows = list(csv.reader(io.StringIO(value.bars_csv.decode())))
    for row in rows[1:]:
        row[1:5] = ["100"] * 4
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    raw = stream.getvalue().encode()
    protocol = json.loads(value.protocol_bytes)
    protocol["members"]["normalized-bars.csv"] = ObjectRef(
        digest=replay.digest(raw), byte_length=len(raw), media_type="text/csv"
    ).model_dump()
    protocol_bytes = replay.canonical(protocol)
    value = replace(
        value,
        bars_csv=raw,
        protocol_bytes=protocol_bytes,
        snapshot_digest=replay.digest(b"INTERNAL SYNTHETIC121" + raw + protocol_bytes),
    )
    if named:
        value = replace(
            value, provenance=replay.SampleProvenance(sample_id="F0", sample_version="F0-v1")
        )
    return value


def legacy_root(root):
    """Rehydrate genuine pre-change v1 report/decision bytes, never recompute."""
    bag = json.loads(zlib.decompress(base64.b85decode(_V1_BAG)))
    root.mkdir(parents=True)
    store = ObjectStore(root)
    for name in ("report", "decision"):
        raw = base64.b64decode(bag[name])
        ref = store.put_bytes("application/json", raw)
        original = bag["job"]["report" if name == "report" else "decision_ref"]
        assert ref.digest == original["digest"]
    (root / "jobs.jsonl").write_bytes(replay.canonical(bag["job"]) + b"\n")
    return bag


def test_new_report_v2_has_bound_structural_and_unknown_source_evidence(tmp_path):
    value = flat_input()
    service = replay.ReplayService(tmp_path, replay_input=value)
    try:
        job = seed_archive(service, value, uuid4())
        report = json.loads(service.artifact(job.job_id))
        assert report["schema_version"] == 2
        evidence = report["sample_evidence"]
        assert evidence["snapshot_digest"] == value.snapshot_digest
        assert evidence["protocol_digest"] == replay.digest(value.protocol_bytes)
        assert evidence["quality"] == dict(
            rows=121,
            warmup_sessions=100,
            observation_sessions=21,
            missing_sessions=0,
            duplicate_sessions=0,
            ordered_sessions_match=True,
            ohlcv_checked=True,
            structural_status="PASS",
        )
        assert evidence["timestamp_basis"] == "synthetic_declared"
        assert evidence["times"]["received_at_utc"] == dict(
            value=None, status="not_applicable", reason="synthetic_no_provider_receipt"
        )
        assert evidence["source_facts"]["pit"]["status"] == "not_applicable"
        assert evidence["refs"]["raw_capture"] is None
        assert evidence["refs"]["normalized_bars"]["digest"] == replay.digest(value.bars_csv)
        assert evidence["trial_count"] is None
        assert report["financial_qualification"] == "INSUFFICIENT"
        assert report["paper_allowed"] is False
    finally:
        service.close()


def test_fixed_f0_has_zero_null_semantics_and_costed_buyhold(tmp_path):
    value = flat_input(named=True)
    protocol = json.loads(value.protocol_bytes)
    assert replay.digest(value.bars_csv) == (
        "7e702010cb52a0937898c12fa141a76e10bdd8d98c34394c861edaccb3214d99"
    )
    assert protocol["runtime"] == dict(
        calendar="4.13.2", numpy="2.5.2", pandas="2.3.3", python=platform.python_version()
    )
    assert re.fullmatch(r"3\.13\.[0-9]+", protocol["runtime"]["python"]) is not None
    # The protocol records the Python patch version and the normalizer source
    # hash. Pin the reviewed offline event parser source bytes while accepting
    # this runner's Python patch version; original stored reports are unchanged.
    protocol["runtime"]["python"] = "<python-patch>"
    assert replay.digest(replay.canonical(protocol)) == (
        "ac871ad84cc1ee20808414d5e989dcce7b7d0d7f59474edbd4c038088cf53457"
    )
    assert value.snapshot_digest == replay.digest(
        b"INTERNAL SYNTHETIC121" + value.bars_csv + value.protocol_bytes
    )
    service = replay.ReplayService(tmp_path, replay_input=value)
    try:
        job = seed_archive(service, value, uuid4())
        report = json.loads(service.artifact(job.job_id))
        assert report["sample_evidence"]["sample_id"] == "F0"
        assert report["sample_evidence"]["sample_version"] == "F0-v1"
        assert report["sample_evidence"]["sample_role"] == "fixed_golden"
        bars = value.verified()[1]
        control = replay.engine.calculate(bars, [], bars.index[100], bars.index[-1])
        for scenario in control["scenarios"].values():
            metrics = scenario["strategy"]["metrics"]
            for field in (
                "fills",
                "long_entries",
                "net_profit_usd",
                "total_return",
                "max_drawdown",
                "friction_usd",
                "gross_traded_notional_over_initial_capital",
            ):
                assert metrics[field] == 0
            assert metrics["terminal_equity"] == 100000
            for field in ("naive_sharpe_rf_zero", "sortino_target_zero", "calmar"):
                assert metrics[field] is None
            assert scenario["buyhold"]["metrics"]["friction_usd"] > 0
    finally:
        service.close()


def test_legacy_v1_get_with_b_configured_preserves_original_unknown_and_decision(
    tmp_path, monkeypatch
):
    bag = legacy_root(tmp_path / "jobs")
    monkeypatch.setattr(replay.engine, "calculate", lambda *args: pytest.fail("must not compute"))
    service = replay.ReplayService(tmp_path / "jobs", replay_input=flat_input())
    original_ledger = (tmp_path / "jobs/jobs.jsonl").read_bytes()
    with TestClient(app(service)) as client:
        key = bag["job"]["job_id"]
        response = client.get(BASE + f"/jobs/{key}")
        assert response.status_code == 200
        job = response.json()
        view = job["sample_freshness_view"]
        assert view["evaluated_snapshot_digest"] == bag["job"]["request"]["snapshot_digest"]
        assert view["reason"] == "legacy_sample_role_unknown"
        report_raw = client.get(BASE + f"/jobs/{key}/artifact").content
        assert report_raw == base64.b64decode(bag["report"])
        assert "sample_evidence" not in json.loads(report_raw)
        assert client.get(BASE + f"/jobs/{key}/artifact?kind=decision").content == base64.b64decode(
            bag["decision"]
        )
        assert job["report"] == bag["job"]["report"]
        assert job["decision_ref"] == bag["job"]["decision_ref"]
    assert (tmp_path / "jobs/jobs.jsonl").read_bytes() == original_ledger


def test_new_job_a_cold_with_b_uses_a_evidence_and_never_recomputes(tmp_path, monkeypatch):
    value = flat_input(named=True)
    service = replay.ReplayService(tmp_path, replay_input=value)
    key = uuid4()
    job = seed_archive(service, value, key)
    raw = service.artifact(key)
    body = replay.DecisionRequest(
        request_digest=job.request_digest,
        report_digest=job.report.digest,
        disposition="watch",
        reason="Engineering only",
    )
    decision_key = uuid4()
    decided = service.decide(key, body, decision_key)[0]
    decision_raw = service.artifact(key, "decision")
    service.close()
    monkeypatch.setattr(replay.engine, "calculate", lambda *args: pytest.fail("must not compute"))
    b = replace(synthetic_input(), frozen_at_utc=datetime(2026, 10, 25, tzinfo=UTC))
    cold = replay.ReplayService(tmp_path, replay_input=b)
    try:
        a = cold.read(key)
        assert a.sample_freshness_view.evaluated_snapshot_digest == value.snapshot_digest
        assert (
            json.loads(cold.artifact(key))["sample_evidence"]["frozen_at_utc"]
            == value.frozen_at_utc.isoformat()
        )
        assert cold.artifact(key) == raw and cold.artifact(key, "decision") == decision_raw
        assert cold.submit(request_for(value), key)[0] == decided
        assert cold.decide(key, body, decision_key)[0] == decided
    finally:
        cold.close()


@pytest.mark.parametrize(
    "now,latest,lag",
    [
        ("2026-11-27T18:29:59+00:00", "2026-11-25", 0),
        ("2026-11-27T18:30:00+00:00", "2026-11-27", 1),
        ("2026-11-29T20:00:00+00:00", "2026-11-27", 1),
        ("2026-11-30T21:29:59+00:00", "2026-11-27", 1),
        ("2026-11-30T21:30:00+00:00", "2026-11-30", 2),
    ],
)
def test_freshness_uses_halfday_weekend_and_complete_session_lag(now, latest, lag):
    report = dict(
        schema_version=1,
        snapshot_digest="a" * 64,
        window=dict(
            calendar_version="exchange-calendars:4.13.2:XNYS",
            source_grace_minutes=30,
            score_end="2026-11-25",
        ),
    )
    view = replay.sample_freshness_view(report, "a" * 64, datetime.fromisoformat(now))
    assert view.latest_complete_session == latest
    assert view.lag_complete_sessions == lag
    assert view.applicability == "unknown" and view.reason == "legacy_sample_role_unknown"


@pytest.mark.parametrize(
    "change,reason",
    [
        (dict(calendar_version="UNKNOWN"), "calendar_unavailable"),
        (dict(source_grace_minutes=0), "calendar_unavailable"),
        (dict(score_end="2026-11-30"), "sample_end_after_latest_complete"),
    ],
)
def test_unknown_clock_basis_never_falls_back_to_calendar_days(change, reason):
    report = dict(
        schema_version=1,
        snapshot_digest="a" * 64,
        window=dict(
            calendar_version="exchange-calendars:4.13.2:XNYS",
            source_grace_minutes=30,
            score_end="2026-11-25",
        ),
    )
    report["window"].update(change)
    view = replay.sample_freshness_view(report, "a" * 64, datetime(2026, 11, 29, tzinfo=UTC))
    assert view.lag_complete_sessions is None and view.reason == reason


def test_unknown_artifact_or_identity_yields_no_age():
    now = datetime(2026, 10, 25, tzinfo=UTC)
    assert replay.sample_freshness_view(None, "a" * 64, now).reason == "report_unavailable"
    view = replay.sample_freshness_view(dict(snapshot_digest="b" * 64), "a" * 64, now)
    assert view.lag_complete_sessions is None and view.reason == "input_identity_mismatch"


def test_trusted_operator_loader_retains_safe_receipts_not_paths_or_private_values(tmp_path):
    path, descriptor, approval = descriptor_fixture(tmp_path)
    value = replay.ReplayInput.from_descriptor(path)
    protocol, bars, _ = value.verified()
    evidence = value.evidence(protocol, bars).model_dump(mode="json")
    assert evidence["provider"] == "opend"
    assert evidence["refs"]["freeze"]["digest"] == descriptor["freeze_digest"]
    assert evidence["refs"]["acceptance"] == descriptor["acceptance"]
    assert evidence["times"]["acceptance_reviewed_at_utc"]["value"] == approval["reviewed_at_utc"]
    assert evidence["times"]["available_at_utc"]["status"] == "unknown"
    assert evidence["source_facts"]["pit"]["status"] == "unknown"
    assert evidence["source_facts"]["source_use"]["value"] == "ALLOW_WITH_SCOPE"
    assert str(tmp_path) not in json.dumps(evidence)


def test_api_post_and_get_have_distinct_types_and_read_clock_never_writes(tmp_path, monkeypatch):
    value = flat_input(named=True)
    clock = [datetime(2026, 10, 24, tzinfo=UTC)]
    original, calls = replay.engine.calculate, []

    def count(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(replay.engine, "calculate", count)
    service = replay.ReplayService(tmp_path, replay_input=value, read_clock=lambda: clock[0])
    key = str(uuid4())
    seed_archive(service, value, key)
    with TestClient(app(service)) as client:
        post = client.post(
            BASE + "/jobs", headers={"Idempotency-Key": key}, json=request_for(value).model_dump()
        )
        assert post.status_code == 200 and "sample_freshness_view" not in post.json()
        raw = client.get(BASE + f"/jobs/{key}/artifact").content
        assert json.loads(raw)["schema_version"] == 2
        decision = dict(
            request_digest=post.json()["request_digest"],
            report_digest=post.json()["report"]["digest"],
            disposition="reject",
            reason="No independent opportunities",
        )
        response = client.post(
            BASE + f"/jobs/{key}/decision", json=decision, headers={"Idempotency-Key": str(uuid4())}
        )
        assert response.status_code == 201 and "sample_freshness_view" not in response.json()
        before = (tmp_path / "jobs.jsonl").read_bytes()
        first = client.get(BASE + f"/jobs/{key}").json()
        clock[0] = datetime(2026, 10, 27, tzinfo=UTC)
        second = client.get(BASE + f"/jobs/{key}").json()
        a, b = first["sample_freshness_view"], second["sample_freshness_view"]
        assert a["lag_complete_sessions"] == 3 and b["lag_complete_sessions"] == 4
        assert a["applicability"] == b["applicability"] == "fixed_regression_not_required"
        assert second["report"] == first["report"] and second["decision"] == first["decision"]
        assert client.get(BASE + f"/jobs/{key}/artifact").content == raw
        assert (tmp_path / "jobs.jsonl").read_bytes() == before and calls == []
        schemas = client.get("/openapi.json").json()["paths"]
        assert schemas[BASE + "/jobs/{job_id}"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"].endswith("ReplayJobRead")
        assert schemas[BASE + "/jobs"]["post"]["responses"]["201"]["content"]["application/json"][
            "schema"
        ]["$ref"].endswith("ReplayJob")


def test_foreign_freeze_reference_cannot_be_bound_as_current_sample(tmp_path):
    path, _, _ = descriptor_fixture(tmp_path)
    value = replay.ReplayInput.from_descriptor(path)
    protocol, bars, _ = value.verified()
    foreign = replace(value, snapshot_digest="b" * 64)
    with pytest.raises(ValueError, match="freeze identity"):
        foreign.evidence(protocol, bars)


@pytest.mark.parametrize("window", [None, [], "UNKNOWN"])
def test_malformed_or_unknown_legacy_window_has_unknown_age(window):
    view = replay.sample_freshness_view(
        dict(snapshot_digest="a" * 64, window=window), "a" * 64, datetime(2026, 10, 25, tzinfo=UTC)
    )
    assert view.lag_complete_sessions is None and view.reason == "calendar_unavailable"


def test_evidence_alone_does_not_fill_missing_actual_source_facts():
    value = replace(flat_input(), evidence_kind="reviewed_opend_freeze_v2")
    protocol, bars, _ = value.verified()
    evidence = value.evidence(protocol, bars)
    assert evidence.source_facts.source_use.status == "unknown"
    assert evidence.source_facts.pit.status == "unknown"
    assert evidence.refs.acceptance is None
    assert evidence.check_scope == "structural_bytes_only"
    # This is only internal metadata construction, no real input submission.


def test_synthetic_label_cannot_be_changed_into_rolling_source_evidence():
    value = replace(
        flat_input(), provenance=replay.SampleProvenance(sample_role="rolling_diagnostic")
    )
    protocol, bars, _ = value.verified()
    with pytest.raises(ValueError, match="synthetic is not source qualification"):
        value.evidence(protocol, bars)


def test_v2_evidence_pin_tamper_is_rejected_on_cold_open(tmp_path):
    value = flat_input(named=True)
    service = replay.ReplayService(tmp_path, replay_input=value)
    job = seed_archive(service, value, uuid4())
    report = json.loads(service.artifact(job.job_id))
    service.close()
    report["sample_evidence"]["snapshot_digest"] = "b" * 64
    ref = ObjectStore(tmp_path).put_bytes("application/json", replay.canonical(report))
    path = tmp_path / "jobs.jsonl"
    record = json.loads(path.read_bytes())
    record["report"] = ref.model_dump()
    path.write_bytes(replay.canonical(record) + b"\n")
    with pytest.raises(replay.ReplayError, match="artifact_invalid"):
        replay.ReplayService(tmp_path)


def test_public_sample_receipts_cannot_upgrade_input_or_claim_paper(tmp_path):
    service = replay.ReplayService(tmp_path)
    with TestClient(app(service)) as client:
        response = client.post(
            BASE + "/jobs",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                **request_for(flat_input()).model_dump(),
                "sample_evidence": {
                    "evidence_kind": "reviewed_opend_freeze_v2",
                    "receipt": "a" * 64,
                },
            },
        )
        assert response.status_code == 422 and response.json() == {"detail": "invalid_request"}


# Genuine report/schema1 + bound decision from the prior passing actual process
# test (6830066a-bbaf-42f9-b903-d26177140014), read as inert original bytes.
# Compressed solely to keep this immutable compatibility fixture small.
_V1_BAG = (
    b"c-rlKTXU;O*5zNBIM01%xY|}l^n-079TZL&+2{f<6%yzMNLC+T1a$O&pS2Uomar|8WlEpvm<LClvNIvsx!1mAuH5"
    b"<WAHl?5JS^^4KmPbJNjssx?9YRCKN>16$qeroEWAvug_N*sDYg3DjTPP}mUF+ct~H4{EU}tbBXhA?c<p{T8d~eIq"
    b"EAOkU#Grac$s*PpIQU=(F&R5-AR%+Fg7=X&fIQBkFFEUt){Pg121M7lk(@pncr??qv0){r7i45C-nyF*j2lWo9oW"
    b"M#!6>88g%h{Q?Z+D!<w$*-pLDh*;?K>-P8;5+%Vd(RE}8aCRXNSjF%hc@ctWr*^tJH^*nAhqR}9TeU+Zo3Ej}otj"
    b"v{JbCxp2ki8{Kyg@%=iYZ%z9=-wZ8sPU$E4G^Pk}2NObNVs9al_h7vBG%iDxJBTvCL}rR2JUG^gSd`Uuis%JZ{^4"
    b"#Tz8gep`;mtL_Z4dYIgq59X>9<D1jqU`+VFc5CUidz!0Qk+<wDz2;11%~r%5LuO8E;W=i;!ft9Q#>RGfnHTzs<@A"
    b"?U7(q6-Ash5GD~m85SGPj+Q@ZkYOi3{4XNT|W#CF@<xM62uW%%Z1Ja?Ta!MvrcZR(gWm1SMcbKKN&AcJt0xY<m?*"
    b"M|7F<_)Z+8=5J;J#&{{Y%RO0<@7ZEKE=BC2J(EUda=K<@_7vne7E)F4zIFNyCDsg+qI`)OxNa_8M+!%S_{ZKVM_}"
    b"#_9b`FTCz62DZ5=-OH*ewp0*d_+jXzqnKNf5dxK8wH9HuOp}G#+xS0>Rv@o~b4C7u*yZ`*>kAM6K@5ev>`1cS0ez"
    b"}e(kCWif(Ib>!k(9Havh-8Y9qH^3S^q=Q{<o?tvU1^}kN<lzI@(k@mt|R{rmukd_vhU-S(P<uzuTYDBt_$?Bu~zP"
    b"rJrZ2Hu<SdM$*sm=%Vp+bUxC~8<XioRW<6hcv#;*EFN<J|DJ>s|1tl>KNkUhb9SLh(%ISQ=XgAt{?wFd<L9^`sXq"
    b"hdOg=xyt0kEpv;KYmc<<lGe+G-$<bek3kI&WfGhMn+)R8{*<;f&a$GSdIbYGH3dZ13U##Eh7C;DV6Ns@nd)|mR^k"
    b"&j{N=ZZGLL-Fkod|1uN^CZ4sFDI+V|8>8LQ~tO0{qM)u*PUIArorUG_k-zp8eE)9av;mPERQFOs%XmjNNVWn6a&("
    b"yXN|K94FkG3Z>SpnM-J3L=a2l?6CU>Z%*n+VP#;5zT4OY7$Y-h|jT;w@b5*;ToGH3GIlGYk3r$u1vx|#~KOHNIrm"
    b"N%W<SaPX^$R@n!Jki-qd%V~zw;TD@vGHn{V=~j7`r+e%OhFwC)0CnG@43*uWHjX2)c1DP5tvxBN&h53w<)41d0#A"
    b"k5tJ&mm0D^)-Z@4|Jj@U-;*gR&M2PU|6V-Kmw5iee5B}S7|l3+octM2R<p<Xk3V!>rRm>}0neX6l@v^<B#rgax#9"
    b"=vMdJ)JE(c>@QO6frL)In@{9d1qClEnHA8B~43@M#Y@$}^+Sd9LBOxF`UZ?s;=3x7m<^?yQ|MT~Ls`}h6tKmGdv4"
    b"OUNa{Er{g#cH(j7o+&ke?5)j#dO;P{Y~qx*J_#9reQgF_JW{B^UweODmqm?QzUr|LwFXb=cDtnGMYBzAW#&wAt~B"
    b"92B<gG33NBOm?~(kO)g|@9H?63Y<zw``YWnFT2FreIf~=^%>>=1qxfO6)5nsM*MQnR*;k;upUQr#+%&+y1*?CLR-"
    b"X!zP%9GL!;|mh+cB;G`0=z3KC`^%Y6AxQKd+O|10Z*hgux&|5EMU;7v>rN-O#!pDxG+|wC=})Rys;|zrR`s?bgFk"
    b"?Pnew7jqB{AlN{lu^z8(V>nuJvZ*_~jS)~~zS@8ED0m4kAIzmZpTGh8%a-c38!EkvU6ZryXTE}WuNc~y37#c+!_M"
    b"PqpwAJs#Qw0q4t_=CK>53<PXGssaZm9+DHwJr*w{?(xZ}l`G2THVGsE?{x$Gbq>B-xF%ag(UdECZ$Ru2fgTI(@AH"
    b"-5z5thwKAA)vd}hl=$u8eVPqxR>61{L6|lCN2}aM`3r`2993lW8pt$%I+wTYa!qxXKro~h&{q#KeEuIAS@aUy)^>"
    b"HClBA_V!T_KJkhrx08~bUTa5d5iZQIYT(32f>E5?TIs%@}O?WBe-H@e+Z?q(QCw;qQ-)Xwl?8@l#i0A*t?-JHD`1"
    b"8k*(NOKg!LNQwGQV-~UX0snM$|{L9eOtXAlOQIuoQZOSaAoP2l}3Tj^=ZkTRfKnBMM{?yzu#nXs-7H=Z$?QK^_$3"
    b"-J(wrQ-H&U(!*AN=B^S;lYS!{x8seEz#DV3#9U?`WavU?Mre<K24n2uTX!<POc@1G%UkGakAlS%a#!#z`VE4@Z6N"
    b"(3M-MuS?~X_>Zn*B<u7hP9c>_Hfs#o*TzWj$RndUv0*`?01D1SH2>8i7K)oozDZNI|<bU)3Xt;eME-tboTm)mxD4"
    b"&(&cb`#t2b;bkKo`U&7aBs!Xhq=2<Vm`j>4g$g!`jh@gn$7h%UO|r^5G20$y(xWfKz)=xB`wMHF8LdExLc791HVp"
    b"`+SmEJ@wcVFjKiJX*|y))U-qv4QacKUNv^hINWd7902kx+d1B!zc;B+M7?a#+epc2!o*Da?Gw8U^<vj?V$bP*4y^"
    b"OwBLZ6j4q;G6BZhk$GZf@Lxg>Q+cu9B?%Uso}Gr-ylhjd|emS7vDMCR?0tUgVqGwRf>%5mxr~Q$Yd+o!XP(zU(oE"
    b"cu%h>u>qd$a(#q6)DLXLw!MsJKk&J*@@GFmZx8G!+98SXG3E%EGbss@fJfP?$TnElC$$Y)b+&;a33JQZ2Kkt6utN"
    b"HoaT&u7Bl$F|vJLWSZ9`O<ZLpd%-MTAl8{A{IK}K?%GKXcDD+S4YVmW3-wqbTk+mNyA%4~ydH)m35+mIf!4c*jkc"
    b"2(w}UD(SQqC9I+jcu?`7B?6h;3cWfHn^IVv9h*7J7ybTZ-IqNnPskIH5uXuQ?AA~u+7PAgL4VInAO>aY^Jb9S=$g"
    b"Dvkj@`FxXz$2<R>1kqo&1x^3X!Yn;k9(Bkx_!ni?0Y?_p`4GB9MHy8?j61$0**YRN+jEZDyo>sPt%47?>*WHws?c"
    b"FiiUTT&z!+#N%IVNH<*pV;W1#SoB)7k~UD!Y)-=7n80W^l}7b^$+K{1_>1pwNbcb^T?Z_Nq&#^J&$^yN;nDjw<QX"
    b"jO>U{)8NB0#0qJ?QNs{F7**-6dRpC$s?%M>{}gAH)7|b7-JNL`#baSlV%ZFHhP=2U-L<bzsk=s6o$fN#cFN{z#<5"
    b"%tah<E?`GiS!0(#s{E7D#4q`K>{%5>Li`daB+%{i8<%@8k;k8~A_HqOJI4tZA-GdL%W84|0qTn)Y_^ULOH$<bV`="
    b"_VG>txfpK9&L<oDp=#?-^<dI+6K8g+u*8JST<KPw4=5GxiH30_6At+iA<qXV;c<Vw6?*m&NgI_L)l!-IhL!<BrCg"
    b"wt?BCcH~b}Hv#N46r*~4@U{{u_8SqElvbkD%G*@df9kv&?0dfs_jHXv*8@?Lz;yaO}`xxgDoeeK5(^<p{Dt^DUKL"
    b";|EkzZ&mE9|X>#u2^sHN;{>!h)=Nw3d^Wh{rac>ugle*{jCzj%-z5B8>U@9_@U*)MY$lJ%Mc;s^0S$&l=(X^KT`)"
    b"#U#pitPJ{*Q4VE77Ywf39-?X3rzebA;cHONOtTSRvXDvKwhR);fZ7=NJwwdzCzO-o@4$U8&F#<IIUcH3?5mtCxBJ"
    b"$2=IwSG46P&fy!dzYy?$3GVqd2H;TX2HLHo-oYz3cBk`W_6vWy?bzxaOh!F=!SYwP$nmF%>qcAhczY4EEv_c&2df"
    b"9Cd#+wO+q4T+$qukky=!^<8y#+lxP&|{}Zxz7D)Xh~xgzDA*b{cM;;@(znEa~0$Ruy>IT-GLu4kl!<mEx~&N_&S~"
    b"DnA<nT=e(uCZ=~)ph{kF_dit2_-X-nlN@O!%_H~<nmh0|(8bFp9uS%Hp<3{EUt?WfE^xS0&GVf2hUaqcU==O4`u4"
    b"8|BK{gNb-KD(?mC?R&)5m!6|BD?CuF|pMt>GtSUm^Y6!|<z*-&l9=?)hhs4dy_99;#cr(Q2Gwtj{^#Xno4aI62Q@"
    b"lsjcyJ}ZmxAiddt&g~DzEwA%=I<TP!wk2o-yMy>?%O@ycl-r7ZKEj?KC%<$1obw?LY(Q>Lw*EFy8mX_|5~lUf=7~"
    b"5ATRkKG!nlmhJi<FzLZ%_d)!sMa86*p`+j-3M8ao{LYO5JN*-lsD^M!B5?-6%g<vfv?^!)OLlR-q&v1&<(Nj~$Bc"
    b"{}xuzuwThy?o6q;rL#)V8?W68@H9@9dt_i@%Lgbldq3^%SMX$0ybw~fA9?W3$NYU`h~URuljFghIj^c@h{4(;D=U"
    b"M&!jg6AF(GV^F28|mWzL)#k4Os$X<^Xd4suF=cL{B`MbF36LHpC0tdtiig$Jra)aHUJ+aK!U*mY=EiU52{x3Li3>"
    b"ET1uKtPxrb?Kf#*^1?z)oTQR#)`x<bN~526TBvI0iN%vhnoqfhrQa?RZ3a-1V*=Rk!||&o%%3@jbUAYrmhyym>5f"
    b"bYD0r<P#ggd_w0jeRlb3uZS3(eq?`G)x0N_y~)+O@X=9f-<9CxU|zYO<@T1y)Gz)>f)19*Df|+9!(Ux*h*JKY&FD"
    b"qOR%ogp@<yuL8{Uvi-k0&4z02$<uOW*N7evG@+mJtFrS{$Z6L4|_Wn10eT4Lw>y=7!89p{WtjKK3?#iI4dkjHhOt"
    b"u?46I3r(OYY?;zv+DR{;Y{Oe=$Y|3r{U<{n!B+=7y8SHtEcgQm*6x&-#_O&eUZ~()4o-c4tBiguEM!)@AIAX3i(b"
    b"X2YPq%bv{lnwVSR^oDm+&SEIMuN%c0ntdi>_@%8gEdix0%2QhX&ZsO{NuFNXZTl-{sTQwJ_r?IeGQg3I+^p?0yGW"
    b"-~1>m%=Uvod?aC1jiPx=ttCv`U^6=jE1??Pok317oDagENfX&?=BE-?L<=)!XX!C7M2RA+wxpoy%jgO<=br$QChJ"
    b"q*x*Bc;<gS4y%NRQ#uZ-nukOCxJkJ<%t(&%^O`fnwO!Z-hByqeaombz+dHjn)9N@*R@U8=lx=!kwwDRZW+`!jA!C"
    b"UlpZI#Lz;UXaELPxiIjfN4<R^BySRr9Y_kxKxb_x3p-E|__ChlWJHrGl|YIF4pIZlerIZkD4?q?hv6S*GZx{z`+*"
    b"xhEYBD*j<rCms>Tl=DYMPDsx7e3?QNR<B~cYu#1-fk5+L?s*?F}qM92Zv>@Y%R*!1!{MMBSQRN$d_VW;tO<@iej;"
    b"ZElz0{45>Q1&{bI0D`^+}qx>e~qA||Hp@I^`afzz23l2M}U8rtN%#f|nkV@Kx&-gb~=p-Y)IWU;PKFHPB1w%TmU8"
    b"s<M6ZUjgZcU8G6(8FL*a3>gvM!yUO3ChWxm92ntdr(wMuqW$FI!p394$PSqs=nD*BAEiU#413+S{%uN6U5T3wD9d"
    b"Z*+Bbry-^><PYpYTHV<+<o?K6Z^D_x-g26Ve?vA?kblEAu-^*V1Ly^<^L%j+?NyHs_R#vYS1IHDWWyM*E8q_Fr(n"
    b">6ZCJ<nZe^_S+6oU_9is1-kl$p$31Uw(wWz2Ot!Hw6O^~7uY##AH43)1FI+Vl1wxwMEAILV63@qZ@+-Wj&Qq8}Sb"
    b"0Z$!w^6i@ywAC~e1Gm<xEmkXoZ{cn_kF$SXT;+e5#K=RWZtl&<a`6p{~?~x5`TMm;p4pc0DZ^t$=8pZo@RZWgQKy"
    b"`P>*nMcAN}4i%W6)9%tc_p92}U8&96xh{vm2=q9&w$&ORw(Vnz&`y41G_8IdU7&7D;`>TNVveN=Lik=H>$BNg_xh"
    b"AlIu+83dvV@MO#LMVC(Rpmf&sjl_h&P+#G`HiwI?vuRmR`9`Gs$+0Cty0UUVS~^Pe0)Q<OQmp{T1e6*_iJ1{FVPh"
    b"?=zpEuZUx)3>N7vmup6CgX{PALqDkHQM57p?cVzDoNM#SOHdDS`(8Z|ns>4*{JUTIN5s!np#!`am^+L<nX?vgBqV"
    b">?ig@f$u2#tVoC3by;ywFR;H%Zx|6V);K4x(HQiJ8yCcmxok;ji$bDAgk%FPy6Q?l>d8Wy}p3Kf+LI2Mk_BinXw<"
    b"0G<ZN-y7M%ku}=?A8;;$nAF7J@Jxp(-9w2PG+zTviByQ?CHewvdOQA%Pcv-&fR;mBE7t#Ig0oF67+lyTaoMfLMjy"
    b"#*>|1BaL741#B+g7VE8@fxh#TVd=Ebo<#lYhUDeC-!}d6}Ph>Op_1kKi(%;R2;hdi4C4YA@X0kb7iu099*R4Sx;-"
    b"v2Bv7hs;zCqm@VHu|tayUqi{0!-r>(&s@K(o2c<OLVMOWhheADi$!<QMsNC5-Q*z3}SR1DeFUpS`QYf^};&jE{UC"
    b"<*usbxQOkHZ&J60_C1W`fUDc=rq=aGJdR$KJPyT5`P_cFZVjE+v*}Du=q5b3y89k=Yea2>T^+wG<F%*C*@jQ*))*"
    b"4Yx(aj{xrwXM&o`-CBWfEe<jHh3ipk5_hEI4hp-H-nyp_>eX=?vX>edL_hAO!-4sx99lD6SES0<x<8OF~rbY;6~="
    b"vCFUvQHN`ymB0>u?-4xx~!ya_^fV?1erp{W(HrG<Z`P(cXM4jjqX-ow<baER7!V`uEoMWVxDxqCWL?U+CUYZ@n<L"
    b"2-D>OBTqfmo*Vr7@U0$mOu^6wn#Ovr)RiEO7G4CtSp&GwNH5M<+`8CHlT3aR0DQK^0#{Ha4>y(w$1?rvHHdI-=hW"
    b"1lR*@lEIj@AW&e2IgDm@Ml_bXK~8dTf={t`W5j)y2GYF3HtO+J?_+*Qk7N+`-uCoPX1ozDeyGQQJ`AJ{V*|``)E&"
    b"!)Lr1<bG5`kS?yEIzj38s9htdyH)aL5I=QG=4+qvW@ul?m8mu~Y?wrK8^1~I8bRGPvI@B!D(7~T(%sK$*K{?W3sb"
    b"EHiqV|zH>q7C=+~TXb^HUW<5MnQ`?PiqWCh)wrHIXR&Rbl3kJ>e&wxL4q3~Z%QGGF_YJEJgXh8WMJ{b-r;;%`#BM"
    b"$|Sa74kdi+<r;h@LBB|2D?Bt;Hmz*pH)^{<+S-)wY6))sARroZjS0M?bSPU7R66(Zih>qg)F1H%9nN5iDV1oBzyZ"
    b"RW8-+ufl74uqxT-zV6L}xzEOZrLwi7U=7G-eDK^Cuq4}NoG#PPZkP9X(>yloplyC0wX=o3aYVs&7qg<c%BWF6hJK"
    b")pMzIu8S!XDDz4Ap+2m?>}b*5|egwNtL&pTidp#s@el{2hI}@9W3VB0k0%HsRS_S+T$J@_p~sOAVX#xShOkYhLVD"
    b"yyNSb#PyST{j6n>juCAS)!Wp?crlizan8LVoAVqj`{_`LpXfq5icjeK@$dPV#<`%{COw(X4UF1x7PK3rTRFEwzR<"
    b"0^ozAd?pGS1e#NubXSc;sV_7NZOo)v7!6U}jsOXJ<UVLsdM<u!0r$g<r}1EodWfC9&fo~zFx^LWb_*?4`}lK7>r4"
    b"6p4(=hSU})^$efYTQnLSkK0Bp>O1iUTkL~&ZBWt$dNAJgKTI`k5SyH{be4F1HHc1$cDfA%fGFz4c<k*c=2If8@fk"
    b"Ev-dg0Sy%o}b#3-I2UPb2cF|h<+qy2i7R&3sMlUs3O8CzI>bf>mGwCLT?f=VlZQj?>zsjd66DQ?-8uBOB^B7~r_h"
    b"eiz;8XVXX6Hlsg^Wv&?y!1-oOV3KN8-34Pf_7x_To{_GnZgDbG{mnPjp}*UV5;f@YQ_Ia~sBMBBKAE4Qocc))Q<Y"
    b"Y*R1?1{OZAM`mpPf1R8E(K<I0`M3i;&AHxxD}U#eBh^jcw^zJ|+}=L2`6)-r;`bxH_{^lLx&U82(_``cYClHZo&)"
    b"*2@1APT_<B3u|GADH-A5+5`c#V_xgv424W*)b7TFhb4<X&Hw8jnTCvig-U#xMHUFPQ}n{<AipZohRHEx7tTOoHRr"
    b"TS<kW&0U-C&}x2nj6c>_lqi$t$b41-c`wqGL(|CRgTIQ@e%QMNT$e-GmO8Yx>sN2?Q~QAec|3ZaQ4w%X>3y=CrU-"
    b"k_pU#C%ZWO6eln7fvm>u3z8RxCr=)V6s4}vRP9)pP>)RlE@0OJ9@%lC#bI3!t`8wkCs2bURnX@A#+bZkZAWml`W&"
    b"2ruo1SdZdEd;S*e=Ust19XN7^jqNrS)xCW|oufXZ3BeOS(5AwZbm#6KyJ~GgwJ|8zI?N$kmyt`PxJo*?z{=@iWVz"
    b"bt$@2#!V`#5ps8;yrEj24%G(KY3-{--tZ|;2R4CfGtv6F#5ojq70GsSO4(Lf+lJPZO3L<=+BO!&2KeDMubQ)}>Vv"
    b"2!ifwbw%3X#0r?6WxCo`m@{HJEVPfQ#rma*Mg>?&ldolv$F*R?TA=47ANwb3komjdyrh+D?=Z&KGrOtxu-+^6ueW"
    b"KL!%M`cU*S7#BO0jB+8@{w9awL#KT%C^FLr6kLl$t7j09+xexd(qiy;-b@;Husy<v=NEFs=QMQv3^)GCv%SFWW;x"
    b"(y-3>2_TkU?y_6NnwtGt1R>;XA{$k0T>{Ct-#Rt8dOP0-)3Tix8!pRYeznrMTySjSm))sy7E-AV@m0|-|<M-5t@M"
    b"RU%5UYTLu2D_N8;p&mC%8)r_=QaAp3`@@H?t=T`X|P{q4QM4q39w8qjOfh?^VktG=NX44`s>}gHv6Q!&)|%@adGF"
    b"x^(9@a!Wevd%(S+nv`hA=)5_t`>V+BH<Wk&*KlvHwTwCb*SR;ePM3bnz1i*mQJohS?sI0~R~CPzjt%Wq_td>QTPj"
    b"~`sick#uhE^^{M>67I(~`&@_Mfy)v?KV{h4r<?b*q{P{*dHVLs@-#tpp}GNtp(f1Q7`kN1NbHE%Hbl-H`+<K-OQ?"
    b"Ni_rY~!u`yXpCd{GN~bH!|HL_R7C8((3p(tRnsm-_I82-+bgJ|GR707-T=F4%lC<Ve^8U_jpRY&#Ro$EkENxPB%`"
    b"eyht}!axfjrjVbrP7{{-zA6d3C*nwx*<!PX_AivIr-py-!E&IgJ+W-f1vhBGpwpJeLr6O;LBLjOydJA8aJdnK_E3"
    b"oyg2KT|7-!tf}$>!hWJRELEZ-!T}wR8Pu=<>Z6dVYS#)jfP|gY%Q{F8m&IKH#zOw(gEK{eYJPdl&P&<_`ak_IMuY"
    b"uRGW*=-Uy~t}w@OUayDjbnsfY%7LF;(6~Fx{66%ng{5>e&*>~YXCA{E>2B!3_qv)3nYsgW!|g8gEWc~k&|HOOZg>"
    b"^igVvm%OB>LhuD9IUD)O1X;eWZW9JT4*RF}_{)$S$U0PU9M#&vqC>$s{n=!Y)7JM7QhFo>-t-A}>j4r2IfS9VD!L"
    b"MtR@q{aEMh@+gIWVH>Q(Z2eM;)ed#|61`-d0gkdlzb|EcONz}Ccm>B4d)a$#yKC2?1mnW1|*jjzq1m*3t#NVqSJ9"
    b"=tA87LovswOoS4tidOW;(@CGvJ#EyR!LB5zb?!W0AFLbiCa6`y>3BRHksvE-gg;C<QVLL*mQ=DOCc(Q|BK<Pu)US"
    b"zk?k7~NNd-%TFh1X<~?RX0-3+6Q5(Xz3CZ|3#xwmwL)md2yI#IqNY#FnmpGobom?9l@z_*nv~Puk4SLqOLa$(O&x"
    b"4)MdHr^dk8JSIM!NwEohKjs7aqOZ)hx1RhWeeRu`ZRqs%Rf^c=!E94Z{)kwZ>^FSwFZc||{f6S?XugKMd?tGfU7W"
    b"$*E8ZY^_S+<{F8)8BBi1IHx^}aN*?4&|8}U0KuPAonZ5*lLn20URUt9ibyS3QfA3Ebaymq{#xFfe&8qJB3^V6>WZ"
    b"_nu4ydQ99r&kB{_V9h0H?U-S9{k}fw>j`f?befbeMNVRuH6;qy+vl*qA}9nQt$2xF%rg(XHg!3XWj#^PbAZ>(t!L"
    b")X5AULH`iCNBMoihJj}?h-0bYi^`2e1yF$*%If2ixXL)S?tN-K<J*un4*M)8tS50m|+cZD@l-`Z8WWL&e#Je_J*0"
    b"J>rT@LX){2j67(4TGdoek_BWPLFsyMXV`@^6me!>-mmW@>ZZ@)O1jT@Dc6VJwS+yjoYCe*QhrUM}Y@e0Gd>nD6ck"
    b"&r|SjUYjo0mseT2!@e}4_>kiEYi%*id7B&JNJGvKV>LL;@mDlwx6hE_1Lr|vUV_}VF7k6My$#igaGn0r%~~;J0Q="
    b"LEJ=iigyG-!=h$%hE9=I8CD6K(%N&d*qT*V%EA?$w$Y)SlVSeu{OPASJHxgNf+r@^i*V4tWqs+8L|1J(}qiq3C1u"
    b"u08%j2uJ8`(Qg;p-s8G!tn1o;w=xp7ua?z*q5H-HGSf|^Y;bBxrN=x?>HnGBBxBbuYY2x#<^GiubAY<eFUR=M5(5"
    b"8`?j*eQM>=>_Ia(zY?sgRdrOzC4dS?GswcQ-hcF%s_Ovx;4#i5YYPDOiL01v%sN})E+nj@Q1$hQ@dvLpO>3qzf58"
    b"u&EUE+o-M#kDyJ32~S1$hy^m*;F`Biao$_bsh#s5F*{ktH`R=CrLIa;`JX1O5Eo{&%sx$2aERA0K=Va-BK86L?g5"
    b"kEDaNHiI}Jv-#Q<dt%|*b>i6JvQh|#w=$1yw{;Q6T(4W{&Q1;t-RtqS;l0199&!e2XXE2Z8$J>G>)pw(<65yZeug"
    b"mBQagrt`aJGLoZ6r`VtyE-ck!)p4>8yFTdzjk-m0)^@ds@kcE+;TwlC)f;<ubf>v~t;<t4vC{*TygU{Tynam5O8$"
    b"=qMOaI|-FoANcSMdw9k`+uVtg};->0)6=OIdn3JZw9Zj^0Rx1?!CPU&9gmO0>9*ETT)@18Ea8&e81s8t$UK$GufI"
    b"C+9oW!&-U8B<WcYNyrdmJXirv%&0w=t;$+jhdH`KOKEK+o&%Ekb9;fZiV-@=6D)4Jcf9ekR^LFHeh>`kqr!}oh;b"
    b"*}2eHw_>^$*$_cs_e=yEo5o^MT%ufAK0S_39b6IHWk4)@3}k|3G(S?{bF!8BEYPZ%blg+g1b<cceo#zyyu6UlJ2}"
    b"TM<miJAO<JFrf%wLJ`M=TN6wK0+<NIF_G2-6LzaSChV3lCbW8B!VvHihPa<_YT_rHPI*jFTQN**?|}LCm`Iph8WY"
    b"r35EFU*k{Vz_62OEcj)`tfFwqylL|+&a)?Ga?A>bzxaX(?y#ZTx0n9#*B5!C||;Z=D|P+Kuf<ohJw9}_7npHEO*K"
    b"}_W5SHC|d%(OfvsI4F-@_mdNV8Ro?geQy%s~)jaYL$<jsI4d_)S6&I6TpNfj)_@KFcAx2A{NF(E!JZ3Q`%4DZACD"
    b"l?9LN@b4<`rSwFFDD}o7kcV6q8V}gFHl9<@G6~P4QPg)O5SgrDyuv)^HkZOVnSpXBVI3{{E!Ngnu6LVoq*w^*Ige"
    b"~AFY;ixK*8>yAraUI7tso|x%X(nKX_dzWwH3oe!s-z_B`hwD32G~diTwOl4KN|#Ck$~v;nc)WIGz9|JYh`KBFCn2"
    b"%H=U3m}8Uvs5QZaCV&Y|922v8U?S|4$3)l>#YD>Lfr*rr$3)76F=1x)z=SE4$Al>fV<PO<1QUG$O!S2@VbvpcO0D"
    b"v-6SWn^gi;es=mMC~#W4}p0~6U*c}!$iqL|2Pv1gYGti`6nYq4rg)?!tGwOCbrE!MBeS}cvTY(BAVD}sr1SBvTUW"
    b"1@6Ek+&7agjy3!Xabnf#4$0e2_|9zOvJ*NsKuULDkY`QPvmU{F=1@#fe9lkj|plkh>5($&-cfKb6Xx0&aEgW6007"
    b"uQ(~2mof1npb~5CeU_ueVgd&a!w<eef1TYbZV<N2uCQ<=Ek&62XvnGDROv+=zOoTBJ8uh?L>9ts2d@VMu$y#hGuo"
    b"jyNuf?i0S&LN#)?!uhwOGF<Yq2y=0Y4E6`-!wJe!>>;6SlaY&}xDST>ulhI3}WcV50O|tS`P6o7QG6HWOHj&BWJY"
    b"Ssm75HT;y#vA1nSFfqeV9dhiMK#hW#aE$`{x*jzO_&7^qV%t^(6IxAb6lel93N-N=1+$veD3}S<D3}S?DB${&)&d"
    b"iy*J8JA1u;>JwOCD{Mu8??qhMB(8U-_f8U-`q8U^-sJ!%y2amoUikcBak)dUlg045}HOmu642?0Oh2>XeoE`Gum@"
    b"DsMUpU`T830(jax;Q4HdSIe-je?nQjRO0+9yJR1ILqe~qBRP%n$#%J1lD3T@wM1lP1a&(0=(FnFfW$$rw+VWKF+v"
    b"2CIor0T1|MdG)`3j6RJ2S{F-25E`W)-FedDJ_=!xwPh{eLq84khx<I{HUA$gwRFitKG|sX)_O`7EChnw7EplucXW"
    b"1M(Z!3Zc(x0p*n2-c8A&Fz6TN6yo1u!ue#zZar#9jFs1>3fwn9%EiiPAL+bnzMmQB7(TL;^JmBH<bZ_FX+{6wo-!"
    b"*0R~Q6~u%g)dUl=048K{O!R7k2~PkMo-ih?MNKdv3t&PxcB(~<0$rd+fi7O7AgW1?f+)X#rYt5xVLy@9#80GUYuR"
    b"ku3Sz=c>wyU~D~|~?6UIcyYJ!Pd0ZiNqW5TLOK9O4G^NG|F&L>Q{CYTWL6Q;PI2<ze}VgXFV!kDn@;U`Mp-L-8ih"
    b">1Gf-9>lEmR*b8wH3ew-HBI+wOBsRl54TMw&gKFcM{iOEtZe7q@UQe6~F}7AGs!&Py{fch-1R72_^yoOa#K1r~%)"
    b"JkFzA-Y1dX16Ix9$p$lL_7so_Y4@@`$e!>y<6G=_{L|I<!uB{*@>cETT<CMx{LXa2B^`~1CO!NgX(HF)<4fsy^IO"
    b"Fn|5aT;>{ZVRy2?0N0i2DhrCVrwUFLu{f3=^e!vHTu-#d^l?rZk@)JSQBhop`8P66X8u8tLJ@WM;S?AKvdxbMp4y"
    b">is)S`P%WpU9a8!J}>wB9^CD^DE9G-eY8TK<js2=v(P8^EeCf4UKjiHihbU^$1c7nye#y|IlBjUlNG-wbc=n|Vjs"
    b"IWwnJIJ+)HzCH_5?!-0j)axA%4&-2HJ^>@zF&(F=VNc3tSh&o;fS`+iU-yZ9c*E%s51eeB|ULbK4v%nE%{>rJ0tv"
    b"5!*hV;9Gk9n7ivM%HOj*8VoPds~<9pf=leu}@U!V{8h25`N#zL9L%|v5#ErV-?5d_=P@Z@jdAwe*B`W)i<(Ei?a5"
    b"&oYc2<6Ao%G6yNhk*6cvmbdK^+2D73K(TX;NpS@fZ`}l=EhqC79xb6yl4sD25v?2WL&ULZRoA+qNK6ddvhc-kj+7"
    b"Ql@F23hbueG9H^FBqng|kARf~?=z>u6hR^ewM$zt7>=qM{Aai#CLFPl|mGZO98R<6s}VIJQF@q8Dul^|6cZ35)MB"
    b"(?Xy0P~W2M`GdFn9tUgRZ{8CX`W*Pid~I<5dw4FqFYDKJvxBvhMX`@x?4uR?*v0oa#rGWObsnc)7yI;zeUxIKH}8"
    b"R7=W$3w_Lmep2dO)t|H|v}sxNs%wxAdg@sx`A<1rXs6=RjX{pVorFJ;+pHL?J)+u?pi9*aze(m#Lv=l=oo=tA8"
)
