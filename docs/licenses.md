# License inventory and policy

Deterministic inventory check (M10 Phase D, issue #61; iteration 0013
Phase B): every distribution in the **pinned release closure** —
`requirements-audit.txt`, the frozen install of `.[dev,research,e2e,moomoo]`
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

The release gate separately installs the exact pip/setuptools/wheel versions in
`requirements-build.txt`, disables PEP 517 build isolation, then resolves the
runtime extras under `requirements-audit.txt` as a constraints file. The
license review verifies both exact build-tool versions and every runtime pin;
an isolated backend download or installed-version drift fails closed.

## Policy

- **Allowed** (permissive, redistributable): MIT, BSD-2-Clause,
  BSD-3-Clause, Apache-2.0, PSF-2.0, ISC, MPL-2.0 (file-level
  copyleft — permissive for redistribution; certifi, tqdm), 0BSD,
  Zlib, CC0-1.0, CNRI-Python (the historical CNRI Python license),
  MIT-CMU (Pillow's MIT variant), MIT-0 (MIT No Attribution,
  OSI-approved; cffi declares it), NCSA (University of Illinois/NCSA
  license; `arch` 8).
- **Refused**: GPL/AGPL, LGPL, proprietary licenses, source-available
  restrictions such as the Commons Clause, and anything unclassified.
- **Untracked installed packages are refused**: the installed
  third-party set must equal the pinned runtime closure plus the separately
  version-verified pip/setuptools/wheel build tooling. This is the iteration-0013
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
| simplejson | MIT | metadata declares `MIT OR AFL-2.1`; QuantMesh selects the allowed MIT alternative |
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

## Framework bake-off tooling (outside the release closure)

Iteration 0020 evaluated candidate frameworks in external checkouts and virtual
environments. ADR-0015 admits neither candidate to the product runtime, so this
record is deliberately separate from the generated release inventory below:

- FinRL-X was pinned to
  `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1` (Apache-2.0). Its isolated install
  failed while building `bt` because MSVC 14.0+ was unavailable; no FinRL-X or
  bake-off-only transitive package was added to QuantMesh.
- NautilusTrader was pinned to `v1.231.0` /
  `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317` (LGPL-3.0). It is retained only as
  removable process-isolated comparison tooling. `nautilus_trader` is not a
  release dependency.
- The comparator's external environment pinned `pandas==2.3.3` for upstream
  compatibility. That pin does not add or alter a release dependency; pandas
  already appears independently in the QuantMesh research closure and the
  inventory below remains generated solely from `requirements-audit.txt`.
- Copied upstream source: zero files. New release runtime dependencies: zero.

The isolated environments, wheels and checkouts are not distributed. Their
portable evidence and hashes are recorded under `docs/evidence/0020/`.

## Platform-restricted closure members

Eight closure packages are pinned for every platform but part of the
frozen resolution on one platform family only. On platforms where they
do not resolve, the license review tolerates their *absence* (they are
pinned in the lock, documented here, and verified from the platform's
own CI/gate run):

Six resolve on Linux only (verified from the Linux CI run):

- `uvloop` — MIT — `uvicorn[standard]`'s loop on CPython/Linux
- `jeepney` — MIT — keyring's Linux D-Bus backend
- `SecretStorage` — BSD-3-Clause — jeepney's Secret Service binding
- `cryptography` — Apache-2.0 | BSD-3-Clause — SecretStorage's crypto
- `cffi` — MIT-0 — cryptography's CFFI backend
- `pycparser` — BSD-3-Clause — CFFI's parser

Two resolve on Windows only (the canonical lock is generated on
Windows, so the dry-run report includes them; the Linux resolution
never selects them):

- `colorama` — BSD-3-Clause — pytest's `sys_platform == "win32"`
  dependency
- `pywin32-ctypes` — BSD-3-Clause — keyring's Windows Secret Service
  backend

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
- **The closure includes the `moomoo` extra (iteration 0021 Task 6)** —
  `moomoo_api==10.10.7008` is Apache-2.0 and supplies the inspected official
  read-only history, adjustment-factor, split and dividend methods. Its
  `protobuf`, `pycryptodome` and `simplejson` dependencies are pinned and
  audited in the same release environment; this does not enable trading.

