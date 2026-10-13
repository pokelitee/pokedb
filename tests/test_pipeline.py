import argparse
import json

import pytest
from conftest import BASE, ref

from pokedb import __main__
from pokedb.pipeline import process_generation
from pokedb.resources import DATA_SCHEMA_VERSION, RESOURCE_INDEX_KEYS
from pokedb.utils.exceptions import ConfigurationError, ParserExecutionError
from pokedb.validation import validate_generation_output


def arguments(*parsers):
    return argparse.Namespace(all=not parsers, parsers=list(parsers), force=True)


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*.json")}


def test_offline_cli_generates_all_catalogs(monkeypatch, offline_api, offline_config):
    monkeypatch.setattr(__main__, "load_config", lambda _: offline_config)
    monkeypatch.setattr(__main__, "ApiClient", lambda _: offline_api)
    monkeypatch.setattr("sys.argv", ["pokedb", "--all", "--gen", "1", "--force"])
    __main__.main()
    root = offline_config.output_root / "gen1"
    validate_generation_output(root)
    index = json.loads((root / "index.json").read_text())
    assert index["metadata"]["schema_version"] == DATA_SCHEMA_VERSION
    assert set(index["metadata"]["generated_resources"]) == set(RESOURCE_INDEX_KEYS)
    assert index["metadata"]["counts"]["ability"] == 0
    move = json.loads((root / "move/thunderbolt.json").read_text())
    assert move["machine"] == {"red-blue": "tm24", "yellow": "tm25"}
    pikachu = json.loads((root / "pokemon/default/pikachu.json").read_text())
    assert pikachu["evolves_from_species"] is None
    costume = json.loads((root / "pokemon/cosmetic/pikachu-costume.json").read_text())
    assert costume["sprites"] == {}


@pytest.mark.parametrize(
    "failed_url",
    [
        f"{BASE}machine/red-blue/",
        f"{BASE}evolution-chain/1/",
        ref("pokemon-form", "pikachu-costume")["url"],
        ref("pokemon-form", "pikachu")["url"],
    ],
)
def test_fetch_failure_preserves_published_output(
    offline_api, offline_config, failed_url
):
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    before = snapshot(root)
    offline_api.failures.add(failed_url)
    with pytest.raises(ParserExecutionError):
        process_generation(arguments(), offline_config, offline_api, 1, 3)
    assert snapshot(root) == before
    assert not (root.parent / ".gen1.staging").exists()


def test_partial_regeneration_preserves_other_catalogs(offline_api, offline_config):
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    before = snapshot(root)
    offline_api.responses[ref("move", "thunderbolt")["url"]]["power"] = 95
    process_generation(arguments("move"), offline_config, offline_api, 1, 3)
    after = snapshot(root)
    assert all(
        after[name] == contents
        for name, contents in before.items()
        if name.parts[0] not in {"move", "index.json"}
    )
    assert (
        after[next(name for name in before if str(name).endswith("thunderbolt.json"))]
        != before[
            next(name for name in before if str(name).endswith("thunderbolt.json"))
        ]
    )
    validate_generation_output(root)


def test_partial_run_cannot_mix_schema_versions(offline_api, offline_config):
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    index_path = root / "index.json"
    index = json.loads(index_path.read_text())
    index["metadata"]["schema_version"] = DATA_SCHEMA_VERSION - 1
    index_path.write_text(json.dumps(index))
    before = snapshot(root)
    with pytest.raises(ConfigurationError, match="Partial regeneration"):
        process_generation(arguments("move"), offline_config, offline_api, 1, 3)
    assert snapshot(root) == before


def test_identical_full_run_preserves_timestamp_and_contents(
    offline_api, offline_config
):
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    before = snapshot(root)
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    assert snapshot(root) == before


def test_partial_generation_declares_omitted_catalogs(offline_api, offline_config):
    process_generation(arguments("pokemon"), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    validate_generation_output(root)
    index = json.loads((root / "index.json").read_text())
    assert set(index["metadata"]["generated_resources"]) == {
        "pokemon",
        "variant",
        "transformation",
        "cosmetic",
    }
    assert index["item"] == []


def test_partial_generation_retains_original_catalog_provenance(
    monkeypatch, offline_api, offline_config
):
    monkeypatch.setenv("POKEDB_GENERATOR_COMMIT", "a" * 40)
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    monkeypatch.setenv("POKEDB_GENERATOR_COMMIT", "b" * 40)
    process_generation(arguments("move"), offline_config, offline_api, 1, 3)
    index = json.loads((offline_config.output_root / "gen1/index.json").read_text())
    provenance = index["metadata"]["resource_provenance"]
    assert provenance["move"]["commit"] == "b" * 40
    assert provenance["pokemon"]["commit"] == "a" * 40


def test_full_regeneration_can_replace_corrupt_index(offline_api, offline_config):
    root = offline_config.output_root / "gen1"
    root.mkdir(parents=True)
    (root / "index.json").write_text("not json")
    process_generation(arguments(), offline_config, offline_api, 1, 3)
    validate_generation_output(root)


def test_offline_cli_generates_every_generation(
    monkeypatch, offline_api, offline_config
):
    monkeypatch.setattr(__main__, "load_config", lambda _: offline_config)
    monkeypatch.setattr(__main__, "ApiClient", lambda _: offline_api)
    monkeypatch.setattr("sys.argv", ["pokedb", "--all", "--gen", "all", "--force"])
    __main__.main()
    for generation in range(1, 4):
        validate_generation_output(offline_config.output_root / f"gen{generation}")
    latest = json.loads((offline_config.output_root / "gen3/index.json").read_text())
    assert latest["metadata"]["is_historical"] is False
    pichu = json.loads(
        (offline_config.output_root / "gen2/pokemon/default/pichu.json").read_text()
    )
    assert pichu["evolves_from_species"] is None


def test_validation_failure_preserves_published_output(offline_api, offline_config):
    from pokedb.utils.exceptions import DataValidationError

    process_generation(arguments(), offline_config, offline_api, 1, 3)
    root = offline_config.output_root / "gen1"
    before = snapshot(root)
    offline_api.responses[ref("move", "thunderbolt")["url"]]["power"] = "invalid"
    with pytest.raises(DataValidationError, match="numeric power"):
        process_generation(arguments(), offline_config, offline_api, 1, 3)
    assert snapshot(root) == before
