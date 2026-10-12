"""Durable effects and checkpoint; reservations precede provider invocation.

Uses the authoritative store's transaction (PostgreSQL in service mode).
Local SQLite use is only the explicitly-labelled offline boundary witness.
"""

from decimal import Decimal

from quantmesh.research.jobs import AnalysisRecord, RunBudget


class EffectLedger:
    def __init__(self, store):
        self.store = store
        with store._transaction() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS model_effects ("
                "job_id TEXT REFERENCES jobs(job_id), digest TEXT, price TEXT NOT NULL, "
                "status TEXT NOT NULL, response TEXT, checkpoint TEXT, "
                "PRIMARY KEY(job_id, digest))"
            )

    def read(self, job_id, digest):
        with self.store._transaction() as con:
            return con.execute(
                "SELECT status,response,checkpoint FROM model_effects WHERE job_id=? AND digest=?",
                (job_id, digest),
            ).fetchone()

    def reserve_call(
        self, job_id: str, request_digest: str, estimated_usd: Decimal, budget: RunBudget, lease
    ) -> bool:
        if estimated_usd is None or not estimated_usd.is_finite() or estimated_usd < 0:
            return False
        with self.store._transaction() as con:
            if lease.job_id != job_id or not self.store._analysis_fenced(
                con, lease, self.store._clock()
            ):
                return False
            if con.execute(
                "SELECT 1 FROM model_effects WHERE job_id=? AND digest=?", (job_id, request_digest)
            ).fetchone():
                return False
            rows = con.execute(
                "SELECT price FROM model_effects WHERE job_id=?", (job_id,)
            ).fetchall()
            if len(rows) >= budget.max_model_calls or sum(
                (Decimal(row[0]) for row in rows), Decimal(0)
            ) + estimated_usd > Decimal(str(budget.max_estimated_model_usd)):
                return False
            con.execute(
                "INSERT INTO model_effects VALUES (?, ?, ?, 'reserved', NULL, NULL)",
                (job_id, request_digest, str(estimated_usd)),
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
