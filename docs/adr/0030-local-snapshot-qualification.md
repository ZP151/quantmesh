# ADR0030 — Local historical snapshot qualification

Status: accepted for the verified local P1 slice; no research qualification,
production or trading admission is implied.
Date: 2026-10-19. Issue: [184](https://github.com/ZP151/quantmesh/issues/184).

## Context

An operator needs to inspect the evidence behind an existing SPY historical
snapshot before using research results. The legacy fixture importer is mutable
and the trusted-data catalog serves qualified data. Neither boundary should
silently certify a package with unresolved source rights, PIT or dividend gaps.
The existing vn.py adapter remains a separately enabled synthetic workflow.

## Decision

Reuse ObjectStore for exact source/package/report bytes and CalendarService for
pinned XNYS sessions. A local snapshot catalog records immutable object references,
deduplicates identical package bytes and verifies stored evidence on reopening.
The initial adapter has one explicit bounded ZIP schema, without arbitrary path
extraction or provider access. An operator-configured root enables its ordinary
workstation API and page; no new queue, engine or trusted catalog admission occurs.

Separate structural consistency from research eligibility. A structural defect
produces REJECT. Consistent bytes with missing entitlement/PIT/source evidence
remain INSUFFICIENT. Manifest assertions alone never independently verify those
claims. Retained raw issuer spreadsheets do not prove their derived JSON matches
the cells. Fixture evidence remains engineering-only. No import grants execution
or strategy-promotion authority.

Pin the initial report bytes and expose their verified digest. Current freshness
is a read-only display relative to completed sessions with a research grace; it
does not rewrite the initial report or establish a vendor availability guarantee.

## Consequences

The first schema is limited to the retained historical SPY package. Other datasets
or daily forward files require explicit adapters. Unknown rights remain unknown;
raw market data stays local and outside Git. This work imports no third-party
engine or strategy implementation and adds no dependencies. Existing source and
dependency licenses remain in force. The prior SMA100 result and consumed OOS
are preserved; the page performs no strategy evaluation.

P2 frozen-experiment display and P3 paper/shadow control are later slices with
separate concrete designs. No live execution or provider credential scope changes.
