"""Observed helper-object validation; not full image/numerical admission."""

import hashlib
import importlib
import sys
import types
import typing
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.version_info[:2] != (3, 12), reason="CPython3.12 helper shape")


def _api():
    return importlib.import_module("quantmesh.research.worker_build")


def _measured_typing():
    path = Path(typing.__file__)
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("name", ["typing.io", "typing.re"])
def test_genuine_measured_typing_alias_passes(name):
    assert _api()._originless_helper(name, sys.modules[name], sys.modules, _measured_typing())


@pytest.mark.parametrize(
    "change",
    [
        "replacement",
        "metaclass",
        "extra_function",
        "member",
        "all",
        "code",
        "external_typing",
        "descriptor",
    ],
)
def test_typing_alias_changes_refuse(monkeypatch, change):
    alias = sys.modules["typing.io"]
    measured = _measured_typing()
    modules = dict(sys.modules)
    if change == "replacement":
        alias = object()
    elif change == "metaclass":
        alias = type("io", (), {})
    elif change == "extra_function":
        monkeypatch.setattr(alias, "foreign", lambda: None, raising=False)
    elif change == "member":
        monkeypatch.setattr(alias, "IO", object())
    elif change == "all":
        monkeypatch.setattr(alias, "__all__", ["IO"])
    elif change == "code":
        monkeypatch.setattr(typing._DeprecatedType, "__getattribute__", lambda self, name: None)
    elif change == "external_typing":
        measured = {}
    elif change == "descriptor":
        monkeypatch.setattr(alias, "__weakref__", object.__dict__["__class__"])
    with pytest.raises(ValueError):
        _api()._originless_helper("typing.io", alias, modules, measured)


def _runtime():
    module = types.ModuleType("cython_runtime")
    module.__package__ = None
    return module


@pytest.mark.parametrize("setting", [None, True, False])
def test_plain_data_only_cython_runtime_passes(setting):
    module = _runtime()
    if setting is not None:
        module.cline_in_traceback = setting
    assert _api()._originless_helper("cython_runtime", module, {}, {})


@pytest.mark.parametrize("payload", [1, object(), lambda: None, property(lambda self: None)])
def test_runtime_arbitrary_payload_refuses(payload):
    module = _runtime()
    module.cline_in_traceback = payload
    with pytest.raises(ValueError):
        _api()._originless_helper("cython_runtime", module, {}, {})


@pytest.mark.parametrize("key", ["__file__", "__path__", "__getattr__", "foreign"])
def test_runtime_extra_members_refuse(key):
    module = _runtime()
    vars(module)[key] = object()
    with pytest.raises(ValueError):
        _api()._originless_helper("cython_runtime", module, {}, {})


def test_module_subclass_hooks_are_not_invoked():
    class Dangerous(types.ModuleType):
        def __getattribute__(self, name):
            raise AssertionError("untrusted module hook invoked")

    with pytest.raises(ValueError):
        _api()._originless_helper("cython_runtime", Dangerous("cython_runtime"), {}, {})


@pytest.mark.parametrize("kind", ["cython_runtime", "typing.io"])
def test_nonstring_dictionary_keys_refuse_without_hooks(kind):
    class HostileKey(str):
        armed = False
        __hash__ = str.__hash__

        def __eq__(self, other):
            if self.armed:
                raise AssertionError("untrusted equality hook invoked")
            return str.__eq__(self, other)

    module = _runtime() if kind == "cython_runtime" else types.ModuleType("typing")
    field = "__name__" if kind == "cython_runtime" else "__file__"
    vars(module).pop(field, None)
    key = HostileKey(field)
    vars(module)[key] = "cython_runtime" if kind == "cython_runtime" else typing.__file__
    key.armed = True
    modules = {} if kind == "cython_runtime" else {"typing": module}
    candidate = module if kind == "cython_runtime" else sys.modules[kind]
    with pytest.raises(ValueError):
        _api()._originless_helper(kind, candidate, modules, {})


def test_measured_invalid_source_has_sanitized_rejection(tmp_path, monkeypatch):
    source = tmp_path / "typing.py"
    source.write_bytes(b"def invalid(\n")
    monkeypatch.setattr(typing, "__file__", str(source))
    files = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    with pytest.raises(ValueError) as failure:
        _api()._originless_helper("typing.io", sys.modules["typing.io"], sys.modules, files)
    assert str(failure.value) == ""


def test_unknown_or_native_cache_is_not_exempted():
    for name in ("unknown", "_cython_3_1_4", "_cython_3_2_9"):
        assert not _api()._originless_helper(name, types.ModuleType(name), {}, {})
