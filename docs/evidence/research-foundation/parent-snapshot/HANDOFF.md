# Task178 single fix pass — ready for root covering acceptance

Root's one Task177 review P2 is repaired on f009 research-integration: filesystem
components acquire held O_DIRECTORY|O_NOFOLLOW handles; descendant source reads,
target exclusive creates, mkdir/stat/discovery and child metadata reads use relative
dir_fd I/O. No full-path leaf fallback. Only '/' is the initial anchor. Bound8192
counts held directory/file descriptors and scan duplication; finally closes them.
Before/after dev/inode/mode/UID/GID, named parent membership and role checks bind
every opened object. Target creation uses owned restrictive directories/files.

Planner explicitly accepts the same held object if transiently renamed and fully
restored with matching associations. The proof is actual no-follow acquisition/
relative I/O, not ctime or a continuous kernel namespace lock. The revised race
witness binds actual leaf opens/creates to the intended already-held parent
descriptor; persistent source/target/metadata directory membership changes reject.
No new kernel-lock/watch/inotify/native permission or module exemption is claimed.

Original RED3fail is retained. GREEN37pass then41pass; affected32pass21existing
Windows-only skips2fail is retained: one overly strong rename-rejection assertion,
one ELOOP exception-contract mismatch. Root's later Planner ruling resolves the
former; sanitized ValueError resolves the latter. Fresh receipt-fix5pass verifies
the old receipt-symlink case plus profile/relative-open/FD-bound behavior. Final
coverage43pass/1unchanged real-roundtrip deselection/7.75s. Unchanged real-roundtrip
ran in41pass; all10 execution-interface cases passed in the affected execution.
No full repeated jobs/artifact suite or third structural reviewer was dispatched.
Final lint/format/diff logs are included. One incumbent third-party warning per
pytest phase remains. Each resources receipt retains its exact tested SHA/command.

Windows has no equivalent stdlib handle-relative primitive: before fixture I/O,
UnsupportedSnapshotProfile emits the explicit unsupported profile, and run_next_job
retains an owned failure receipt with that limitation. Earlier3pass38profile/fixture
skips and final-byte3pass0skip actual Windows guard checks are retained. This is an
UNDEPLOYED Windows research Worker availability limitation; approved A target stays
Linux. Existing Windows Job Object code, OpenD, Startup, privileges/policy untouched.
No supported Windows snapshot safety or native runtime qualification is inferred.

Changed files: fixture_snapshot.py, new private _fixture_handles.py, job_runner.py
(only snapshot/metadata/error mapping), test_fixture_snapshot.py and narrow
test_research_job_runner.py prerequisites. Four-argument runner/nine store methods/
manifest/global Lake/registry3baselines/costs/windows/schema/report math remain.
All five source/test paths UNSTAGED; no commit/push/AWS/local bundle/environment/
G1 retry/global Temp access. Root docs/output and old177 raw seal remain untouched.
Source packet and hashes permit root's covering checks; root mirrors iteration.

Same original8,876,772B baseline and24MB cumulative ceiling,5.5MBfoundation+
250KBoperator+2MBfixtures retained. Explicit source/test/evidence/Git/copy allowance
600KB; no reset or deletion. Final resource receipt charges old177 evidence, current
5files/copies, new178 evidence/copies, Git reserve and all owned retained fixtures,
including root Windows boundary roots and short-case reserve. The separately known
524,611,584B private crash capture is unread/not copied/deleted; whole-C original5GB
attribution remains PENDING, not GREEN. Complete G1/G3/native/runtime/image/config/
parent/CID/kernel/advisory/user-loop and full Option A remain unaccepted/ACTIVE.
