import argparse
import re
from datetime import date
from pathlib import Path

APPEND_MARKER = "<!-- quantmesh-iterations:append-above -->"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("Iteration title must contain at least one ASCII letter or number")
    return slug


def next_iteration_id(iterations_dir: Path) -> str:
    ids = [
        int(path.name[:4])
        for path in iterations_dir.glob("[0-9][0-9][0-9][0-9]-*.md")
        if path.name[:4].isdigit()
    ]
    return f"{max(ids, default=0) + 1:04d}"


def create_iteration(
    root: Path,
    title: str,
    owner: str,
    status: str = "planned",
    started: str | None = None,
) -> Path:
    iterations_dir = root / "docs" / "iterations"
    template_path = iterations_dir / "ITERATION_TEMPLATE.md"
    index_path = iterations_dir / "INDEX.md"

    if not template_path.exists() or not index_path.exists():
        raise FileNotFoundError("Run this command from a QuantMesh repository checkout")

    iteration_id = next_iteration_id(iterations_dir)
    started_on = started or date.today().isoformat()
    destination = iterations_dir / f"{iteration_id}-{slugify(title)}.md"

    content = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{ID}}": iteration_id,
        "{{TITLE}}": title,
        "{{STATUS}}": status,
        "{{STARTED}}": started_on,
        "{{OWNER}}": owner,
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    destination.write_text(content, encoding="utf-8")

    index = index_path.read_text(encoding="utf-8")
    if APPEND_MARKER not in index:
        destination.unlink(missing_ok=True)
        raise ValueError(f"Missing iteration append marker in {index_path}")

    row = f"| {iteration_id} | {status} | {started_on} |  | {title} |  |\n\n"
    index_path.write_text(index.replace(APPEND_MARKER, row + APPEND_MARKER), encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and index a QuantMesh iteration record")
    parser.add_argument("title", help="Iteration title")
    parser.add_argument("--owner", default="unassigned")
    parser.add_argument("--status", default="planned", choices=["planned", "active", "blocked"])
    parser.add_argument("--started")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    destination = create_iteration(
        root=args.root.resolve(),
        title=args.title,
        owner=args.owner,
        status=args.status,
        started=args.started,
    )
    print(destination)


if __name__ == "__main__":
    main()

