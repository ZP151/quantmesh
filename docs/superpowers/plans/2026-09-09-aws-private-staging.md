# AWS Private Staging Workstation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an exact-commit, private AWS Lightsail demo station that visibly identifies its staging build while preserving QuantMesh's loopback and paper-only invariants.

**Architecture:** QuantMesh continues to run as its existing single FastAPI/React process on `127.0.0.1`. Opt-in deployment metadata is validated in settings and projected into health/the shell; repository-owned systemd and release scripts install exact commits and Tailscale Serve supplies private HTTPS outside the application process.

**Tech Stack:** Python 3.12, Pydantic Settings, FastAPI, React/TypeScript/Vite, Bash, systemd, AWS Lightsail and Tailscale Serve.

**Spec:** `docs/superpowers/specs/2026-09-09-aws-private-staging-design.md`

## Global Constraints

- Branch and worktree start at `origin/main@a78ff0a`; issue #135 is authoritative.
- QuantMesh must continue to refuse every non-loopback workstation host.
- Staging runs `--demo` only with paper mode true and live trading false.
- Tailscale Funnel and public application ports 80, 443 and 8765 are prohibited.
- A build reference is exactly 40 lowercase hexadecimal characters.
- Local health JSON and local shell rendering remain unchanged when deployment metadata is absent.
- No AWS, broker, wallet, model or Tailscale secret enters source, fixtures, logs or environment templates.
- Development checkpoints use focused tests only; no full pytest, browser E2E or release gate.
- Iteration 0030 and iteration-0021 files, branches and runtime state are out of scope.

---

### Task 1: Opt-in deployment identity

**Files:**
- Modify: `src/quantmesh/settings.py`
- Modify: `src/quantmesh/api/app.py`
- Create: `tests/test_deployment_identity.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/shell/AppShell.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/screens/NavigationAndValuation.test.tsx`
- Regenerate: `frontend/src/api/client.ts`
- Regenerate: `src/quantmesh/api/static/app/**`

**Interfaces:**
- Consumes: `Settings.environment`, `_health()`, `Health`, `AppShell`.
- Produces: `Settings.build_ref: str | None`; optional health field
  `deployment: {environment: "staging", build_ref: str}`; visible staging badge.

- [ ] **Step 1: Write failing backend settings and health tests**

  Add tests which prove `Settings(environment="staging")` fails without a
  build ref, uppercase/short/non-hex refs fail, an exact ref succeeds, local
  `_health()` retains its old object and staging health adds exactly the
  deployment object. Also prove `create_app` serves the object at both
  `/health` and `/api/health`.

- [ ] **Step 2: Run the backend RED selection**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.'
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m pytest tests/test_deployment_identity.py -q
  ```

  Expected: collection or assertions fail because `build_ref` and the health
  deployment projection do not exist.

- [ ] **Step 3: Implement the minimal validated settings and health projection**

  Close `environment` to `Literal["local", "staging"]`, add an optional exact
  ref field, and use a Pydantic model validator to require it for staging.
  Add a helper that returns no extra health key for local and the exact nested
  object for staging. Do not change runtime-mode detection or host validation.

- [ ] **Step 4: Run backend GREEN and adjacent health tests**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.'
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m pytest tests/test_deployment_identity.py tests/test_api.py -q
  ```

  Expected: all selected tests pass in under one minute.

- [ ] **Step 5: Write the failing AppShell badge test**

  Extend the `Health` fixture with an optional deployment object and add one
  test where staging health renders `STAGING · 0123456`, exposes the full ref
  in its accessible label/title and retains the demo runtime badge. The default
  fixture must assert no staging badge exists.

- [ ] **Step 6: Run the frontend RED selection**

  Run:

  ```powershell
  Set-Location frontend
  npm.cmd exec vitest run src/screens/NavigationAndValuation.test.tsx
  ```

  Expected: the new staging badge assertion fails because AppShell ignores the
  deployment field.

- [ ] **Step 7: Implement the minimal typed and localized badge**

  Add the optional `deployment` member to `Health`, add exact English and
  Simplified-Chinese `shell.stagingBuild` messages, and render one amber outline
  badge next to the existing demo badge. Use the full ref for title/accessible
  text and the first seven characters for the visible value.

