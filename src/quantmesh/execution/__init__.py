"""Execution kernel: deterministic paper matching and the durable order journal.

``PaperMatcher`` produces fills as a pure function of order/quote/time;
``OrderJournal`` records every order snapshot durably so broker/paper
reconciliation (ADR-0006) has a single source of truth for order
identity.
"""

from quantmesh.execution.journal import JOURNAL_FILE, OrderJournal
from quantmesh.execution.matcher import MatchResult, PaperMatcher

__all__ = ["JOURNAL_FILE", "MatchResult", "OrderJournal", "PaperMatcher"]
