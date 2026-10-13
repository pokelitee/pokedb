"""Assemble the API explorer around an unchanged published dataset snapshot."""

import argparse
import json
import re
import shutil
from html import escape
from pathlib import Path


def prepare_pages(root: Path, data_commit: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", data_commit) is None:
        raise ValueError("data_commit must be a full lowercase Git commit SHA")
    generations = []
    for directory in root.iterdir():
        match = re.fullmatch(r"gen([1-9][0-9]*)", directory.name)
        if not directory.is_dir() or match is None:
            continue
        generation = int(match[1])
        index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
        metadata = index["metadata"]
        schema = metadata["schema_version"]
        if (
            metadata["generation"] != generation
            or type(schema) is not int
            or schema < 1
        ):
            raise ValueError(f"Invalid generation metadata in {directory}")
        generations.append((generation, schema))
    if not generations:
        raise ValueError("No published generation indexes found")
    links = "\n".join(
        f'<li><a href="gen{generation}/index.json">Generation {generation}</a>'
        f" (schema {schema})</li>"
        for generation, schema in sorted(generations)
    )
    snapshot = f"https://github.com/pokelitee/pokedb/tree/{data_commit}"
    template = Path(__file__).resolve().parents[1] / "site"
    shutil.copytree(template, root, dirs_exist_ok=True)
    document = (template / "index.html").read_text(encoding="utf-8")
    document = document.replace("<!-- generation-links -->", links).replace(
        "<!-- snapshot-link -->",
        f'<a href="{escape(snapshot, quote=True)}"><code>{data_commit}</code></a>',
    )
    (root / "catalog.json").write_text(
        json.dumps(
            {
                "generations": [
                    {"generation": generation, "schema": schema}
                    for generation, schema in sorted(generations)
                ],
                "commit": data_commit,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "index.html").write_text(document, encoding="utf-8")
    (root / ".nojekyll").touch()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--data-commit", required=True)
    args = parser.parse_args()
    prepare_pages(args.root, args.data_commit)


if __name__ == "__main__":
    main()
