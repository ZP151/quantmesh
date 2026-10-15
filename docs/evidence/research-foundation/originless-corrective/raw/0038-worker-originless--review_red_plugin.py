"""Controlled previous adapter overlay; no production-source mutation."""
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def previous_adapter(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[2] / 'src/quantmesh/research/worker_build.py'
    source = path.read_text()
    for guard in ('        if any(type(key) is not str for key in raw):\n            raise ValueError\n',
                  '    if any(type(key) is not str for key in namespace):\n        raise ValueError\n'):
        assert source.count(guard) == 1
        source = source.replace(guard, '')
    start = source.index('    try:\n        expected = named_code(')
    end = source.index('        raise ValueError from None', start) + len('        raise ValueError from None')
    old = source[start:end].splitlines()[1:-2]
    source = source[:start] + '\n'.join(line[4:] for line in old) + source[end:]
    overlay = tmp_path/'previous_worker_build.py'
    overlay.write_text(source)
    name = 'quantmesh.research.worker_build'
    module = types.ModuleType(name)
    module.__file__ = str(overlay)
    exec(compile(source, str(overlay), 'exec'), vars(module))
    monkeypatch.setitem(sys.modules, name, module)