- [ ] **Step 8: Run frontend GREEN, regenerate contracts and package the SPA**

  Run:

  ```powershell
  Set-Location frontend
  npm.cmd exec vitest run src/screens/NavigationAndValuation.test.tsx src/lib/messages.test.ts
  npm.cmd run generate:api
  npm.cmd run typecheck
  npm.cmd run lint
  Set-Location ..
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe tools/build_frontend.py
  ```

  Expected: selected tests, generation, typecheck, lint and build exit 0.

- [ ] **Step 9: Record the slice and commit**

  Update the iteration checkpoint with RED/GREEN counts, then commit the source,
  tests, generated client and packaged bundle as
  `feat(staging): expose exact deployment identity`.

---

### Task 2: Exact-commit Lightsail deployment assets

**Files:**
- Create: `deploy/aws/lightsail/quantmesh-staging.service`
- Create: `deploy/aws/lightsail/deploy_release.py`
- Create: `deploy/aws/lightsail/bootstrap_host.sh`
- Create: `tests/test_aws_staging_assets.py`

**Interfaces:**
- Consumes: canonical repository `https://github.com/ZP151/quantmesh.git`,
  systemd, Python 3.12, urllib and an exact commit argument.
- Produces: `/opt/quantmesh/current`, `/etc/quantmesh/staging.env`,
  `quantmesh-staging.service`, and health-checked rollback behavior.

- [ ] **Step 1: Write failing deployment behavior and unit-semantics tests**

  Load `deploy_release.py` as a real Python module. Use a temporary layout and
  narrow fakes only for Git/systemd/HTTP, then assert observable outcomes:

  - malformed refs are rejected before any command or filesystem mutation;
  - a successful deployment verifies `FETCH_HEAD`, prepares a new release,
    activates it, restarts the service and returns the exact healthy build ref;
  - a mismatched health build ref restores the previous active release and
    restarts it; and
  - a first-deploy health failure removes the broken activation and stops the
    service.

  Parse the unit as a systemd-style section map and assert the effective user,
  environment, writable paths and `ExecStart` semantics: demo root/port 8765,
  staging, paper true/live false, with no public bind or live switch. Human
  runbook prose receives no change-detector test.

- [ ] **Step 2: Run the asset RED selection**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.'
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m pytest tests/test_aws_staging_assets.py -q
  ```

  Expected: module loading or assertions fail because the deployment program
  and unit do not exist.

- [ ] **Step 3: Implement the systemd unit**

  Use `User=quantmesh`, `Group=quantmesh`, `WorkingDirectory=/opt/quantmesh/current`,
  the current release venv entry point, explicit demo/paper/live settings,
  `EnvironmentFile=/etc/quantmesh/staging.env`, restart-on-failure and systemd
  hardening compatible with writes only beneath `/var/lib/quantmesh`.

- [ ] **Step 4: Implement idempotent bootstrap and the testable release program**

  `bootstrap_host.sh` installs only `git`, `curl`, `python3` and `python3-venv`,
  creates the service account/directories, installs the unit and delegates the
  exact commit to `deploy_release.py`. The Python program validates, fetches and
  verifies the commit, creates a Git worktree and venv, installs core QuantMesh,
  writes the non-secret per-release environment, changes the symlink atomically,
  checks `deployment.build_ref`, and rolls back on any post-switch failure.
  External command execution, service control, activation and health reads are
  narrow injectable callables so tests exercise the real orchestration.

- [ ] **Step 5: Run asset GREEN and syntax checks**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.'
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m pytest tests/test_aws_staging_assets.py -q
  & 'C:\Program Files\Git\bin\bash.exe' -n deploy/aws/lightsail/bootstrap_host.sh
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m py_compile deploy/aws/lightsail/deploy_release.py
  ```

  Expected: focused tests, Bash syntax and Python compilation exit 0.

- [ ] **Step 6: Record the slice and commit**

  Update the iteration checkpoint and commit as
  `feat(staging): add exact-commit Lightsail deployment`.

---

### Task 3: Durable operator handoff and bounded verification

