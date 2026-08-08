# License inventory and policy

Deterministic inventory check (M10 Phase D, issue #61; iteration 0013
Phase B): every distribution in the **pinned release closure** —
`requirements-audit.txt`, the frozen install of `.[dev,research,e2e]`
— is classified from its PEP 639 / PEP 345 metadata by
`tools/license_review.py` (stdlib only, no network) and must land on
the documented allowlist. The CI `security` job runs it over a fresh
install of the release extras; exit 0 only when every closure package
is allowed and **no package outside the closure is installed** — an
incompatible, unclassifiable or untracked package names itself and
fails the job.

The closure contract is what makes the gate deterministic: the review
never scans the ambient environment, so a development venv's leftover
packages (older research experiments, or the audit tool's own
dependencies) cannot silently drift into the inventory. Run the gate
in the deterministic release environment (`tools/release_gate.py`
creates one).

## Policy

- **Allowed** (permissive, redistributable): MIT, BSD-2-Clause,
  BSD-3-Clause, Apache-2.0, PSF-2.0, ISC, MPL-2.0 (file-level
  copyleft — permissive for redistribution; certifi, tqdm), 0BSD,
  Zlib, CC0-1.0, CNRI-Python (the historical CNRI Python license),
  MIT-CMU (Pillow's MIT variant), MIT-0 (MIT No Attribution,
  OSI-approved; cffi declares it).
- **Refused**: GPL/AGPL, LGPL, proprietary licenses, source-available
  restrictions such as the Commons Clause, and anything unclassified.
- **Untracked installed packages are refused**: the installed
  third-party set must equal the pinned closure (plus the venv's own
  pip/setuptools/wheel build tooling). This is the iteration-0013
  resolution of the ambient `license-expression`/`boolean.py` drift.
- **`WITH <exception>` SPDX qualifiers relax** the license
  (e.g. `BSD-2-Clause AND Apache-2.0 WITH LLVM-exception` for
  llvmlite) and are stripped, never treated as restricting members.
- **Free-text `License` fields read the first line as authoritative**
  when it names a known license: some wheels inline the entire
  `LICENSES/` folder into one field (pandas 2.3.3 Linux builds — BSD
  text plus bundled Apache/MIT texts), where scanning the whole blob
  would credit a bundled third-party text as the project's license.
  The Commons Clause check still runs first, so a
  Commons-Clause package can never slip through via a bundled text.
- **Documented exceptions** cover closure packages whose metadata
  carries no usable license field; each must name the license the
  package actually ships under. Only closure members belong in this
  table (the review never classifies anything outside
  `requirements-audit.txt`):

| Package | License | Justification |
| --- | --- | --- |
| certifi | MPL-2.0 | MPL-2.0 is on the allowlist; metadata omits it |
| tzdata | Apache-2.0 | the IANA timezone database under Apache-2.0 |

## Security toolchain (outside the release closure)

The advisory scanner is not part of the release install. It runs in a
separate step (CI) or a separate environment (release gate) so its own
CLI dependencies never contaminate the application's license
inventory. Recorded for reference, verified permissive:

- `pip-audit 2.10.1` — Apache-2.0 (its own license)
- `license-expression 30.4.4` — Apache-2.0 (pip-audit transitive)
- `boolean.py 5.0` — BSD-2-Clause (pip-audit transitive)

