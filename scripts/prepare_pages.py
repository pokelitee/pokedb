"""Add a discovery page to an unchanged published dataset snapshot."""

import argparse
import json
import re
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
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PokéDB JSON API</title>
</head>
<body>
  <h1>PokéDB JSON API</h1>
  <p>Generation indexes link to the resource catalogs. Use the same relative
  paths below this site to request individual JSON files.</p>
  <ul>{links}</ul>
  <p>Each index declares its dataset schema. Deploying this site does not
  regenerate data or upgrade older snapshots.</p>
  <p><a href="{escape(snapshot, quote=True)}">Published data commit</a>:
  <code>{data_commit}</code></p>
  <p><a href="https://github.com/pokelitee/pokedb">Source and documentation</a></p>
</body>
</html>
"""
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
