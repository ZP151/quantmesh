import pytest
@pytest.fixture(autouse=True)
def release_missing_policy_environment(monkeypatch):
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
