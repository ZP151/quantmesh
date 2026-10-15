# Bounded parent byte snapshot implementation plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. Implement this one complete slice; no per-type native exceptions.

**Goal:** Remove Parquet parsing from the job-owner snapshot path and put child runtime admission ahead of input decoding.

**Architecture:** A research-only snapshot helper checks bounded plain manifest metadata and byte hashes, streams the declared canonical shards into the owned attempt, and verifies the same manifest/export DatasetRef before and after copying. The existing isolated child remains responsible for actual coverage, schema, chronology, numerical and window validation. This slice does not certify the complete native runtime or change shared Lake defaults.

**Tech stack:** Existing Python/Pydantic, standard-library stable file reads and SHA256; existing Windows Job Object/Linux execution contracts.

**Spec:** Approved Option A fixture-only registered baselines, frozen JobStore v1; input-authority audit output/176-worker-input-authority-20261014 in a718, independently checked against root f0093aa6d7853ebad9f70f938fbfae7500b4e1b1 (17 actual source pins).

## Global constraints

- Root source base f0093aa6d7853ebad9f70f938fbfae7500b4e1b1; work in the existing research-integration worktree. Do not modify the three unrelated a718 provenance WIP files.
- Preserve four-argument run_next_job, nine JobStore methods, public v1 job/schema/cost/window/report math and registry's three baselines. No arbitrary code/plugin/SQL/callback/API/model capability.
- Do not change global Lake/manifest readers or numerical functions in this slice. Parent can inspect metadata and bytes only; no Lake.dataset, scan_series, DuckDB, validate_dataset or pin_fixture_dataset calls from _snapshot.
- Manifest limit 256KiB, coverage limit 64, canonical shard limit 4096, per-shard and aggregate snapshot byte limit 256MiB; copy buffer <=512KiB. Bounds must precede reads/large allocations. Snapshot wall deadline min(10 seconds, job timeout), checked between bounded reads and discovery entries. No background lease keeper.
- Reject duplicate JSON keys/nonfinite constants, non-dict metadata, unsafe paths, symlinks/nonregular/hardlinked files and unstable descriptor/name identities. Normalize validated DatasetManifest coverage rather than traversing raw coverage. Require fixture/test, schema1, dataset/revision match and exact manifest/export digests. Preserve canonical export hashing format.
- Copy only declared canonical shards. Repin source and destination bytes; changes or extra canonical files in covered partitions reject. Parent does not claim content/schema/row validation. Actual content validation remains in the child before numerical work and again afterward.
- Child runtime/build fingerprint and bounded runtime receipt read precede JobRecord/input JSON and all Parquet content validation. Bound job/runtime metadata reads to 256KiB, with stable regular-file reads; no gate weakening or default Linux activation.
- Software forecast for source/test files/logs/metadata/Git copies <=400KB. NEW retained SQLite/Parquet/test fixtures have a separate2,000,000B reservation. Explicitly increase ONLY the same cumulative software ceiling22MB to24MB for this bounded fixture verification; original8,876,772B baseline/all failures/copies/full5.5MBfoundation forecast/250KBoperator reserve unchanged. Check the2MB fixture bound before each group; no silent waiver. No local new env/wheels/images/bulk; reuse existing environment, small owned fixture tmp roots and no-bytecode commands. Retain RED/failed outputs. No full hourly suite, commit/push/deploy yet.

## Review focus

1. Malicious or corrupt Parquet bytes must never reach a parent decoder before isolation.
2. Huge manifest/shard, many entries, FIFO/link, mid-copy mutation and a timed-out snapshot fail with sanitized DatasetRejected before child start.
3. Typed/raw manifest ambiguity and same-sized mutation cannot bypass the pinned export digest.
4. Runtime admission rejection must prevent JobRecord/manifest/Parquet decoder markers in the child.
5. Ordinary fixtures still publish the identical numerical result; rejected snapshots retain owned receipts and correct store fencing.

## Task 1: Parent snapshot and child admission ordering

**Files:** Create src/quantmesh/research/fixture_snapshot.py; modify src/quantmesh/research/job_runner.py only snapshot/child ordering and bounded metadata reads; create tests/test_fixture_snapshot.py; narrowly adjust/add tests/test_research_job_runner.py as needed.

**Interfaces:** Consumes JobRecord, DatasetRef, DatasetManifest and canonical layout validation. Produces copy_fixture_snapshot(job: JobRecord, source: Path, destination: Path) -> None. _snapshot delegates to this helper. Existing _verify remains child content authority; do not replace it with metadata-only verification.

