"""Durable effects and checkpoint; reservations precede provider invocation.

Uses the authoritative store's transaction (PostgreSQL in service mode).
Local SQLite use is only the explicitly-labelled offline boundary witness.
"""

from decimal import Decimal

from qm_research_agent.accounting import (
    PortfolioBudgetPolicy,
    admit,
    canonical,
    exact_total,
    initialize,
    valid_amount,
)
from quantmesh.research.jobs import AnalysisRecord, RunBudget


class EffectLedger:
    def __init__(self, store, *, policy=None, category=None):
        if (
            (policy is None) != (category is None)
            or (policy is not None and not isinstance(policy, PortfolioBudgetPolicy))
            or (category is not None and category not in {"operating", "development"})
        ):
            raise ValueError("invalid portfolio configuration")
        self.store = store
        self.policy, self.category = policy, category
        with store._transaction() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS model_effects ("
                "job_id TEXT REFERENCES jobs(job_id), digest TEXT, price TEXT NOT NULL, "
                "status TEXT NOT NULL, response TEXT, checkpoint TEXT, "
                "PRIMARY KEY(job_id, digest))"
            )
            initialize(con, policy, store._clock())

    def read(self, job_id, digest):
        with self.store._transaction() as con:
            return con.execute(
                "SELECT status,response,checkpoint FROM model_effects WHERE job_id=? AND digest=?",
                (job_id, digest),
            ).fetchone()

    def reserve_call(
        self, job_id: str, request_digest: str, estimated_usd: Decimal, budget: RunBudget, lease
    ) -> bool:
        if not valid_amount(estimated_usd):
            return False
        with self.store._transaction() as con:
            now = self.store._clock()
            if lease.job_id != job_id or not self.store._analysis_fenced(con, lease, now):
                return False
            if con.execute(
                "SELECT 1 FROM model_effects WHERE job_id=? AND digest=?", (job_id, request_digest)
            ).fetchone():
                return False
            rows = con.execute(
                "SELECT price FROM model_effects WHERE job_id=?", (job_id,)
            ).fetchall()
            try:
                prices = [Decimal(row[0]) for row in rows]
                if any(not valid_amount(price) for price in prices):
                    return False
                within_job = exact_total([*prices, estimated_usd]) <= exact_total(
                    [Decimal(str(budget.max_estimated_model_usd))]
                )
            except (ValueError, ArithmeticError):
                return False
            if len(rows) >= budget.max_model_calls or not within_job:
                return False
            admission = admit(con, self.policy, self.category, now, estimated_usd)
            if admission is None:
                return False
            con.execute(
                "INSERT INTO model_effects VALUES (?, ?, ?, 'reserved', NULL, NULL)",
                (job_id, request_digest, canonical(estimated_usd)),
            )
            con.execute(
                "INSERT INTO qm_portfolio_reservations VALUES (?,?,?,?,?,?)",
                (
                    job_id,
                    request_digest,
                    self.category,
                    admission[0],
                    canonical(estimated_usd),
                    admission[1],
                ),
            )
            return True

    def response(self, lease, digest, response):
        with self.store._transaction() as con:
            if not self.store._analysis_fenced(con, lease, self.store._clock()):
                return False
            return (
                con.execute(
                    "UPDATE model_effects SET status='completed',response=? "
                    "WHERE job_id=? AND digest=? AND status='reserved'",
                    (response, lease.job_id, digest),
                ).rowcount
                == 1
            )

    def checkpoint(self, lease, digest, record: AnalysisRecord):
        with self.store._transaction() as con:
            if not self.store._analysis_fenced(con, lease, self.store._clock()):
                return False
            return (
                con.execute(
                    "UPDATE model_effects SET checkpoint=? WHERE job_id=? AND digest=?",
                    (record.model_dump_json(), lease.job_id, digest),
                ).rowcount
                == 1
            )
