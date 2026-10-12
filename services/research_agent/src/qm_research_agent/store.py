"""PostgreSQL adapter for the frozen, already-reviewed local state machine.

The small SQL facade reuses state/artifact validation without SQLite storage.
A schema-scoped transaction advisory lock serializes two-slot admission and all
fenced writes across processes. No external effect occurs inside transactions.
"""

import re
import ssl
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pg8000.dbapi
from pydantic import SecretStr

from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import StoreUnavailable


class _Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        query = query.replace("?", "%s").replace("ORDER BY rowid", "ORDER BY sequence")
        query = query.replace(
            "INSERT INTO jobs VALUES",
            "INSERT INTO jobs(job_id, operator_id, idempotency_key, payload) VALUES",
        )
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        return cursor


def connect(dsn: SecretStr):
    """Explicit URI configuration, with TLS by default and no ambient secrets."""
    parsed = urlsplit(dsn.get_secret_value())
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or not parsed.username
        or not parsed.hostname
    ):
        raise ValueError("invalid PostgreSQL configuration")
    options = parse_qs(parsed.query)
    if set(options) - {"sslmode"} or parsed.fragment:
        raise ValueError("invalid PostgreSQL configuration")
    mode = options.get("sslmode", ["verify-full"])
    if mode not in (["disable"], ["verify-full"]):
        raise ValueError("invalid PostgreSQL TLS configuration")
    return pg8000.dbapi.connect(
        user=unquote(parsed.username),
        password=unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=unquote(parsed.path.lstrip("/")),
        timeout=5,
        ssl_context=False if mode == ["disable"] else ssl.create_default_context(),
    )


class PostgresJobStore(SQLiteJobStore):
    """Reuse the nine protocol methods, with PostgreSQL as sole authority.

    DSN must be injected explicitly. Schemas separate owned fixtures; production
    uses a dedicated private role/database, not a shared workstation database.
    """

    def __init__(
        self,
        dsn: SecretStr,
        *,
        lake_root: Path,
        artifact_root: Path,
        schema: str = "qm_research",
        clock=None,
    ):
        from datetime import UTC, datetime

        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("invalid service schema")
        if not isinstance(dsn, SecretStr):
            raise ValueError("DSN requires SecretStr")
        self._dsn, self._schema = dsn, schema
        self.lake_root, self.artifact_root = Path(lake_root), Path(artifact_root)
        self._clock = clock or (lambda: datetime.now(UTC))
        with self._transaction() as con:
            con.execute("CREATE TABLE IF NOT EXISTS qm_schema(version INTEGER NOT NULL)")
            versions = [
                tuple(row) for row in con.execute("SELECT version FROM qm_schema").fetchall()
            ]
            if not versions:
                con.execute("INSERT INTO qm_schema VALUES (1)")
            elif versions != [(1,)]:
                raise ValueError("unsupported service schema")
            con.execute(
                "CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, "
                "operator_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
                "payload TEXT NOT NULL, sequence BIGSERIAL UNIQUE, "
                "UNIQUE(operator_id, idempotency_key))"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS analysis_outbox ("
                "job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), lease TEXT, "
                "attempt INTEGER NOT NULL DEFAULT 0, sequence BIGSERIAL UNIQUE)"
            )

    def __repr__(self):
        return "<PostgresJobStore private>"

    @contextmanager
    def _transaction(self):
        connection = None
        try:
            connection = connect(self._dsn)
            con = _Connection(connection)
            con.execute("SET LOCAL statement_timeout='5s'")
            con.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                ("quantmesh-research:" + self._schema,),
            )
            # Schema is constrained to an ASCII identifier before interpolation.
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')
            con.execute(f'SET LOCAL search_path TO "{self._schema}"')
            yield con
            connection.commit()
        except (pg8000.dbapi.Error, OSError):
            raise StoreUnavailable("job store unavailable") from None
        finally:
            if connection:
                try:
                    connection.rollback()
                finally:
                    connection.close()

    def _all(self, con):
        return [
            self._decode(row[0])
            for row in con.execute("SELECT payload FROM jobs ORDER BY sequence").fetchall()
        ]

    def _artifacts(self, record, artifacts):
        import json

        refs = super()._artifacts(record, artifacts)
        report = next(ref for ref in refs if ref.kind == "report")
        envelope = json.loads(self._artifact_bytes(record, report))
        if (
            envelope.get("schema_version") != 1
            or envelope.get("implementation_digest") != record.implementation_digest
            or not isinstance(envelope.get("result"), dict)
        ):
            raise ValueError("report envelope invalid")
        return refs
