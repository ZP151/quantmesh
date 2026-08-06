# Vendored Open-Source References

The directories below are Git submodules pinned to a specific upstream commit. They are grouped into two categories:

- `components/`: candidates for direct runtime integration behind QuantMesh adapters.
- `reference/`: complete applications and frameworks used for architecture study or isolated companion services.

Do not copy code from a submodule into `src/quantmesh/` without preserving its license and copyright headers. Prefer importing a package, adding an adapter, or running the project as a separate local service.

Update submodules intentionally and review the license before changing a pin:

```powershell
git submodule update --remote --merge
git submodule status
```