## Project-scoped development skills

These agent-development resources are vendored documentation/tools and are not
part of the Python runtime dependency closure:

- `Leonxlnx/taste-skill` at
  `e988add20dab0fa97d7a76781c48961c8184288e`, MIT. The upstream license is
  preserved in `docs/third-party/taste-skill-LICENSE`.
- `pbakaus/impeccable` at
  `aee6ce9352b842217b3f57c78296a7a4fa35a7f3`, Apache-2.0. The repository root
  carries the Apache-2.0 license and the upstream notice is preserved in
  `docs/third-party/impeccable-NOTICE.md`.

## Frontend npm closure (iteration 0020 Task 6, checked 2026-08-12)

ADR-0013 Decision 5 budget: permissive licenses only; any dependency
outside the adopted set enters through a license/maintenance check
recorded here and in `docs/REUSE_MATRIX.md`. The checks are `npm audit
--audit-level=high` for advisories plus the fail-closed, stdlib-only
`python tools/npm_license_review.py` scan of `package-lock.json` (no network).
They run in PR CI, the path-filtered Security workflow and the clean-checkout
release gate. **646 packages**
(lockfile v3, root entry excluded, all platform variants included), **every license
allowlisted**: MIT 562, ISC 26, MPL-2.0 24, Apache-2.0 11,
BSD-3-Clause 8, BSD-2-Clause 7, BlueOak-1.0.0 2, 0BSD 1, MIT-0 1,
OFL-1.1 1, CC-BY-4.0 1, Python-2.0 1, `(MIT OR CC0-1.0)` 1. No GPL/AGPL/LGPL, no
source-available restriction, no untracked package.

