# License inventory and policy

Deterministic inventory check (M10 Phase D, issue #61): every
distribution in the installed environment is classified from its PEP
639 / PEP 345 metadata by `tools/license_review.py` (stdlib only, no
network) and must land on the documented allowlist. The CI `security`
job runs it over the real install of `.[dev,research]`; exit 0 only
when every package is allowed — an incompatible or unclassifiable
license names its package and fails the job.

## Policy

- **Allowed** (permissive, redistributable): MIT, BSD-2-Clause,
  BSD-3-Clause, Apache-2.0, PSF-2.0, ISC, MPL-2.0 (file-level
  copyleft — permissive for redistribution; certifi, tqdm), 0BSD,
  Zlib, CC0-1.0, CNRI-Python (the historical CNRI Python license),
  MIT-CMU (Pillow's MIT variant), MIT-0 (MIT No Attribution,
  OSI-approved; cffi declares it).
- **Refused**: GPL/AGPL, LGPL, proprietary licenses, source-available
  restrictions such as the Commons Clause, and anything unclassified.
- **`WITH <exception>` SPDX qualifiers relax** the license
  (e.g. `BSD-2-Clause AND Apache-2.0 WITH LLVM-exception` for
  llvmlite) and are stripped, never treated as restricting members.
- **Documented exceptions** cover packages whose metadata carries no
  usable license field; each must name the license the package
  actually ships under:

| Package | License | Justification |
| --- | --- | --- |
| asttokens | MIT | full MIT text ships in the sdist; metadata omits it |
| certifi | MPL-2.0 | MPL-2.0 is on the allowlist; metadata omits it |
| charset-normalizer | MIT | metadata omits the license |
| fonttools | MIT | metadata omits the license |
| tqdm | MPL-2.0 | MPL-2.0 is on the allowlist; metadata omits it |
| tzdata | Apache-2.0 | the IANA timezone database under Apache-2.0 |

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

## Inventory (generated 2026-08-08; 100 packages in this environment,
plus 6 Linux-only closure packages)

The CI-relevant closure is the 61 packages pinned in
`requirements-audit.txt` (a fresh `.[dev,research]` install,
quantmesh itself excluded); the table below is the review output
over the working environment (superset — includes leftover
transitives of the removed vectorbt and of earlier dev experiments,
all permissively licensed) plus the 6 Linux-only closure packages
CI's Linux runner installs (`uvloop` from `uvicorn[standard]`;
`jeepney`, `SecretStorage`, `cryptography`, `cffi`, `pycparser`
from keyring), so the documented coverage holds on both platforms.
Regenerate with `python tools/license_review.py`.

