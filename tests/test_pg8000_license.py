"""The PostgreSQL driver closure uses pg8000 without weakening license policy."""

from importlib import metadata

from tools import license_review


def test_postgres_runtime_closure_uses_pg8000_and_keeps_lgpl_classification():
    closure = license_review.read_closure()
    assert closure["pg8000"] == "1.31.5"
    assert "psycopg" not in closure
    assert "psycopg-binary" not in closure
    assert license_review._from_expression("LGPL-3.0-only") == "LGPL-3.0-only"


def test_pg8000_pinned_metadata_classifies_as_bsd_three_clause():
    distribution = metadata.distribution("pg8000")
    assert distribution.version == "1.31.5"
    assert license_review.classify(distribution) == "BSD-3-Clause"


def test_pg8000_scram_dependency_classifies_the_exact_mit_zero_declaration():
    distribution = metadata.distribution("scramp")
    assert distribution.version == "1.4.17"
    assert license_review.classify(distribution) == "MIT-0"
