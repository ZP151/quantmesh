from fastapi.testclient import TestClient

from quantmesh.api.app import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["project"] == "QuantMesh"
    assert response.json()["paper_mode"] is True

