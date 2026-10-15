import pytest

from tools.research_service_gate import read_lock, require_postgres_fixture


def test_gate_refuses_unhashed_or_duplicate_lock(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text("pydantic==2.13.5\n")
    with pytest.raises(ValueError):
        read_lock(path)
    path.write_text(
        "pydantic==2.13.5 \\\n --hash=sha256:"
        + "a" * 64
        + "\npydantic==2.13.4 \\\n --hash=sha256:"
        + "b" * 64
        + "\n"
    )
    with pytest.raises(ValueError):
        read_lock(path)


def test_gate_requires_explicit_disposable_database():
    assert require_postgres_fixture({}) is False
    assert require_postgres_fixture({"DATABASE_URL": "existing-private-db"}) is False
    assert (
        require_postgres_fixture(
            {
                "QM_TEST_DISPOSABLE_POSTGRES_DSN": "fixture",
                "QM_TEST_DISPOSABLE_POSTGRES_ACK": "owned-disposable",
            }
        )
        is True
    )
