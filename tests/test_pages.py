import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "prepare_pages", Path(__file__).resolve().parents[1] / "scripts/prepare_pages.py"
)
PAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAGES)


def write_index(root, generation, schema):
    path = root / f"gen{generation}" / "index.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps({"metadata": {"generation": generation, "schema_version": schema}}),
        encoding="utf-8",
    )
    return path


def test_pages_preserves_snapshots_and_reports_their_actual_schema(tmp_path):
    newest = write_index(tmp_path, 9, 4)
    oldest = write_index(tmp_path, 1, 5)
    before = {path: path.read_bytes() for path in (newest, oldest)}
    PAGES.prepare_pages(tmp_path, "a" * 40)
    document = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert document.index("Generation 1") < document.index("Generation 9")
    assert "Generation 9</a> (schema 4)" in document
    assert "https://github.com/pokelitee/pokedb/tree/" + "a" * 40 in document
    assert (tmp_path / ".nojekyll").exists()
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert catalog == {
        "generations": [
            {"generation": 1, "schema": 5},
            {"generation": 9, "schema": 4},
        ],
        "commit": "a" * 40,
    }
    assert (tmp_path / "assets/app.js").is_file()
    assert (tmp_path / "assets/styles.css").is_file()
    assert "<!-- generation-links -->" not in document
    assert "<!-- snapshot-link -->" not in document
    assert all(path.read_bytes() == contents for path, contents in before.items())


def test_pages_rejects_mismatched_generation_metadata(tmp_path):
    path = write_index(tmp_path, 1, 5)
    path.write_text('{"metadata": {"generation": 2, "schema_version": 5}}')
    with pytest.raises(ValueError, match="generation metadata"):
        PAGES.prepare_pages(tmp_path, "a" * 40)


def test_pages_rejects_an_empty_snapshot(tmp_path):
    with pytest.raises(ValueError, match="No published"):
        PAGES.prepare_pages(tmp_path, "a" * 40)


def test_pages_rejects_an_invalid_commit(tmp_path):
    with pytest.raises(ValueError, match="Git commit SHA"):
        PAGES.prepare_pages(tmp_path, "not-a-commit")
