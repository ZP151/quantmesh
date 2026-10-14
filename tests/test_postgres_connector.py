"""PostgreSQL driver configuration stays strict and license-approved."""

import ssl

import pytest


def test_pg8000_connector_defaults_to_verified_tls_and_decodes_uri(monkeypatch):
    from quantmesh.research import job_store

    seen = {}

    def connect(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(job_store.pg8000.dbapi, "connect", connect)

    result = job_store._connect_postgres(
        "postgresql://research%40user:p%2Fass@db.internal:5544/mesh%20research"
    )

    assert result is not None
    assert seen["user"] == "research@user"
    assert seen["password"] == "p/ass"
    assert seen["host"] == "db.internal"
    assert seen["port"] == 5544
    assert seen["database"] == "mesh research"
    assert seen["timeout"] == 5
    assert isinstance(seen["ssl_context"], ssl.SSLContext)


def test_pg8000_connector_allows_unverified_tls_disable_only_for_loopback(monkeypatch):
    from quantmesh.research import job_store

    seen = {}
    monkeypatch.setattr(
        job_store.pg8000.dbapi,
        "connect",
        lambda **kwargs: seen.update(kwargs) or object(),
    )

    job_store._connect_postgres("postgres://user@127.0.0.1/db?sslmode=disable")
    assert seen["ssl_context"] is False

    with pytest.raises(ValueError, match="TLS"):
        job_store._connect_postgres("postgres://user@db.example/db?sslmode=disable")


@pytest.mark.parametrize(
    "dsn",
    (
        "postgresql://user@db.example/db?sslmode=require",
        "postgresql://user@db.example/db?unknown=1",
        "postgresql://user@db.example/db#fragment",
        "postgresql://@db.example/db",
        "postgresql://user@/db",
        "postgresql://user@db.example/",
    ),
)
def test_pg8000_connector_rejects_ambiguous_or_unsupported_uri(dsn):
    from quantmesh.research import job_store

    with pytest.raises(ValueError):
        job_store._connect_postgres(dsn)


def test_postgres_connection_facade_uses_cursor_and_preserves_transaction_api(monkeypatch):
    from quantmesh.research import job_store

    class Cursor:
        def execute(self, statement, parameters):
            self.statement = statement
            self.parameters = parameters

    class Connection:
        def cursor(self):
            return cursor

    cursor = Cursor()
    facade = job_store._PostgresConnection(Connection(), "quantmesh")
    result = facade.execute("SELECT * FROM jobs WHERE job_id=?", ("id",))

    assert result is cursor
    assert cursor.statement == 'SELECT * FROM "quantmesh".jobs WHERE job_id=%s'
    assert cursor.parameters == ("id",)


@pytest.mark.parametrize("failure_type", [OSError, "driver"])
def test_postgres_transaction_maps_driver_and_socket_errors(monkeypatch, tmp_path, failure_type):
    from quantmesh.research import job_store

    class BrokenConnection:
        def __init__(self):
            self.rolled_back = False
            self.closed = False

        def cursor(self):
            if failure_type == "driver":
                raise job_store.pg8000.dbapi.DatabaseError("synthetic driver failure")
            raise OSError("synthetic socket failure")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    connection = BrokenConnection()
    monkeypatch.setattr(job_store, "_connect_postgres", lambda dsn: connection)
    store = object.__new__(job_store.PostgresJobStore)
    store._pg8000 = job_store.pg8000
    store.dsn = "postgres://private"
    store.schema = "quantmesh"

    with pytest.raises(job_store.StoreUnavailable, match="job store unavailable"):
        with store._transaction():
            pass

    assert connection.rolled_back
    assert connection.closed


def test_postgres_transaction_sanitizes_rollback_and_close_failures(monkeypatch):
    from quantmesh.research import job_store

    class BrokenConnection:
        rolled_back = False
        closed = False

        def cursor(self):
            raise job_store.pg8000.dbapi.DatabaseError("original private driver detail")

        def rollback(self):
            self.rolled_back = True
            raise job_store.pg8000.dbapi.DatabaseError("rollback private detail")

        def close(self):
            self.closed = True
            raise OSError("close private detail")

    connection = BrokenConnection()
    monkeypatch.setattr(job_store, "_connect_postgres", lambda dsn: connection)
    store = object.__new__(job_store.PostgresJobStore)
    store._pg8000 = job_store.pg8000
    store.dsn = "postgres://private"
    store.schema = "quantmesh"

    with pytest.raises(job_store.StoreUnavailable, match="job store unavailable"):
        with store._transaction():
            pass

    assert connection.rolled_back
    assert connection.closed


def test_postgres_transaction_maps_close_failure_after_commit(monkeypatch):
    from quantmesh.research import job_store

    class Cursor:
        def execute(self, statement, parameters):
            return self

    class CloseFailureConnection:
        committed = False
        closed = False

        def cursor(self):
            return Cursor()

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True
            raise job_store.pg8000.dbapi.DatabaseError("private close detail")

    connection = CloseFailureConnection()
    monkeypatch.setattr(job_store, "_connect_postgres", lambda dsn: connection)
    store = object.__new__(job_store.PostgresJobStore)
    store._pg8000 = job_store.pg8000
    store.dsn = "postgres://private"
    store.schema = "quantmesh"

    with pytest.raises(job_store.StoreUnavailable, match="job store unavailable"):
        with store._transaction():
            pass

    assert connection.committed
    assert connection.closed
