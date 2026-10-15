import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from qm_research_agent.app import create_app

from quantmesh.research.jobs import StoreUnavailable


def test_authenticated_build_health_retains_real_store_check(local):
    store, _, _ = local
    build = "a" * 40
    client = TestClient(
        create_app(
            store,
            operator_id="operator",
            token=SecretStr("fixture-private-token"),
            actual_build=build,
        )
    )
    assert client.get("/health").status_code == 401
    response = client.get("/health", headers={"Authorization": "Bearer fixture-private-token"})
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "advisory_only": True,
        "actual_build": build,
        "capabilities": {"worker": "pending_containment", "model": "unavailable"},
    }


def test_unqualified_factory_does_not_invent_a_build(local):
    store, _, _ = local
    client = TestClient(
        create_app(store, operator_id="operator", token=SecretStr("fixture-private-token"))
    )
    response = client.get("/health", headers={"Authorization": "Bearer fixture-private-token"})
    assert response.json()["actual_build"] is None


@pytest.mark.parametrize("build", ["a" * 39, "A" * 40, "g" * 40, "a" * 41, False, 0])
def test_factory_rejects_invalid_build_identity(local, build):
    store, _, _ = local
    with pytest.raises(ValueError, match="invalid actual build"):
        create_app(
            store,
            operator_id="operator",
            token=SecretStr("fixture-private-token"),
            actual_build=build,
        )


def test_build_health_does_not_mask_unavailable_database():
    class UnavailableStore:
        def get(self, *_):
            raise StoreUnavailable("synthetic-private-dsn-must-not-escape")

    client = TestClient(
        create_app(
            UnavailableStore(),
            operator_id="operator",
            token=SecretStr("fixture-private-token"),
            actual_build="b" * 40,
        )
    )
    response = client.get("/health", headers={"Authorization": "Bearer fixture-private-token"})
    assert response.status_code == 503
    assert response.json() == {"detail": "service_unavailable"}
    assert "synthetic-private" not in response.text