| Package | Version | License |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.14.2 | MIT |
| anywidget | 0.11.0 | MIT |
| arch | 7.2.0 | BSD-2-Clause |
| asttokens | 3.0.2 | MIT (documented exception) |
| certifi | 2026.7.22 | MPL-2.0 (documented exception) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.4.9 | MIT (documented exception) |
| click | 8.4.2 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause |
| comm | 0.2.3 | BSD-3-Clause |
| contourpy | 1.3.3 | BSD-3-Clause |
| cryptography | 50.0.0 | Apache-2.0 | BSD-3-Clause |
| cycler | 0.12.1 | BSD-3-Clause |
| dateparser | 1.4.2 | BSD-3-Clause |
| dill | 0.4.1 | BSD-3-Clause |
| duckdb | 1.5.5 | MIT |
| executing | 2.2.1 | MIT |
| fastapi | 0.141.1 | MIT |
| fonttools | 4.63.0 | MIT (documented exception) |
| greenlet | 3.5.4 | MIT | PSF-2.0 |
| h11 | 0.16.0 | MIT |
| hmmlearn | 0.3.3 | BSD-3-Clause |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.8.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.18 | BSD-3-Clause |
| ImageIO | 2.37.4 | BSD-2-Clause |
| iniconfig | 2.3.0 | MIT |
| ipython | 9.16.1 | BSD-3-Clause |
| ipython_pygments_lexers | 1.1.1 | BSD-3-Clause |
| ipywidgets | 8.1.8 | BSD-3-Clause |
| jaraco.classes | 3.4.0 | MIT |
| jaraco.context | 6.1.2 | MIT |
| jaraco.functools | 4.6.0 | MIT |
| jedi | 0.20.0 | MIT |
| jeepney | 0.9.0 | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| joblib | 1.5.3 | BSD-3-Clause |
| jupyterlab_widgets | 3.0.16 | BSD-2-Clause |
| keyring | 25.7.0 | MIT |
| kiwisolver | 1.5.0 | BSD-3-Clause |
| lightgbm | 4.7.0 | MIT |
| llvmlite | 0.48.0 | Apache-2.0 | BSD-2-Clause |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| matplotlib | 3.11.1 | Apache-2.0 |
| matplotlib-inline | 0.2.2 | BSD-3-Clause |
| more-itertools | 11.1.0 | MIT |
| mypy_extensions | 1.1.0 | MIT |
| narwhals | 2.24.0 | MIT |
| numba | 0.66.0 | BSD-3-Clause |
| numpy | 2.4.6 | 0BSD | BSD-3-Clause | CC0-1.0 | MIT | Zlib |
| packaging | 26.3 | Apache-2.0 | BSD-2-Clause |
| pandas | 2.3.3 | BSD-3-Clause |
| parso | 0.8.7 | MIT |
| patsy | 1.0.2 | BSD-3-Clause |
| pillow | 12.3.0 | MIT-CMU |
| pip | 26.2.1 | MIT |
| playwright | 1.62.0 | Apache-2.0 |
| plotly | 6.9.0 | MIT |
| pluggy | 1.6.0 | MIT |
| prompt_toolkit | 3.0.53 | BSD-3-Clause |
| psutil | 7.2.2 | BSD-3-Clause |
| psygnal | 0.15.1 | BSD-3-Clause |
| pure_eval | 0.2.3 | MIT |
| pydantic | 2.13.4 | MIT |
| pydantic-settings | 2.14.2 | MIT |
| pydantic_core | 2.46.4 | MIT |
| pycparser | 3.0 | BSD-3-Clause |
| pyee | 13.0.1 | MIT |
| Pygments | 2.20.0 | BSD-2-Clause |
| pyparsing | 3.3.2 | MIT |
| pytest | 8.4.2 | MIT |
| pytest-asyncio | 0.26.0 | Apache-2.0 |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pytz | 2026.3.post1 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| regex | 2026.7.19 | Apache-2.0 | CNRI-Python |
| requests | 2.34.2 | Apache-2.0 |
| ruff | 0.16.1 | MIT |
| schedule | 1.2.2 | MIT |
| scikit-learn | 1.9.0 | BSD-3-Clause |
| scipy | 1.18.0 | BSD-3-Clause |
| SecretStorage | 3.5.0 | BSD-3-Clause |
| six | 1.17.0 | MIT |
| stack-data | 0.6.3 | MIT |
| starlette | 1.4.1 | BSD-3-Clause |
| statsmodels | 0.14.6 | BSD-3-Clause |
| threadpoolctl | 3.6.0 | BSD-3-Clause |
| tqdm | 4.70.0 | MPL-2.0 (documented exception) |
| traitlets | 5.16.1 | BSD-3-Clause |
| typing-inspection | 0.4.2 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.3 | Apache-2.0 (documented exception) |
| tzlocal | 5.4.4 | MIT |
| urllib3 | 2.7.0 | MIT |
| uvicorn | 0.52.1 | BSD-3-Clause |
| uvloop | 0.22.1 | MIT |
| watchfiles | 1.2.0 | MIT |
| wcwidth | 0.8.2 | MIT |
| websockets | 17.0.1 | BSD-3-Clause |
| widgetsnbextension | 4.0.15 | BSD-3-Clause |
