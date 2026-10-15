# f009 input-authority route audit

READ-ONLY, 2026-10-14. Root HEADf0093aa6d7853ebad9f70f938fbfae7500b4e1b1.
Source was read from Git blobs, not staged docs. source-pins.json binds Git/blob
SHA256 and actual worktree SHA256 with normalized agreement. No research source
was imported; no runtime/tests/review/AWS/vendor operation occurred.

## Finding and boundary

Application calls choose data, paths and one of THREE fixed strategies, with no
caller source/callback/address/plugin/SQL/pickle API. This conditional source-level
contract relies on A1/A2, not proved decoder internals or binary/source equivalence.

Scope: schema-v1 fixture dataset and JSON job, through parent snapshot, child
baseline and report. In-memory hostile objects/programmatic callers, wider pipeline
APIs and subsequent analysis-provider operations are excluded. Parent roots/env,
_execution/admission provider, runtime.json, image manifest/expected SHA are trusted
configuration, not job fields. analysis_requested/model budgets do not become code
selectors in _child_main. Their separate parent/deployment authority still matters.

## Route matrix

File names below are under src/quantmesh; all are pinned in source-pins.json.
Verdicts concern direct calls under A1/A2, not unproved provider implementation.

| Caller-controlled input | Decoder / allowed type | Authority-consuming downstream API | Direct authority result |
|---|---|---|---|
| job.json / request fields | research/jobs.py Contract extra=forbid/frozen; declared models/enums/numbers/aware dates. JobRecord.model_validate_json in job_runner:315 | ResearchJobRequest.registered_setup; _verify revalidates canonical request digest | Static models/validators; no object_hook, eval/exec, dynamic type import or pickle call here. parameters must be empty. Frozen does not attest code. |
| strategy_id/version | Identifier then strategy_registry.get_strategy:22 | _BASELINES momentum/mean_reversion/risk_parity, version1; digest pins baselines+reports | Only three existing source functions. Wider reports.STRATEGIES do not pass this registry. No import/callback from identifier. |
| interval/universe/cost/window/budget | Six registry intervals, moomoo/internal venues, validated unique symbols; positive finite costs; train>=2/test>=1/step>=test; timeout<=900,memory<=2048MiB,cpu<=1 | Fixed arithmetic/slicing/sorting and OS limit configuration | Numeric control only. universe has min1, no max; windows lack maxima. Source-created sorting lambdas are not caller callbacks. |
| dataset/pins/permission and manifest JSON | DatasetRef; _fixture_pin -> DatasetManifest/SeriesCoverage; fixture/test/schema1, revision/digests, UTC/aware dates, validated intervals/symbols, duplicate series refused | Lake.dataset -> scan_series; typed coverage hashes shards; validate_dataset re-pins after reads | File/value selection only. Digest equality does not prove decoder safety. _snapshot later uses raw json.loads coverage after verification; typed/raw parser equivalence is not established here. |
| layout names/root | data/layout.py dataset/symbol whitelist excludes slash/colon/quote and Windows devices. shards_in only day-pattern/shard-0000.parquet, rejects shard/day links; scan checks directory components; _contained rejects resolved escape/links | _snapshot copies manifest plus covered shards and verifies source/destination | No arbitrary code files selected. Day grammar is lexical, not calendar validation. Private copy is not proof of RO/noexec or stable inode ownership. |
| Parquet bytes / shard paths | manifest.scan_series: default duckdb.connect -> fixed SELECT count/min/max FROM read_parquet(quoted path) -> fetchone | Coverage/freshness comparison and revision gate | SQL structure is fixed; single quotes doubled. No caller SQL program under normal SQL semantics. Native metadata/format decoding happens before bar/model validation. |
| bar columns | Lake.read_bars: default connect -> fixed SELECT * FROM read_parquet(quoted path) -> fetchall; normalize timestamp; InstrumentType enum, Instrument/Bar models; finite/chronological/aligned checks in validate_dataset | OHLCV arithmetic in three weight functions | No Arrow/joblib/pickle API called on this route. Eight-column row destructuring is implicit schema, not physical Parquet type policy. Scalar conversion and absence of executable metadata remain A2. |
| original bytes/private snapshot | _snapshot:115 _verify(source) FIRST, covered reads/copy, cumulative256MiB limit, source re-pin, _verify(destination); run_next_job serializes verified job/runtime | Child _verify -> runtime equality -> report -> _verify again | Parent DuckDB parses before child isolation. Whole files are read BEFORE cumulative copy limit. Job/manifest reads lack explicit byte caps; compressed bytes do not bound expanded rows. |
| validated selector/values | _child_main:322 passes dataset/revision/strategy/interval/universe/windows/costs/fixed digest and explicit ReportRegistry/lake roots | run_baseline_report -> resolve_pin -> Lake.dataset/read_bars -> run_walk_forward | No signals_by_symbol/window_signal_provider passed. Three fixed branches call fixed weights. Wider model/callback branches cannot be reached through registry. |
| report / JSONL data | StrategyReport, deterministic report_id and JSON/CSV paths; JsonlStore uses fixed model.model_validate_json and source-provided key lambda | write_artifacts, ReportRegistry.record/resolve_pin | Plain data serialization, not code restoration. Generic store callback capability is not populated from job JSON. Supplied commit digest avoids current_commit subprocess fallback on this child path. |
| runtime/binding/entry metadata | job_runner.runtime_fingerprint:54 manifest branch -> worker_build.measure_worker_runtime:293; expected hash is separate trusted argument | Actual inventory/source/interpreter/dependencies/loaded origins; runtime.json comparison; admission.verify before start/exit | Job cannot choose manifest argument. Metadata-only fallback explicitly is not full-byte attestation. f009 has no deploy/research_worker entry source: fixed /opt/quantmesh/worker_entry.py command is an image expectation. Legacy literal -B -c startup is not canonical -B-I-S admission. |

