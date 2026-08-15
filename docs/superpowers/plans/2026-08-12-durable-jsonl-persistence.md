# Durable JSONL Persistence Module Implementation Plan

> **For agentic workers:** Follow TDD (red → green → refactor) for every behavior
> change; record the failing and passing command in the iteration ledger. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Consolidate the repeated ADR-0006 append-only JSONL discipline into one
shared `JsonlStore` seam, then migrate one registry (`ReportRegistry`) with
byte-identical round-trip and unchanged tests, without touching iteration 0021 or
any trading-safety invariant.

**Architecture:** A new `quantmesh.persistence` package owns the discipline every
registry used to reimplement: atomic temp+replace appends, fail-closed
line-attributed reads, duplicate identity refusal, hostile-path refusal (root must
be a directory, the store file a regular non-symlink file), and schema validation
through the caller's pydantic model. `scan` reports crash orphans (leftover temp
files) and hostile entries without deleting. Domain concerns — the report's lake
pin gate, journal replay validation, watchlist's venue-aware identity — stay in
their owning modules and plug into the store through a small, parameterized
constructor.

**Tech Stack:** Python 3.13, Pydantic v2, `quantmesh._fs.atomic_replace`, pytest, Ruff.

## Global Constraints

- Work only on branch `0022-durable-jsonl-persistence` (worktree
  `QuantMesh-iteration-0022`), created from `origin/main` at `d4aeed3`.
- Independent of iteration 0021: never depend on or modify
  `0021-trusted-data-fabric`; its soak HEAD stays `77141b9`.
- External venues stay read-only and execution stays paper-only. No credentials,
  live trading, paid services, or major architecture change.
- Byte-identical round-trip: the migrated registry writes exactly
  `record.model_dump_json() + "\n"` per record, same as before.
- Existing tests pass unchanged (or a reviewed equivalent); report registry tests
  in `tests/test_research_reports.py` are the equivalence oracle.
- One integration branch, tested commits at phase boundaries, one final PR.

## File Structure

- `src/quantmesh/persistence/__init__.py`: re-export `JsonlStore`.
- `src/quantmesh/persistence/jsonl.py`: the shared `JsonlStore` seam.
- `tests/test_persistence_jsonl.py`: the single-seam tests (crash, corruption,
  duplicate, hostile-path, schema, byte-identical round-trip).
- `src/quantmesh/research/reports.py`: first migrated registry.
- `docs/adr/0016-durable-jsonl-persistence-module.md`: the shared contract ADR.

---

### Task 1: Shared `JsonlStore` seam, tested before implemented

**Files:**
- Create: `src/quantmesh/persistence/__init__.py`
- Create: `src/quantmesh/persistence/jsonl.py`
- Create: `tests/test_persistence_jsonl.py`

**Interfaces:**

```python
class JsonlStore(Generic[Model]):
    def __init__(
        self,
        root: Path,
        *,
        filename: str,
        model: type[Model],
        label: str,                 # "report registry" (read-side error messages)
        id_label: str,              # "report" (share-a-<id_label>-id / <id_label> already recorded)
        key: Callable[[Model], str],
        error_type: type[Exception] = ValueError,
        extra_validate: Callable[[Model], None] | None = None,
    ) -> None: ...

    @property
    def path(self) -> Path: ...

    def read(self) -> list[Model]: ...        # fail-closed, line-attributed, duplicate-refusing
    def write(self, records: Iterable[Model]) -> None: ...  # atomic temp+replace full rewrite
    def append(self, record: Model) -> Model: ...          # duplicate-refusing atomic append
    def scan(self) -> list[Path]: ...          # report orphans + hostile entries; never delete
```

- [ ] **Step 1: Write the failing seam tests**

```python
class FixtureRecord(BaseModel):
    id: str
    value: int = 0

def test_round_trip_is_byte_identical(tmp_path):
    store = JsonlStore(tmp_path, filename="f.jsonl", model=FixtureRecord,
                       label="fixture store", id_label="fixture", key=lambda r: r.id)
    store.append(FixtureRecord(id="a", value=1))
    assert (tmp_path / "f.jsonl").read_text(encoding="utf-8") == '{"id":"a","value":1}\n'
    assert store.read() == [FixtureRecord(id="a", value=1)]
```

- [ ] **Step 2: Run and capture red**

Run: `python -m pytest -q tests/test_persistence_jsonl.py`
Expected: collection error — `quantmesh.persistence.jsonl` does not exist.

- [ ] **Step 3: Implement `JsonlStore`**

- [ ] **Step 4: Green + refactor**

---

### Task 2: Migrate `ReportRegistry`

**Files:**
- Edit: `src/quantmesh/research/reports.py`

**Interfaces:** `ReportRegistry` keeps its public `record` / `get` / `all` /
`resolve` / `resolve_pin` surface unchanged; `_append` and `_read` are replaced by a
private `JsonlStore` bound to `StrategyReport` with `label="report registry"`,
`id_label="report"`, `key=lambda r: r.id`. `record` keeps the lake pin gate
(`_require_pin`) as a domain precondition and delegates the duplicate check + atomic
append to `store.append`.

- [ ] **Step 1: Run existing tests unchanged as the equivalence oracle**
  `python -m pytest -q tests/test_research_reports.py`
- [ ] **Step 2: Migrate and re-run; require identical result**

---

### Task 3: ADR and iteration checkpoint

- [ ] Write `docs/adr/0016-durable-jsonl-persistence-module.md`.
- [ ] Append a dated checkpoint to `docs/iterations/0022-durable-jsonl-persistence.md`.
- [ ] Run full checks: `python -m pytest -q`, `ruff check src tests tools`, `git diff --check`.
