import re
from pathlib import Path

from pokedb.resources import DATA_SCHEMA_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_documented_schema_version_matches_runtime_contract():
    documents = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / ".github" / "data-branch-README.md",
    ]

    for path in documents:
        contents = path.read_text(encoding="utf-8")
        pattern = rf"schema version `?{DATA_SCHEMA_VERSION}`?"
        assert re.search(pattern, contents, re.IGNORECASE), path


def test_static_api_examples_use_the_pokemon_category_directory():
    contents = (PROJECT_ROOT / ".github" / "data-branch-README.md").read_text(
        encoding="utf-8"
    )
    assert "/gen9/pokemon/default/pikachu.json" in contents
    assert "/gen9/pokemon/pikachu.json" not in contents


def test_data_workflow_regenerates_every_generation_and_documentation():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "update-data.yaml").read_text(
        encoding="utf-8"
    )

    assert "--all --gen all --no-cache --force" in workflow
    assert ".github/data-branch-README.md" in workflow
    assert not (PROJECT_ROOT / ".github/workflows/regenerate-data.yaml").exists()
    assert not (PROJECT_ROOT / ".github/workflows/publish-wiki.yaml").exists()
