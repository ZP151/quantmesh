"""Compatibility wrapper for the packaged crash-safe daily soak runner."""

from quantmesh.ops.soak_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
