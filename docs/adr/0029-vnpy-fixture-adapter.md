# ADR0029 — Optional vn.py synthetic fixture adapter

Status: experimental implementation; not production runtime admission.
Date:2026-10-16. Issue:[177](https://github.com/ZP151/quantmesh/issues/177).

## Context

The operator requested direct reuse of an existing engine and official strategy
source through QuantMesh strategy selection, configuration, submission, progress
and report. Prior isolated bakeoff produced42verified checks and demonstrated
unchanged official vn.py CTA and LEAN runs on one small synthetic dataset.
The current baseline request/report validators encode different algorithms,
walk-forward windows and accounting. Passing native CTA results through them
would misrepresent the engine and weaken existing evidence contracts.

## Decision

Use installed vnpy4.5.0, vnpy_ctastrategy1.4.1 and vnpy_sqlite1.1.3 in an external
Windows Python3.12 environment. Import the unchanged BacktestingEngine and
DoubleMaStrategy/AtrRsiStrategy from official packages. The adapter contains no
copied upstream engine or strategy implementation. Pin official source SHA256s,
fixture SHA256, exact versions, request and adapter/runner hashes to identity.

Expose a separate version1 fixture-only API through an explicit local app factory
and `python -m quantmesh.api.vnpy_fixture`. The default workstation does not mount
these routes. The UI provides a clearly labeled engine selector alongside existing
baselines. No baseline DTO/validator/store/PG/Worker argument or dependency lock
changes. One local owned child at a time,120seconds/1024MiB/one CPU core using the
existing Windows Job Object primitive. Requests select fixed classes and numeric
parameters only; paths are operator CLI inputs and never request inputs.

Model fee in bps of turnover, half spread and slippage in USD/unit/fill. The latter
two map to native additive slippage. Native reports retain daily marking, fills
and nonfinite/unavailable-statistic semantics. Parent validation independently
reconciles signed cash, fees, slippage, positions and five daily balances, and
requires complete replay plus init/start/stop callbacks. Canonical report bytes
are content addressed, checked on read, and SHA-verified by the browser.

## Consequences

This is a removable local experiment. Job discovery and active state are in-memory;
restart interrupts active jobs. Completed bytes remain in the owned output root,
and users can retain standalone JSON downloads. There is no new production queue,
store, durable discovery, advisory or execution authority. Linux, real data,
out-of-sample evaluation, paper trading and promotion require separate slices.

Upstream projects are MIT ([CTA repository](https://github.com/vnpy/vnpy_ctastrategy),
[core repository](https://github.com/vnpy/vnpy)). Exact official wheel LICENSEs and
source oracle remain in the external bakeoff runtime packet. Its dependency
metadata includes Qt/PySide/shiboken and LGPL packages; process isolation does not
authorize redistribution. No external wheel, runtime or dependency closure is
bundled or admitted to QuantMesh's permissive release. Coordinator must mirror this
decision into the shared iteration and reuse matrix before integration.
