import json

import pytest

from pokedb.output import generation_content_digest, generator_provenance
from pokedb.resources import DATA_SCHEMA_VERSION, RESOURCE_PATHS
from pokedb.utils.exceptions import DataValidationError
from pokedb.validation import validate_generation_output


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_ability_dataset(tmp_path, version_group_key):
    resources = {resource: [] for resource in RESOURCE_PATHS}
    resources["ability"] = [{"name": "stench", "id": 1}]
    _write_json(
        tmp_path / "index.json",
        {
            "metadata": {
                "schema_version": DATA_SCHEMA_VERSION,
                "generated_resources": ["ability"],
                "resource_provenance": {"ability": generator_provenance()},
                "versions": ["scarlet"],
                "source": "pokeapi",
                "api_base_url": "https://example.test/",
                "is_historical": False,
                "generation": 9,
                "version_groups": ["scarlet-violet"],
                "created_at": "2026-01-01T00:00:00+00:00",
                "counts": {
                    resource: (1 if resource == "ability" else 0)
                    for resource in RESOURCE_PATHS
                },
            },
            **resources,
        },
    )
    _write_json(
        tmp_path / "ability" / "stench.json",
        {
            "id": 1,
            "name": "stench",
            "source_url": "https://example.test/ability/1/",
            "is_main_series": True,
            "generation": "generation-iii",
            "effect": {version_group_key: "Current effect"},
            "short_effect": {version_group_key: "Current short effect"},
            "flavor_text": {},
        },
    )

    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["metadata"]["content_sha256"] = generation_content_digest(tmp_path)
    _write_json(index_path, index)


def test_generation_validation_accepts_consistent_ability_data(tmp_path):
    _write_ability_dataset(tmp_path, "scarlet-violet")

    validate_generation_output(tmp_path)


def test_generation_validation_rejects_rewritten_identifiers(tmp_path):
    _write_ability_dataset(tmp_path, "scarlet_violet")

    with pytest.raises(DataValidationError, match="version groups"):
        validate_generation_output(tmp_path)


@pytest.mark.parametrize(
    "mutation,message",
    [
        (
            lambda data: data["moves"]["machine"][0].update(level_learned_at=-1),
            "learnset",
        ),
        (lambda data: data["moves"]["machine"][0].update(name=None), "learnset"),
        (
            lambda data: data["moves"]["machine"][0].update(
                version_groups=["red-blue", "red-blue"]
            ),
            "version groups",
        ),
        (
            lambda data: data.update(held_items={"thunder-stone": {"red-blue": 101}}),
            "held item",
        ),
        (
            lambda data: data.update(
                held_items={"thunder-stone": {"unknown-version": 5}}
            ),
            "unknown versions",
        ),
        (lambda data: data.update(evolves_from_species="pichu"), "evolution parent"),
        (
            lambda data: data["forms"].append(
                {"name": "missing-form", "category": "cosmetic"}
            ),
            "unknown form",
        ),
        (
            lambda data: data["sprites"].update(
                front_default="https://example.test/current.png"
            ),
            "historical sprites",
        ),
    ],
)
def test_generation_validation_rejects_invalid_nested_pokemon(
    offline_api, offline_config, mutation, message
):
    import argparse

    from pokedb.pipeline import process_generation

    process_generation(
        argparse.Namespace(all=True, parsers=[], force=True),
        offline_config,
        offline_api,
        1,
        3,
    )
    root = offline_config.output_root / "gen1"
    path = root / "pokemon/default/pikachu.json"
    data = json.loads(path.read_text())
    mutation(data)
    _write_json(path, data)
    with pytest.raises(DataValidationError, match=message):
        validate_generation_output(root)


def test_empty_generated_catalog_is_rejected(tmp_path):
    _write_ability_dataset(tmp_path, "scarlet-violet")
    path = tmp_path / "index.json"
    index = json.loads(path.read_text())
    index["ability"] = []
    index["metadata"]["counts"]["ability"] = 0
    (tmp_path / "ability/stench.json").unlink()
    _write_json(path, index)
    with pytest.raises(DataValidationError, match="unexpectedly empty"):
        validate_generation_output(tmp_path)


def test_resource_digest_detects_undocumented_content_change(tmp_path):
    _write_ability_dataset(tmp_path, "scarlet-violet")
    path = tmp_path / "ability/stench.json"
    data = json.loads(path.read_text())
    data["effect"]["scarlet-violet"] = "changed"
    _write_json(path, data)
    with pytest.raises(DataValidationError, match="content_sha256"):
        validate_generation_output(tmp_path)
