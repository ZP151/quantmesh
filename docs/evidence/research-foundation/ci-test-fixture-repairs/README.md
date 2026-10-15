# Two actual CI-fixture repairs

The historical quiet log contains14F symbols; the reconstructed node mapping
remains inference because collected runtime/plugins differ from CI. Root then
actually reproduces two narrowed cases on bf64883 source: foreign fixture
UID/GID assignment fails with EPERM, and mount equality retains request-specific
nested evaluated_at timestamps. Both fail before repair (RED2).

Only two test files change. Positive fake-engine profiles use a real assignable
POSIX owner; production chown is neither mocked nor relaxed. A new actual
non-root test rejects a foreign UID before container creation. The two state
mounts now compare their complete JSON at one injected test evaluation clock,
including age and nested freshness metadata. Production feed/calendar/source
and ownership code is unchanged.

Native full two-file boundary:78passed/0skipped/23.01s/exit0. Ruff and whitespace
pass. Formatting corrects existing wraps in live_router without an AST change
after the test run. One bounded independent review finds no P1/P2. Afterward
unmodified dependency admission verifies6669RECORD entries/81licenses/zero.pyc.

These tests use fake Engine control and fixture updates/owned controller/local
HTTP processes; there is no actual Docker Engine, real source or model call,
OCI certification, recovered historical traceback, or complete CI qualification.
The new native-snapshot metadata helper initially attempted Git through the
Windows worktree pointer after its checks passed and failed128; Windows Git
captures that same diff separately. No broad test/dependency rerun masks it.

Raw diagnostic/RED/GREEN/JUnit/format/dependency/patch/review bytes remain hash
bound. No private fixture directories, executable wheels or credentials copied.