**Files:**
- Create: `docs/adr/0019-private-staging-boundary.md`
- Create: `docs/runbooks/aws-private-staging.md`
- Create: `docs/iterations/0031-private-aws-staging-workstation.md`
- Modify: `docs/iterations/INDEX.md`
- Modify: `CONTEXT.md`
- Modify: `docs/roadmap/ROADMAP.md`
- Modify: `docs/REUSE_MATRIX.md`
- Modify: `docs/goals/ACTIVE.md`

**Interfaces:**
- Consumes: issue #135, the approved design, deployment scripts and AWS account
  facts recorded in the spec.
- Produces: one Windows-first bootstrap/update/rollback/cost runbook and the
  durable planner/researcher/implementer/reviewer/verifier ledger.

- [ ] **Step 1: Write the ADR and operator runbook**

  ADR-0019 records the controlled exception from local-device to private
  single-operator staging while retaining loopback. The runbook gives exact
  Lightsail selections, initial SSH restriction, server bootstrap command,
  Tailscale Serve command, Windows Tailscale access, health checks, update and
  rollback commands, and AWS Budget thresholds. It explicitly states that
  budget alerts are not hard caps and that instance creation/device
  authorization require operator confirmation.

- [ ] **Step 2: Update durable project state**

  Record iteration 0031 as active without altering 0030's branch-owned ledger;
  update stale 0028/0029 status in the index/context where the merged tree is
  authoritative; add the staging feedback station to the roadmap; record
  Tailscale as an external host adapter rather than a Python dependency; and
  make `docs/goals/ACTIVE.md` resumable from issue #135 and this plan.

- [ ] **Step 3: Run fresh bounded verification**

  Run:

  ```powershell
  $env:PYTHONPATH='src;.'
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m pytest tests/test_deployment_identity.py tests/test_aws_staging_assets.py tests/test_api.py -q
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe check src/quantmesh/settings.py src/quantmesh/api/app.py tests/test_deployment_identity.py tests/test_aws_staging_assets.py
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\ruff.exe format --check src/quantmesh/settings.py src/quantmesh/api/app.py tests/test_deployment_identity.py tests/test_aws_staging_assets.py
  Set-Location frontend
  npm.cmd exec vitest run src/screens/NavigationAndValuation.test.tsx src/lib/messages.test.ts
  npm.cmd run typecheck
  npm.cmd run lint
  npm.cmd run check:api
  Set-Location ..
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe tools/build_frontend.py --check
  & 'C:\Program Files\Git\bin\bash.exe' -n deploy/aws/lightsail/bootstrap_host.sh
  C:\Users\15492\Develop\QuantMesh\.venv\Scripts\python.exe -m py_compile deploy/aws/lightsail/deploy_release.py
  git diff --check
  ```

  Expected: every command exits 0. No full pytest, domain sweep, browser E2E or
  release gate is part of this checkpoint.

- [ ] **Step 4: Review the requirements and push the integration branch**

  Compare every issue acceptance criterion and spec constraint to the diff,
  inspect that no secret/public/live authority appears, update the iteration
  with exact verification output and commit as
  `docs(staging): add private AWS operator handoff`. Push
  `codex/0031-aws-private-staging` for durable recovery.

- [ ] **Step 5: Stop at the AWS financial confirmation gate**

  Present the verified repository state and the exact Lightsail selection. Do
  not click `Create instance`, create a budget, authorize a Tailscale device or
  install anything on the operator's Windows computer until the corresponding
  action-time confirmation is obtained.

## Final requirements checklist

- [ ] Issue #135 acceptance criteria map one-to-one to implementation evidence.
- [ ] Local health and shell behavior are unchanged without staging metadata.
- [ ] Staging refuses missing or malformed exact build identity.
- [ ] QuantMesh remains loopback-only and demo/paper-only.
- [ ] Exact-commit deploy verifies health identity and rolls back on failure.
- [ ] No public application port, Funnel, secret, live/testnet order or paid
      auxiliary AWS service is introduced.
- [ ] The Windows runbook covers create, bootstrap, private access, update,
      rollback, bounded smoke and cost alerts.
- [ ] Focused verification is fresh and recorded; no long suite was run.
