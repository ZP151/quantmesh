# ADR-0027: Admit the LGPL weak-copyleft dependency family

- **Status:** Accepted
- **Date:** 2026-10-14
- **Decision owners:** QuantMesh operator and maintainers
- **Supersedes:** the blanket Python dependency audit refusal of LGPL; it does
  not change ADR-0013's separately scoped frontend dependency selection.

## Context

The exact-head release security gate refused the installed `psycopg` and
`psycopg-binary` distributions because their declared license is LGPL-3.0 and
the Python closure audit refused all LGPL licenses. The operator explicitly
approved expanding that policy and asked that similar cases be covered. The
existing PostgreSQL job-store implementation uses Psycopg; replacing it with a
different driver solely to avoid this policy decision would add churn and would
not resolve the underlying dependency-policy question.

The exact Windows wheels `psycopg==3.3.6` and
`psycopg-binary==3.3.6` were downloaded from the package index and their
METADATA fields both declare `License-Expression: LGPL-3.0-only`; each wheel
includes `LICENSE.txt`. Their recorded SHA256 values are
`a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631` for
the universal Psycopg wheel and
`0ebfad5d131de9f892ae9e70cc7616207768b6714b66a52d4612b8ceaf78b372` for
the CPython 3.13 Windows binary wheel. The [upstream Psycopg license](https://github.com/psycopg/psycopg/blob/master/LICENSE.txt)
is the GNU Lesser General Public License version 3.

The additional exact identifiers were checked against the Open Source
Initiative's [MPL-2.0](https://opensource.org/license/MPL-2.0),
[EPL-2.0](https://opensource.org/license/EPL-2.0) and
[CDDL-1.0](https://opensource.org/license/CDDL-1.0) license records. Their
reciprocal obligations have different scopes; inclusion in an inventory
allowlist only means a package may proceed to exact-package and distribution-
form review.

## Decision

The Python release closure may include LGPL-2.0, LGPL-2.1 and LGPL-3.0, whether
the metadata uses the base version or its explicit SPDX `-only` or
`-or-later` form. The operator also approved the same bounded treatment for the
exact SPDX identifiers `MPL-2.0`, `EPL-2.0` and `CDDL-1.0`. No other version,
license family or variant is inferred from a broad label such as “weak
copyleft”; it remains refused until the operator and maintainers record an
explicit exact-identifier decision. This allows comparable file/component-
scoped copyleft terms without turning the classifier into a wildcard.

The audit continues to fail closed for GPL, AGPL, proprietary or unknown
licenses, and source-available restrictions such as the Commons Clause.
Compound declarations containing any refused member remain refused.

For every weak-copyleft component, release owners must identify the exact
package, version and license text and evaluate the intended distribution
before shipping. Where applicable, distribution must preserve notices and
license text and meet that license's source, modification, relinking and
reciprocity requirements. The inventory checker records classification; it
does not certify that a particular product distribution complies with those
obligations. This ADR is an engineering policy decision, not legal advice.

The frontend npm license gate remains governed by its own inventory and
allowlist. This ADR does not add LGPL packages to that closure.

## Consequences

- Psycopg may remain the PostgreSQL driver, subject to exact closure pins and
  passing the security gate.
- The audit parser admits only the exact weak-copyleft SPDX identifiers listed
  above, explicitly distinguishes them from GPL/AGPL, and retains the refusal
  for Commons Clause and unknown terms.
- Future weak-copyleft identifiers or versions still require an explicit
  policy decision; this approval does not open an unrestricted wildcard.