These are the packages whose ambient presence tripped the pre-0013
gate in the development venv (iteration 0013 "Verified starting
point"). Under the closure contract they are isolated from the product
inventory by design; installing them into a release environment
refuses the license gate with a precise message.

## Linux-only closure members

Six closure packages are pinned for every platform but installable
only on some. On non-Linux machines the license review tolerates their
*absence* (they are pinned in the lock, documented here, and verified
from the Linux CI run):

- `uvloop` — MIT — `uvicorn[standard]`'s loop on CPython/Linux
- `jeepney` — MIT — keyring's Linux D-Bus backend
- `SecretStorage` — BSD-3-Clause — jeepney's Secret Service binding
- `cryptography` — Apache-2.0 | BSD-3-Clause — SecretStorage's crypto
- `cffi` — MIT-0 — cryptography's CFFI backend
- `pycparser` — BSD-3-Clause — CFFI's parser

If a dependency change adds a new platform-restricted member, the lock
regeneration (see `docs/release-process.md`) and
`PLATFORM_TOLERATED` in the review tool must grow together; the gate
fails loudly otherwise.

## Decisions recorded on this surface

- **vectorbt was removed from the `research` extra (ADR-0012
  decision 4)** — it ships as Apache-2.0 **with the Commons Clause**
  (source-available, not OSI: the clause strips the right to sell the
  software). No code path imported it, so the extra shrank instead of
  carrying a non-OSI dependency. The review's text classifier refuses
  the Commons Clause before the Apache appendix text can match, so a
  Commons-Clause package can never silently re-enter the inventory.
- **keyring was added to the `dev` extra (ADR-0012 decision 5,
  M10 Phase E)** — MIT, the OS-backed secret store behind the
  `KeyStore` protocol. The suite exercises only the fixture backend;
  the real backend refuses construction outside an explicit drill
  flag, so the OS keyring is never touched (T-07).
- **The closure includes the `e2e` extra (iteration 0013 Phase B)** —
  playwright (Apache-2.0) with pyee and greenlet are part of the
  release extras install, so the audit lock, the license gate and the
  CI security job cover the full release closure, not just
  `.[dev,research]`.

## Inventory (generated 2026-08-08; 64 packages in the release
closure `.[dev,research,e2e]`)

Regenerate with `python tools/license_review.py` in an environment
that is exactly the release closure (the release gate creates one).
Version numbers drift with the lock; the license key is the contract.

| Package | Version | License |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.14.2 | MIT |
| arch | 7.2.0 | BSD-2-Clause |
| certifi | 2026.7.22 | MPL-2.0 (documented exception) |
| cffi | 2.1.1 (Linux-only) | MIT-0 |
| click | 8.4.2 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause |
| cryptography | 50.0.0 (Linux-only) | Apache-2.0 | BSD-3-Clause |
| duckdb | 1.5.5 | MIT |
| fastapi | 0.141.1 | MIT |
| greenlet | 3.5.4 | MIT | PSF-2.0 |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.8.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.18 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| jaraco.classes | 3.4.0 | MIT |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| jeepney | 0.9.0 (Linux-only) | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| joblib | 1.5.3 | BSD-3-Clause |
| keyring | 25.7.0 | MIT |
| lightgbm | 4.7.0 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| more-itertools | 11.1.0 | MIT |
| narwhals | 2.24.0 | MIT |
| numpy | 2.5.1 | 0BSD | BSD-3-Clause | CC0-1.0 | MIT | Zlib |
| packaging | 26.3 | Apache-2.0 | BSD-2-Clause |
| pandas | 2.3.3 | BSD-3-Clause |
| patsy | 1.0.2 | BSD-3-Clause |
| playwright | 1.62.0 | Apache-2.0 |
| pluggy | 1.6.0 | MIT |
| pycparser | 3.0 (Linux-only) | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pydantic_core | 2.46.4 | MIT |
| pyee | 13.0.1 | MIT |
| Pygments | 2.20.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pytz | 2026.3.post1 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| ruff | 0.16.2 | MIT |
| scikit-learn | 1.9.0 | BSD-3-Clause |
| scipy | 1.18.0 | BSD-3-Clause |
| SecretStorage | 3.5.0 (Linux-only) | BSD-3-Clause |
| six | 1.17.0 | MIT |
| starlette | 1.5.0 | BSD-3-Clause |
| statsmodels | 0.14.6 | BSD-3-Clause |
| threadpoolctl | 3.6.0 | BSD-3-Clause |
| typing-inspection | 0.4.2 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.3 | Apache-2.0 (documented exception) |
| uvicorn | 0.52.1 | BSD-3-Clause |
| uvloop | 0.22.1 (Linux-only) | MIT |
| watchfiles | 1.2.0 | MIT |
| websockets | 17.0.1 | BSD-3-Clause |