- MPL-2.0 ×24 is one project: `lightningcss` (Tailwind 4's CSS
  engine) plus its platform binaries — file-level copyleft,
  permissive for redistribution (same policy as the Python
  allowlist's certifi/tqdm).
- Notable non-MIT: `typescript` (Apache-2.0), `lightningcss`
  (MPL-2.0), `@fontsource-variable/geist` (OFL-1.1 font license),
  `caniuse-lite` (CC-BY-4.0 data), `argparse` JS port (Python-2.0),
  `tslib` (0BSD), `dotenv`/`esprima`/`entities` (BSD-2-Clause),
  `qs`/`source-map`/`tough-cookie`/`diff` (BSD-3-Clause),
  `aria-query`/`xml-name-validator`/`human-signals` (Apache-2.0),
  `isexe`/`minimatch` (BlueOak-1.0.0), `class-variance-authority`
  (Apache-2.0), `expect-type` (Apache-2.0).
- Phase E additions (`frontend/package.json` devDependencies):
  `vitest` 3.2.7 (MIT), `jsdom` 26.1.0 (MIT),
  `@testing-library/react` 16.3.2 (MIT),
  `@testing-library/jest-dom` 6.9.1 (MIT),
  `@testing-library/user-event` 14.6.3 (MIT) — all already present
  in the closure scan above; recorded in `docs/REUSE_MATRIX.md`.
- Iteration 0020 Task 6 adds exact pins `openapi-fetch` 0.17.0 (MIT,
  runtime) and `openapi-typescript` 7.13.0 (MIT, development). The generator's
  declared TypeScript 5 peer range requires exact `typescript` 5.9.3
  (Apache-2.0), replacing the unsupported 6.0 pre-existing range. These changes
  add 20 lockfile entries. `type-fest` 4.41.0 accounts for the one
  `(MIT OR CC0-1.0)` entry.
- Iteration 0020 Task 11 adds exact runtime pin `lightweight-charts` 5.2.0
  ([npm](https://www.npmjs.com/package/lightweight-charts),
  [source](https://github.com/tradingview/lightweight-charts)) under
  Apache-2.0, plus its MIT dependency `fancy-canvas` 2.1.0. Registry metadata
  records an unpacked package size of 3,066,492 bytes. The adapter keeps the
  library behind one QuantMesh component, enables its TradingView attribution
  logo, and renders a user-visible `Charts by TradingView` link. The package
  ships `LICENSE` but no separate `NOTICE`; the Apache license remains in the
  npm distribution and no upstream notice file needs vendoring.
- Runtime `dependencies` (direct): `react`/`react-dom` 19.2.8,
  `react-router-dom` 7.18.2, `@tanstack/react-query` 5.101.4,
  `@base-ui/react` 1.7.0, `tailwindcss` 4.3.3 + `@tailwindcss/vite`,
  `tw-animate-css`, `class-variance-authority`, `clsx`,
  `tailwind-merge`, `lucide-react`, `shadcn` 4.16.2 (CLI),
  `openapi-fetch` 0.17.0, `lightweight-charts` 5.2.0,
  `@fontsource-variable/geist`, `@rolldown/binding-win32-x64-msvc`
  (Vite's bundler binary) — all permissive (MIT / Apache-2.0 /
  BSD-3-Clause / OFL-1.1 as scanned above).
- Maintenance: both frontend gates run on every PR and release candidate;
  package/lock changes also trigger the Security workflow. A dependency
  change beyond patch level requires a re-check of this section and the
  explicit SPDX allowlist.

## Inventory (generated 2026-08-24; 72 packages in the release
closure `.[dev,research,e2e,moomoo]`)

Regenerate with `python tools/license_review.py` in an environment
that is exactly the release closure (the release gate creates one).
Version numbers drift with the lock; the license key is the contract.

| Package | Version | License |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.14.2 | MIT |
| arch | 8.0.0 | NCSA |
| certifi | 2026.7.22 | MPL-2.0 (documented exception) |
| cffi | 2.1.1 (Linux-only) | MIT-0 |
| click | 8.4.2 | BSD-3-Clause |
| colorama | 0.4.6 (Windows-only) | BSD-3-Clause |
| cryptography | 50.0.0 (Linux-only) | Apache-2.0 | BSD-3-Clause |
| duckdb | 1.5.5 | MIT |
| exchange_calendars | 4.13.2 | Apache-2.0 |
| fastapi | 0.141.1 | MIT |
| greenlet | 3.5.5 | MIT | PSF-2.0 |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.8.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.19 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| jaraco.classes | 3.4.0 | MIT |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| jeepney | 0.9.0 (Linux-only) | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| joblib | 1.5.3 | BSD-3-Clause |
| keyring | 25.7.0 | MIT |
| korean_lunar_calendar | 0.4.0 | MIT |
| lightgbm | 4.7.0 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| moomoo_api | 10.10.7008 | Apache-2.0 |
| more-itertools | 11.1.0 | MIT |
| narwhals | 2.25.0 | MIT |
| numpy | 2.5.2 | 0BSD | BSD-3-Clause | CC0-1.0 | MIT | Zlib |
| packaging | 26.3 | Apache-2.0 | BSD-2-Clause |
| pandas | 2.3.3 | BSD-3-Clause |
| patsy | 1.0.2 | BSD-3-Clause |
| playwright | 1.62.0 | Apache-2.0 |
| pluggy | 1.6.0 | MIT |
| protobuf | 7.36.0 | BSD-3-Clause |
| pycparser | 3.0 (Linux-only) | BSD-3-Clause |
| pycryptodome | 3.23.0 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pydantic_core | 2.46.4 | MIT |
| pyee | 13.0.1 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pyluach | 2.3.0 | MIT |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pytz | 2026.3.post1 | MIT |
| pywin32-ctypes | 0.2.3 (Windows-only) | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| ruff | 0.16.4 | MIT |
| scikit-learn | 1.9.0 | BSD-3-Clause |
| scipy | 1.18.1 | BSD-3-Clause |
| SecretStorage | 3.5.0 (Linux-only) | BSD-3-Clause |
| simplejson | 4.1.1 | MIT (documented exception) |
| six | 1.17.0 | MIT |
| starlette | 1.6.0 | BSD-3-Clause |
| statsmodels | 0.14.6 | BSD-3-Clause |
| threadpoolctl | 3.6.0 | BSD-3-Clause |
| toolz | 1.1.0 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.3 | Apache-2.0 (documented exception) |
| uvicorn | 0.52.4 | BSD-3-Clause |
| uvloop | 0.22.1 (Linux-only) | MIT |
| watchfiles | 1.2.0 | MIT |
| websockets | 17.0.1 | BSD-3-Clause |