- [x] Add real minimal RED tests: parent snapshot of a correctly pinned arbitrary byte shard succeeds without parser calls (decoder tripwire); copied bytes/digests exactly match. A real small file with a test-only reduced maximum refuses before read (no256MB sparse logical allocation); duplicate JSON, symlink/FIFO/hardlink/mutation/shard-count/deadline cases refuse before child start. Test actual digest mismatch. Test-only lower bounds never change production256MiB or grant native permission.
- [x] Watch targeted RED and preserve raw command/output/exit. Implement stable bounded metadata reads, discovery, streaming copy and repins with sanitized failures. Do not use all-file read_bytes for shards.
- [x] Add child ordering RED: rejected runtime fingerprint/receipt prevents job model/input validation markers. Keep real entry signatures/containment; no test-only operational bypass.
- [x] Implement ordering and bounded job/runtime reads. Run targeted tests plus existing research job runner/jobs/artifacts and worker_execution affected files, Ruff and diff whitespace. Existing native tests may require their existing isolated Linux fixtures; do not manufacture native admission or skip failures silently.
- [x] Produce handoff with actual commands/counts, code hashes, changed paths, original source pins, resource delta and remaining G1/G3/complete runtime limitations. Root performs one bounded implementation review before integration.

Ruling: close G2 and child pre-decode ordering now as one independent repair; leave physical Parquet schema/row cardinality and DuckDB policy for the next explicit decoder slice. Reason: ownership of the parser must be fixed before qualifying it. Cost if wrong: bounded fixture rejection or a narrow snapshot revision; no production activation or permission widening.

## Final review / Task178: one association fix pass

Task177 is completed but NOT integrated. Root independently verifies all4 source
hashes/46sealed evidence members and reads actual91pass21Windows-only skips plus
pilot1pass, final44pass, lint/format/diff0. One independent implementation review
finds P2: full-path os.open with leaf O_NOFOLLOW can follow a transient replaced
ancestor which is restored before cached (dev,ino,mode) postchecks. Directory
ctime alone is not a guaranteed association primitive; do not weaken the no-link
boundary or repeat native172-176/type exemptions.

- [x] NEW targeted RED for source and destination ancestor rename/symlink/restore
  around real opening/creation, using only small owned Linux fixture directories.
- [x] Fix this one P2 with held no-follow directory handles and relative traversal,
  file opening, metadata reads and exclusive creation. Root acquisition itself
  must reject symlinks component-wise; bind all opened objects to held handles.
  Keep descriptor count bounded (maximum8192), close all held handles in finally;
  repin and reject unexpected membership/identity/role association changes. No
  arbitrary-root pathname fallback, broad filesystem scan or unbounded fd cache.
- [x] Windows must use an equivalent guaranteed handle-relative association API
  if implemented. If such association cannot be guaranteed by the existing
  platform APIs, fail closed BEFORE fixture I/O with an explicit unsupported
  snapshot profile; no silent full-path fallback or privilege/policy change.
  Keep public4arg JobStore/schema/math and Windows OpenD/GUI/Startup untouched.
  Record any Windows Worker availability limitation explicitly; these new
  research jobs have not been activated/deployed and the approved A target is
  server-side Linux. Existing Windows Job Object implementation stays separate.
- [x] Correct test prerequisites only: root Windows check currently26pass3skip/
  4fail;3fail are WinError1314 symlink setup, not decoder outcomes. Explicitly
  report missing fixture capability rather than treating it as a security pass.
  Same-code short-owned-path destination-inode case passes; long first harness
  rejected before its mutation marker. Preserve both original outputs. Do not
  request Developer Mode/privilege/AutoLogin/execution policy changes or blanket
  skip genuine supported behavior. Use short owned temp roots.
- [x] Targeted RED/GREEN and affected tests after this single fix; root verifies
  covering tests/gates, no second full structural review. Keep complete native
  runtime/G1/G3/parent/kernel admission unaccepted. No commit/push/AWS execution.

Ruling: source/test/evidence/Git/copy allowance for this same repair explicitly
400KB to600KB, within the SAME24MB software ceiling (original baseline/full5.5MB
foundation/250KBoperators/2MBretainedfixtures unchanged). Check actual scope/24MB
frontier before new artifacts; no reset, deletion or silent native waiver. The
known524,611,584B private WSL crash-capture payload from root G1 diagnostics is
separately disclosed, unread/not deleted, outside this source allowance; no
further local G1 native-policy retries. Whole-C original5GB attribution PENDING.

### Task178 acceptance clarification

The final-review P2 concerns I/O following transient ancestor links. Acceptance
requires component-wise no-follow acquisition, held intended directory objects,
relative leaf I/O, and before/after membership, identity and role checks. A
rename of the same already-held directory object followed by complete restoration
need not be detected if I/O never resolves the substituted pathname or symlink.
Do not claim that timestamps guarantee detection of every namespace mutation.
Covering tests must observe the actual parent dir_fd used during source reading,
destination creation and metadata reading, and preserve persistent membership
rejection and descriptor closure. Preserve the initial three REDs and failed
affected run; fix the leaf ELOOP refusal to the sanitized public error contract.
No added kernel-lock guarantee, platform privilege change or native admission.

Root final source acceptance: final46 sealed producer members and5source hashes independently match. Linux covering43/leaf5 and actual Windows unsupported-profile3 checks pass; retained affected run still contains2failures separately corrected. Source integration into draft PR175 is permitted; native/runtime/production and human release gates remain pending.
