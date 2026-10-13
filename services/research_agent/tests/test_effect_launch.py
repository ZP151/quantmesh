"""A real owned child verifies interpreter behavior without a provider call."""

import json
import sys

from qm_research_agent.bounded import bounded_complete

from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.ai.wire import ChatMessage, ModelRequest
from quantmesh.research.jobs import RunBudget


def test_owned_effect_child_does_not_generate_bytecode(tmp_path, monkeypatch):
    # An owned fixture module reports interpreter state before any provider or
    # unpickling. It shadows only this child's module; no runtime is qualified.
    package = tmp_path / "qm_research_agent"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "effect_worker.py").write_text(
        "import json, sys\n"
        "sys.stdin.buffer.read()\n"
        "print(json.dumps({'response': {'model_name': 'scripted-fixture', "
        "'content': json.dumps({'no_bytecode': sys.dont_write_bytecode})}, "
        "'scripted_seen': 1}))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    gateway = ModelGateway(ScriptedModelTransport([]), model_name="scripted-fixture")
    response = bounded_complete(
        gateway,
        ModelRequest(messages=[ChatMessage(role="user", content="owned fixture")]),
        RunBudget(timeout_seconds=5),
    )
    assert json.loads(response.content) == {"no_bytecode": True}
    assert not list(package.rglob("*.pyc"))