## Reachability, not grep inference

Parent: claim -> snapshot/verify -> trusted fingerprint -> serialize -> start.
Child: typed JSON -> verify -> fingerprint equality -> fixed report -> verify ->
receipt. Dataset opening scans ALL canonical series; report resolve/record reopens
the gate. Hash pins additionally detect same-count/range byte changes, after decode.
Both SQL sites were read. write_bars DataFrame/COPY is not reached. research/__init__
eagerly imports drift/features/models/pipelines; Settings() initializes at import.
This broader startup closure/config is trusted despite inaccessible job selectors.

## Trusted upstream assumptions (not proven library facts)

A1: pinned interpreter/JSON/Pydantic decode primitives/static models without arbitrary
object restoration or data-defined callbacks. Only application validators inspected.

A2: pinned DuckDB read_parquet/fetchone/fetchall returns ordinary data, not executable
objects/plugin/native authority. DEFAULT connect has no explicit autoload/install/
external-access policy here. Absence of application LOAD/INSTALL proves no internals.
Validated local paths do not exclude every provider side effect; later Bar validation
cannot undo executable behavior during decode.

A3: authentic providers/config preserve reviewed semantics; data does not exploit
memory corruption. This process-integrity/TCB premise is not established by hashes/GC.

f009 Linux lock declares DuckDB1.5.5, Pydantic2.13.5/core2.46.5/settings2.15.0,
pandas2.3.3,numpy2.5.2. These are declared versions, not observed executing binaries.
Source/runtime metadata cannot satisfy immutable closure/noexec/seccomp/parent chain.

## Concrete remaining gaps and next source slice

G1: accept/prove A1/A2 for the actual pinned providers. Freeze physical/logical
Parquet schema, primitive conversion, metadata and supported controls for extension
load/install/external access. No undocumented DuckDB flag or internals claim here.
G2: qualify parent decoder/provider environment OR byte-pin/copy in parent and
perform content decoding inside the separately admitted child. Child controls do
not cover pre-snapshot parent parsing.
G3: add pre-read JSON/manifest/shard limits and cardinality/expanded-row/nesting
bounds; snapshot256MiB is post-read. This is a bounded-resource gap, not an observed
executable-input dispatch. Establish typed/raw manifest equivalence.
G4: canonical entry/closure/noexec/seccomp/parent rebinding remain unproved. Child
JSON/_verify precede child fingerprint: entry admission must precede those decodes.
No opaque/native gate removal follows this audit.

ONE candidate next source slice for Root to freeze: bounded fixture decoder policy.
Create data/fixture_reader.py with only coverage and bars query roles, bounded
path/schema/row conversion and actual qualified DuckDB1.5.5 constructor policy.
Modify Lake.read_bars and scan_series to consume it; job_runner._snapshot/_child_main
must use pre-read bounds and one normalized manifest representation. Root freezes
explicit limits and G2 ownership before implementation; unspecified policy refuses.
Tests: tests/test_fixture_reader.py and affected test_job_runner.py routes. This
recommendation authorizes no source/store/schema/math/entry changes now.

Needed negatives (none run): unknown strategies/versions/nonempty parameters;
serialized source/callback/pointer/pickle/object metadata; quote/semicolon/URI,
traversal/device/link paths; wrong/nested Parquet schema, hostile extension metadata,
malformed/oversized/expanding input; duplicate/coercive manifests; byte/path changes
during copy; source/namespace/runtime changes; reaching model callback/install APIs.
Require sink/dispatch markers and rejection before the authority-consuming sink.
Positive evidence: all three baselines on valid pinned scalar Parquet; both readers,
parent/child policy on actual canonical providers. Keep software and runtime receipts
separate. Native controls still need actual hostile transient-load/codegen/mprotect/
memfd/SHM/vDSO evidence and independently qualified parent chain.

## Accounting

Only ignored176 artifacts changed; source/tests/gates and172-175 intact. No runtime,
test/source import/review/commit/push/materialization. SAME8,876,772B baseline,
22MB SOFTWARE/full5.5MB foundation/250KB audit reserve; two copies<=40KB.
Whole-C attribution PENDING; exact current frontier/hashes accompany.
