"""Check saved actual observations; does not execute Docker, SSH or numeric code."""

import ast
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent
index = json.loads((root / "SHA256.json").read_bytes())
for name, pin in index.items():
    raw = (root / name).read_bytes()
    assert len(raw) == pin["bytes"]
    assert hashlib.sha256(raw).hexdigest() == pin["sha256"]

expected = {
    "schema-receipt.json": "e603a5cb4c6c8389957849dba0351cbb6f897abe83d2dd71a5cffe8c1819a9cf",
    "fd-diagnostic-receipt.json": (
        "0d7413602013379fd61e40475d5361fad96348232396fdd8544a25cb1a53a61a"
    ),
    "sealed-receipt.json": "50334ba2a5c2e0e8004442c983897d84a298c55c1e103579217934edaa32e84b",
    "sealed-output.json": "d1238efdfc097c1dc2da6bb55bc497172e75efcbfcee54f507cbd3a45244612f",
    "probe-sealed-fd.py": "93da1b0e24bc9a8060ffe5679de7374646d75e36eb9702ae0f08b859f0de1770",
    "sealed-child.py": "071fd24bbf48c6c2998e2b51d99c9d46ff20db2cfb5438693ae485df54d35b5e",
}
assert all(index[name]["sha256"] == value for name, value in expected.items())
receipt = json.loads((root / "sealed-receipt.json").read_bytes())
output = json.loads((root / "sealed-output.json").read_bytes())
assert receipt["observation"] == output
assert receipt["exit"] == receipt["actual_child_exit"] == 0
assert not receipt["actual_oom"] and receipt["actual_pid"] == 0
assert receipt["owned_container_removed"]
assert receipt["final_engine"] == {
    "ID": "cfe71bf3-9059-4059-887d-ac401f2283ec",
    "Images": 2,
    "Containers": 0,
}
assert receipt["child_source_sha256"] == expected["sealed-child.py"]
state = dict(
    Running=False,
    ExitCode=receipt["actual_child_exit"],
    Pid=receipt["actual_pid"],
    OOMKilled=receipt["actual_oom"],
    StartedAt=receipt["actual_started_at"],
    FinishedAt=receipt["actual_finished_at"],
)
tree = ast.parse((root / "probe-sealed-fd.py").read_bytes())
functions = [
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name in ("require", "validate_observation", "validate_sealed_observation")
]
assert len(functions) == 3
scope = {"re": re, "datetime": datetime}
exec(compile(ast.Module(body=functions, type_ignores=[]), "saved-validators", "exec"), scope)
scope["validate_observation"]({"State": state}, output)
scope["validate_sealed_observation"](output)
schema = json.loads((root / "schema-output.json").read_bytes())
assert all(
    output[key] == schema[key]
    for key in ("logical_schema", "physical_schema", "rows", "native_module_sha256")
)
for name in ("fd-failed-receipt.json", "fd-diagnostic-receipt.json"):
    failed = json.loads((root / name).read_bytes())
    assert failed["exit"] == failed["actual_child_exit"] == 1
    assert failed["owned_container_removed"] and failed["actual_pid"] == 0
    assert not failed["actual_oom"] and failed["final_engine"] == receipt["final_engine"]
assert receipt["whole_host_introduced_bytes"] <= 5_000_000_000
assert receipt["host_free_bytes"] >= 50_000_000_000
assert all(
    receipt[key] is False
    for key in (
        "native_admission",
        "numerical_certificate",
        "kernel_profile_qualified",
        "production_services_enabled",
        "full_option_A_complete",
    )
)
print(json.dumps(dict(saved_actual_fields_checked=True, native_execution=False, cases=9)))
