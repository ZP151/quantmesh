"""Pure routing-context checks; no fixture I/O or numeric/native execution."""

import importlib
import importlib.util
from pathlib import Path

import pytest


def scope_module():
    name = "quantmesh.data._fixture_read_scope"
    assert importlib.util.find_spec(name) is not None, "fixture read scope absent"
    return importlib.import_module(name)


def test_outside_job_has_no_reader():
    assert scope_module().current_reader(Path("fixture"), "sample") is None


def test_scoped_reader_matches_root_and_dataset_and_cleans_up():
    module = scope_module()
    root = Path("fixture").absolute()
    reader = object()
    with module.bind_reader(root, "sample", reader):
        assert module.current_reader(root, "sample") is reader
        assert module.current_reader(Path("fixture"), "sample") is reader
    assert module.current_reader(root, "sample") is None


@pytest.mark.parametrize("change", ["root", "dataset"])
def test_active_scope_refuses_other_root_or_dataset_without_fallback(change):
    module = scope_module()
    root = Path("fixture").absolute()
    with module.bind_reader(root, "sample", object()):
        with pytest.raises(ValueError, match="fixture_read_scope_invalid"):
            module.current_reader(
                root / "other" if change == "root" else root,
                "other" if change == "dataset" else "sample",
            )


def test_consumer_error_resets_context_and_is_preserved():
    module = scope_module()
    root = Path("fixture").absolute()
    error = RuntimeError("consumer failure")
    with pytest.raises(RuntimeError) as caught:
        with module.bind_reader(root, "sample", object()):
            raise error
    assert caught.value is error
    assert module.current_reader(root, "sample") is None


def test_nested_scope_refuses_without_displacing_outer_reader():
    module = scope_module()
    root = Path("fixture").absolute()
    reader = object()
    with module.bind_reader(root, "sample", reader):
        with pytest.raises(ValueError, match="fixture_read_scope_invalid"):
            with module.bind_reader(root, "sample", object()):
                pytest.fail("nested scope admitted")
        assert module.current_reader(root, "sample") is reader


class Hostile:
    def callback(self, *args):
        pytest.fail("foreign object callback ran")

    __str__ = __eq__ = __bool__ = callback


@pytest.mark.parametrize("which", ["root", "dataset", "empty_reader", "dotdot"])
def test_binding_refuses_invalid_inputs_before_foreign_callbacks(which):
    module = scope_module()
    root = Path("fixture").absolute()
    values = dict(root=root, dataset="sample", reader=object())
    if which == "empty_reader":
        values["reader"] = None
    elif which == "dotdot":
        values["root"] = root / ".." / "other"
    else:
        values[which] = Hostile()
    with pytest.raises(ValueError, match="fixture_read_scope_invalid"):
        with module.bind_reader(**values):
            pytest.fail("invalid binding admitted")


@pytest.mark.parametrize("which", ["root", "dataset"])
def test_active_lookup_rejects_foreign_inputs_without_callbacks(which):
    module = scope_module()
    root = Path("fixture").absolute()
    with module.bind_reader(root, "sample", object()):
        with pytest.raises(ValueError, match="fixture_read_scope_invalid"):
            module.current_reader(
                Hostile() if which == "root" else root,
                Hostile() if which == "dataset" else "sample",
            )
