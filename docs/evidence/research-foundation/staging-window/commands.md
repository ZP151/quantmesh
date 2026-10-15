Workspace: C:/Users/15492/.codex-clean/worktrees/4836/QuantMesh

Exact fresh verification commands (PowerShell):

```powershell
wsl -d Ubuntu --cd /mnt/c/Users/15492/.codex-clean/worktrees/4836/QuantMesh -- /usr/bin/python3 -B output/169-staging-window/run-native-tests.py
wsl -d Ubuntu -- /usr/bin/python3 -I -S -B /mnt/c/Users/15492/.codex-clean/worktrees/4836/QuantMesh/output/169-staging-window/final-native-proof.py
python -m pytest tests/test_opend_staging_window.py -q --basetemp output/169-staging-window/windows-final-temp
ruff check src tests tools deploy/aws/opend/stage_console.py
ruff format --check deploy/aws/opend/stage_console.py tests/test_opend_staging_window.py
git diff --check
git submodule status
git diff b9d7b5dc9c764ae8699c2c4bce402f48f8f8535c...HEAD --name-status
git status --porcelain
git rev-parse HEAD
```

Native tests are fixed by run-native-tests.py: existing pure pytest tools,
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, only this test file, owned ignored basetemp.
Standalone owned-fixture commands use the fixed same launcher with -I -S -B;
default has no flags/exit2. No command ever invokes real --start/--pane/--prepare/
--create-pane on a host. Test code can call start_staging_console with explicitly
mocked authority/backend and a forced synthetic-only child; no vendor execution.

Each *.log/JSON has a matching *.exit. policy-red/context-red/native-red/safe-error-red/
closure-red/backend-order-red/post-order-red/pin-red/admission-round1-red retain
their actual failing output. Corresponding green/final files are fresh observed output,
not manually edited receipts. See HANDOFF for failure attribution and limits.
