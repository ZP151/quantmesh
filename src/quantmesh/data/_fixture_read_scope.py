"""Private job-local data routing; never native admission or order authority."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from quantmesh.data.layout import validate_dataset_name

_PATH_TYPE = type(Path())
_reader: ContextVar[tuple[Path, str, object] | None] = ContextVar(
    "quantmesh_fixture_read_scope", default=None
)


def _invalid() -> None:
    raise ValueError("fixture_read_scope_invalid")


def _key(root: Path, dataset: str) -> tuple[Path, str]:
    if type(root) is not _PATH_TYPE or type(dataset) is not str:
        _invalid()
    if ".." in root.parts:
        _invalid()
    try:
        validate_dataset_name(dataset)
    except ValueError:
        _invalid()
    return root.absolute(), dataset


def current_reader(root: Path, dataset: str) -> object | None:
    """An active job scope refuses mismatches instead of falling back to raw I/O."""
    binding = _reader.get()
    if binding is None:
        return None
    if _key(root, dataset) != binding[:2]:
        _invalid()
    return binding[2]


@contextmanager
def bind_reader(root: Path, dataset: str, reader: object):
    """Bind one trusted internal reader across a job's complete compute/repin flow.

    Only the verified child caller will activate this context. The context itself
    is a routing mechanism and grants no runtime, image or native exception.
    """
    if _reader.get() is not None or reader is None:
        _invalid()
    key = _key(root, dataset)
    token = _reader.set((*key, reader))
    try:
        yield reader
    finally:
        _reader.reset(token)
