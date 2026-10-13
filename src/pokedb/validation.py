"""Runtime validation for generated generation datasets."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .output import generation_content_digest
from .resources import DATA_SCHEMA_VERSION, RESOURCE_INDEX_KEYS, RESOURCE_PATHS
from .utils.exceptions import DataValidationError

VERSIONED_MOVE_FIELDS = {
    "accuracy",
    "power",
    "pp",
    "effect_chance",
    "type",
    "effect",
    "short_effect",
}
MODERN_STAT_NAMES = {
    "hp",
    "attack",
    "defense",
    "special-attack",
    "special-defense",
    "speed",
}
GENERATION_ONE_STAT_NAMES = {
    "hp",
    "attack",
    "defense",
    "special",
    "speed",
}
STAT_NAMES = MODERN_STAT_NAMES | GENERATION_ONE_STAT_NAMES


def _is_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-z0-9]+(?:-+[a-z0-9]+)*", value) is not None
    )


def _validate_groups(value: Any, allowed: set[str], path: Path, field: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or not all(_is_identifier(group) for group in value)
        or len(value) != len(set(value))
        or not set(value) <= allowed
    ):
        raise DataValidationError(f"{path}: {field} has invalid version groups")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_optional(value: Any, expected_type: type) -> bool:
    return value is None or isinstance(value, expected_type)


def _require_fields(data: dict[str, Any], fields: set[str], path: Path) -> None:
    missing = fields - set(data)
    if missing:
        raise DataValidationError(f"{path}: missing fields {sorted(missing)}")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise DataValidationError(
            f"Cannot read valid JSON from {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise DataValidationError(f"Expected a JSON object in {path}")
    return value


def _validate_version_map(
    data: dict[str, Any], field: str, version_groups: set[str], path: Path
) -> None:
    value = data.get(field)
    if not isinstance(value, dict) or set(value) != version_groups:
        raise DataValidationError(
            f"{path}: {field} must contain exactly the generation version groups"
        )


def _validate_common(
    data: dict[str, Any], expected_name: str, api_base_url: str, path: Path
) -> None:
    if not _is_identifier(expected_name) or data.get("name") != expected_name:
        raise DataValidationError(
            f"{path}: name must match its filename ({expected_name!r})"
        )
    if not _is_int(data.get("id")) or data["id"] <= 0:
        raise DataValidationError(f"{path}: id must be a positive integer")
    source_url = data.get("source_url")
    if not isinstance(source_url, str) or not source_url.startswith(api_base_url):
        raise DataValidationError(
            f"{path}: source_url must use the configured PokéAPI base URL"
        )


def _validate_unverified_historical_fields(
    data: dict[str, Any],
    is_historical: bool,
    expected_fields: set[str],
    path: Path,
) -> None:
    unverified = data.get("unverified_historical_fields")
    if not isinstance(unverified, list) or not all(
        isinstance(field, str) for field in unverified
    ):
        raise DataValidationError(
            f"{path}: unverified_historical_fields must be a list of strings"
        )
    if set(unverified) - expected_fields:
        raise DataValidationError(
            f"{path}: unverified_historical_fields contains unexpected fields"
        )
    if is_historical:
        if set(unverified) != expected_fields:
            raise DataValidationError(
                f"{path}: historical record must flag all unverified fields"
            )
    elif unverified:
        raise DataValidationError(
            f"{path}: unverified_historical_fields must be empty when not historical"
        )


def _validate_ability(
    data: dict[str, Any],
    version_groups: set[str],
    _generation: int,
    _is_historical: bool,
    path: Path,
) -> None:
    _require_fields(
        data,
        {"is_main_series", "generation", "effect", "short_effect", "flavor_text"},
        path,
    )
    if not isinstance(data["is_main_series"], bool) or not isinstance(
        data["generation"], str
    ):
        raise DataValidationError(f"{path}: invalid ability flags or generation")
    for field in ("effect", "short_effect"):
        _validate_version_map(data, field, version_groups, path)
        if any(
            value is not None and not isinstance(value, str)
            for value in data[field].values()
        ):
            raise DataValidationError(f"{path}: {field} values must be strings or null")
    if not isinstance(data["flavor_text"], dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in data["flavor_text"].items()
    ):
        raise DataValidationError(f"{path}: flavor_text must be an object")


def _validate_move(
    data: dict[str, Any],
    version_groups: set[str],
    generation: int,
    is_historical: bool,
    path: Path,
) -> None:
    _require_fields(
        data,
        VERSIONED_MOVE_FIELDS
        | {
            "priority",
            "damage_class",
            "target",
            "generation",
            "flavor_text",
            "stat_changes",
            "machine",
            "metadata",
            "unverified_historical_fields",
        },
        path,
    )
    _validate_version_map(data, "machine", version_groups, path)
    if any(
        value is not None and not _is_identifier(value)
        for value in data["machine"].values()
    ):
        raise DataValidationError(f"{path}: invalid machine identifiers")
    for field in VERSIONED_MOVE_FIELDS:
        _validate_version_map(data, field, version_groups, path)
    for field in ("accuracy", "power", "pp", "effect_chance"):
        if any(
            value is not None and not _is_int(value) for value in data[field].values()
        ):
            raise DataValidationError(f"{path}: invalid numeric {field} values")
    for field in ("type", "effect", "short_effect"):
        if any(
            value is not None and not isinstance(value, str)
            for value in data[field].values()
        ):
            raise DataValidationError(f"{path}: invalid textual {field} values")
    _validate_unverified_historical_fields(
        data, is_historical, {"priority", "target", "metadata", "stat_changes"}, path
    )
    if is_historical:
        damage_class = data.get("damage_class")
        if generation < 4:
            if damage_class not in {None, "physical", "special", "status"}:
                raise DataValidationError(f"{path}: invalid derived damage class")
        elif damage_class is not None:
            raise DataValidationError(f"{path}: historical damage_class must be null")
    if not _is_int(data.get("priority")):
        raise DataValidationError(f"{path}: priority must be an integer")
    if not all(
        _is_optional(data[field], str)
        for field in ("damage_class", "target", "generation")
    ):
        raise DataValidationError(f"{path}: invalid move identifiers")
    if not isinstance(data["flavor_text"], dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in data["flavor_text"].items()
    ):
        raise DataValidationError(f"{path}: invalid move flavor_text")
    if not isinstance(data.get("metadata"), dict) or not isinstance(
        data.get("stat_changes"), list
    ):
        raise DataValidationError(f"{path}: invalid move metadata or stat_changes")


def _validate_item(
    data: dict[str, Any],
    version_groups: set[str],
    _generation: int,
    is_historical: bool,
    path: Path,
) -> None:
    _require_fields(
        data,
        {
            "prices",
            "fling_power",
            "fling_effect",
            "attributes",
            "category",
            "effect",
            "short_effect",
            "flavor_text",
            "sprite",
            "unverified_historical_fields",
        },
        path,
    )
    _validate_unverified_historical_fields(
        data,
        is_historical,
        {
            "fling_power",
            "fling_effect",
            "attributes",
            "category",
            "effect",
            "short_effect",
            "sprite",
        },
        path,
    )
    _validate_version_map(data, "prices", version_groups, path)
    for currencies in data["prices"].values():
        if currencies is None:
            continue
        if not isinstance(currencies, dict) or not currencies:
            raise DataValidationError(
                f"{path}: item prices must contain currencies or null"
            )
        for currency, amounts in currencies.items():
            if (
                not _is_identifier(currency)
                or not isinstance(amounts, dict)
                or set(amounts) != {"purchase_price", "sell_price"}
                or any(
                    amount is not None and (not _is_int(amount) or amount < 0)
                    for amount in amounts.values()
                )
            ):
                raise DataValidationError(f"{path}: invalid item prices")
    if data["fling_power"] is not None and not _is_int(data["fling_power"]):
        raise DataValidationError(f"{path}: fling_power must be an integer or null")
    if not all(
        _is_optional(data[field], str)
        for field in ("fling_effect", "category", "effect", "short_effect", "sprite")
    ):
        raise DataValidationError(f"{path}: invalid item text or identifier field")
    if not isinstance(data.get("attributes"), list) or not isinstance(
        data.get("flavor_text"), dict
    ):
        raise DataValidationError(f"{path}: invalid item attributes or flavor_text")
    if not all(isinstance(value, str) for value in data["attributes"]):
        raise DataValidationError(f"{path}: item attributes must be strings")


def _validate_pokemon(
    data: dict[str, Any],
    version_groups: set[str],
    generation: int,
    is_historical: bool,
    path: Path,
) -> None:
    _require_fields(
        data,
        {
            "species",
            "is_default",
            "types",
            "abilities",
            "stats",
            "ev_yield",
            "height",
            "weight",
            "cries",
            "sprites",
            "base_experience",
            "held_items",
            "moves",
            "unverified_historical_fields",
            "forms",
            "evolves_from_species",
            "evolution_chain",
        },
        path,
    )
    if not isinstance(data["species"], str) or not isinstance(data["is_default"], bool):
        raise DataValidationError(f"{path}: invalid species or is_default")
    if not all(
        _is_int(data[field]) and data[field] >= 0 for field in ("height", "weight")
    ):
        raise DataValidationError(
            f"{path}: height and weight must be non-negative integers"
        )
    if data["base_experience"] is not None and not _is_int(data["base_experience"]):
        raise DataValidationError(f"{path}: base_experience must be an integer or null")
    if data["cries"] is not None and (
        not isinstance(data["cries"], dict)
        or not set(data["cries"]) <= {"legacy", "latest"}
        or not all(isinstance(value, str) for value in data["cries"].values())
    ):
        raise DataValidationError(f"{path}: invalid cries")
    if is_historical and (
        not isinstance(data["sprites"], dict) or set(data["sprites"]) - {"versions"}
    ):
        raise DataValidationError(
            f"{path}: historical sprites must use generation assets"
        )
    if not isinstance(data["sprites"], dict):
        raise DataValidationError(f"{path}: invalid generation-specific media")
    types = data.get("types")
    if (
        not isinstance(types, list)
        or not 1 <= len(types) <= 2
        or not all(isinstance(value, str) for value in types)
    ):
        raise DataValidationError(f"{path}: types must contain one or two identifiers")
    stats = data.get("stats")
    expected_stats = GENERATION_ONE_STAT_NAMES if generation == 1 else MODERN_STAT_NAMES
    if (
        not isinstance(stats, dict)
        or set(stats) != expected_stats
        or not all(_is_int(value) and 1 <= value <= 255 for value in stats.values())
    ):
        raise DataValidationError(
            f"{path}: stats must contain the valid generation-specific base stats"
        )
    abilities = data.get("abilities")
    if not isinstance(abilities, list) or not all(
        isinstance(ability, dict)
        and isinstance(ability.get("name"), str)
        and isinstance(ability.get("is_hidden"), bool)
        and _is_int(ability.get("slot"))
        for ability in abilities
    ):
        raise DataValidationError(f"{path}: invalid abilities")
    if len({ability["slot"] for ability in abilities}) != len(abilities) or any(
        ability["slot"] not in {1, 2, 3}
        or not _is_identifier(ability["name"])
        or (generation < 5 and ability["is_hidden"])
        for ability in abilities
    ):
        raise DataValidationError(f"{path}: invalid ability slots or hidden abilities")
    if generation < 3 and abilities:
        raise DataValidationError(
            f"{path}: abilities must be empty before Generation 3"
        )
    ev_yield = data.get("ev_yield")
    if generation < 3:
        if ev_yield is not None:
            raise DataValidationError(
                f"{path}: EV yield must be null before Generation 3"
            )
    elif not isinstance(ev_yield, list) or not all(
        isinstance(entry, dict)
        and entry.get("stat") in STAT_NAMES
        and _is_int(entry.get("effort"))
        and 1 <= entry["effort"] <= 3
        for entry in ev_yield
    ):
        raise DataValidationError(f"{path}: invalid EV yield")
    _validate_unverified_historical_fields(
        data,
        is_historical,
        {
            "base_experience",
            "base_happiness",
            "capture_rate",
            "hatch_counter",
            "gender_rate",
            "egg_groups",
            "growth_rate",
            "forms_switchable",
        },
        path,
    )
    moves = data.get("moves")
    held_items = data.get("held_items")
    if not isinstance(moves, dict) or not isinstance(held_items, dict):
        raise DataValidationError(f"{path}: moves and held_items must be objects")
    for method, entries in moves.items():
        if not _is_identifier(method) or not isinstance(entries, list):
            raise DataValidationError(f"{path}: each move method must contain a list")
        seen = set()
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not _is_identifier(entry.get("name"))
                or not _is_int(entry.get("level_learned_at"))
                or not 0 <= entry["level_learned_at"] <= 100
            ):
                raise DataValidationError(f"{path}: invalid learnset entry")
            _validate_groups(entry.get("version_groups"), version_groups, path, "move")
            signature = (entry["name"], entry["level_learned_at"])
            if signature in seen:
                raise DataValidationError(f"{path}: duplicate learnset entry")
            seen.add(signature)
    for item, versions in held_items.items():
        if (
            not _is_identifier(item)
            or not isinstance(versions, dict)
            or not versions
            or not all(
                _is_identifier(version) and _is_int(rarity) and 0 <= rarity <= 100
                for version, rarity in versions.items()
            )
        ):
            raise DataValidationError(f"{path}: invalid held item values")
    forms = data["forms"]
    if not isinstance(forms, list) or not all(
        isinstance(form, dict)
        and _is_identifier(form.get("name"))
        and form.get("category") in {"default", "variant", "transformation", "cosmetic"}
        for form in forms
    ):
        raise DataValidationError(f"{path}: invalid forms")
    if len({(form["name"], form["category"]) for form in forms}) != len(forms):
        raise DataValidationError(f"{path}: duplicate forms")
    if data["evolves_from_species"] is not None and not _is_identifier(
        data["evolves_from_species"]
    ):
        raise DataValidationError(f"{path}: invalid evolution parent")
    chain_parents: dict[str, str | None] = {}

    def validate_evolution_node(node: Any, parent: str | None = None) -> None:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("species_name"), str)
            or not isinstance(node.get("evolves_to"), list)
        ):
            raise DataValidationError(f"{path}: invalid evolution chain node")
        species = node["species_name"]
        if not _is_identifier(species) or species in chain_parents:
            raise DataValidationError(f"{path}: invalid or repeated evolution species")
        chain_parents[species] = parent
        for evolution in node["evolves_to"]:
            availability = (
                evolution.get("availability") if isinstance(evolution, dict) else None
            )
            if availability not in {"available", "unavailable"}:
                raise DataValidationError(f"{path}: invalid evolution availability")
            details = (
                evolution.get("evolution_details")
                if isinstance(evolution, dict)
                else None
            )
            if not isinstance(details, list):
                raise DataValidationError(f"{path}: invalid evolution details")
            if (availability == "available") != bool(details):
                raise DataValidationError(
                    f"{path}: evolution availability disagrees with its details"
                )
            for detail in details:
                groups = (
                    detail.get("version_groups") if isinstance(detail, dict) else None
                )
                _validate_groups(groups, version_groups, path, "evolution")
                if not _is_optional(detail.get("introduced_in_version_group"), str):
                    raise DataValidationError(
                        f"{path}: invalid evolution introduction version group"
                    )
                if detail.get("time_of_day") == "":
                    raise DataValidationError(
                        f"{path}: empty evolution time_of_day must be null"
                    )
            validate_evolution_node(evolution, species)

    evolution_chain = data.get("evolution_chain")
    if evolution_chain is not None:
        validate_evolution_node(evolution_chain)
        if (
            data["species"] not in chain_parents
            or chain_parents[data["species"]] != data["evolves_from_species"]
        ):
            raise DataValidationError(
                f"{path}: evolution parent disagrees with reconstructed chain"
            )
    elif data["evolves_from_species"] is not None:
        raise DataValidationError(f"{path}: evolution parent requires a chain")


VALIDATORS: dict[str, Callable[[dict[str, Any], set[str], int, bool, Path], None]] = {
    "ability": _validate_ability,
    "item": _validate_item,
    "move": _validate_move,
    "pokemon": _validate_pokemon,
    "variant": _validate_pokemon,
    "transformation": _validate_pokemon,
    "cosmetic": _validate_pokemon,
}


def validate_generation_output(generation_root: Path) -> None:
    """Validates schemas, index/file agreement, and core domain invariants."""
    index_path = generation_root / "index.json"
    index = _read_object(index_path)
    metadata = index.get("metadata")
    if not isinstance(metadata, dict):
        raise DataValidationError(f"{index_path}: metadata must be an object")
    version_group_list = metadata.get("version_groups")
    generation = metadata.get("generation")
    schema_version = metadata.get("schema_version")
    source = metadata.get("source")
    api_base_url = metadata.get("api_base_url")
    is_historical = metadata.get("is_historical")
    if schema_version != DATA_SCHEMA_VERSION:
        raise DataValidationError(
            f"{index_path}: schema_version must be {DATA_SCHEMA_VERSION}"
        )
    if source != "pokeapi":
        raise DataValidationError(f"{index_path}: source must be pokeapi")
    if not isinstance(api_base_url, str) or not api_base_url.endswith("/"):
        raise DataValidationError(f"{index_path}: invalid api_base_url")
    if not isinstance(is_historical, bool):
        raise DataValidationError(f"{index_path}: is_historical must be boolean")
    if not _is_int(generation) or generation < 1:
        raise DataValidationError(
            f"{index_path}: generation must be a positive integer"
        )
    if (
        not isinstance(version_group_list, list)
        or not all(isinstance(group, str) for group in version_group_list)
        or len(version_group_list) != len(set(version_group_list))
    ):
        raise DataValidationError(
            f"{index_path}: version_groups must be unique strings"
        )
    generated = metadata.get("generated_resources")
    if (
        not isinstance(generated, list)
        or not all(isinstance(resource, str) for resource in generated)
        or len(generated) != len(set(generated))
        or not set(generated) <= set(RESOURCE_INDEX_KEYS)
    ):
        raise DataValidationError(f"{index_path}: invalid generated_resources")
    generated = set(generated)
    provenance = metadata.get("resource_provenance")
    if not isinstance(provenance, dict) or set(provenance) != generated:
        raise DataValidationError(f"{index_path}: invalid resource_provenance")
    for record in provenance.values():
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("version"), str)
            or (
                record.get("commit") is not None
                and (
                    not isinstance(record["commit"], str)
                    or re.fullmatch(r"[0-9a-f]{40}", record["commit"]) is None
                )
            )
            or not isinstance(record.get("dependencies"), dict)
            or set(record["dependencies"]) != {"requests", "tqdm"}
            or not all(
                isinstance(value, str) for value in record["dependencies"].values()
            )
        ):
            raise DataValidationError(f"{index_path}: invalid generator provenance")
    versions = metadata.get("versions")
    if (
        not isinstance(versions, list)
        or not all(_is_identifier(version) for version in versions)
        or len(versions) != len(set(versions))
    ):
        raise DataValidationError(f"{index_path}: invalid versions")
    version_groups = set(version_group_list)
    counts = metadata.get("counts")
    try:
        if datetime.fromisoformat(metadata["created_at"]).utcoffset() is None:
            raise ValueError("timezone required")
    except (KeyError, TypeError, ValueError) as error:
        raise DataValidationError(
            f"{index_path}: created_at must be a timestamp with timezone"
        ) from error
    if not isinstance(counts, dict) or set(counts) != set(RESOURCE_INDEX_KEYS):
        raise DataValidationError(f"{index_path}: counts must be an object")
    if set(index) != {"metadata", *RESOURCE_INDEX_KEYS}:
        raise DataValidationError(
            f"{index_path}: resource keys must use the complete stable schema"
        )

    loaded: dict[str, list[dict[str, Any]]] = {}
    for resource, relative_path in RESOURCE_PATHS.items():
        summaries = index.get(resource)
        if (
            not isinstance(summaries, list)
            or not _is_int(counts.get(resource))
            or counts[resource] != len(summaries)
        ):
            raise DataValidationError(
                f"{index_path}: invalid {resource} summaries or count"
            )
        if resource not in generated and summaries:
            raise DataValidationError(
                f"{index_path}: omitted catalog {resource} must be empty"
            )
        if (
            resource in generated
            and resource in {"ability", "move", "pokemon", "item"}
            and not summaries
        ):
            if resource != "ability" or generation >= 3:
                raise DataValidationError(
                    f"{index_path}: generated catalog {resource} unexpectedly empty"
                )
        names = [entry.get("name") for entry in summaries if isinstance(entry, dict)]
        if len(names) != len(summaries) or any(
            not isinstance(name, str) for name in names
        ):
            raise DataValidationError(f"{index_path}: invalid {resource} summary")
        if len(names) != len(set(names)):
            raise DataValidationError(f"{index_path}: duplicate {resource} names")

        directory = generation_root / relative_path
        files = (
            {path.stem: path for path in directory.glob("*.json")}
            if directory.exists()
            else {}
        )
        if set(names) != set(files):
            raise DataValidationError(
                f"{directory}: files must exactly match the {resource} index"
            )
        loaded[resource] = []
        for summary in summaries:
            path = files[summary["name"]]
            data = _read_object(path)
            _validate_common(data, summary["name"], api_base_url, path)
            if summary.get("id") != data["id"]:
                raise DataValidationError(f"{path}: id differs from its index summary")
            VALIDATORS[resource](data, version_groups, generation, is_historical, path)
            loaded[resource].append(data)

    if "ability" in generated:
        ability_names = {entry["name"] for entry in loaded["ability"]}
        for resource in ("pokemon", "variant", "transformation", "cosmetic"):
            for pokemon in loaded.get(resource, []):
                missing = {
                    entry["name"] for entry in pokemon["abilities"]
                } - ability_names
                if missing:
                    raise DataValidationError(
                        f"{pokemon['name']}: unknown abilities {sorted(missing)}"
                    )

    move_names = {entry["name"] for entry in loaded.get("move", [])}
    item_names = {entry["name"] for entry in loaded.get("item", [])}
    species_names = {entry["species"] for entry in loaded.get("pokemon", [])}

    def validate_evolution_references(node: Any, owner: str) -> None:
        if not isinstance(node, dict):
            return
        species_name = node.get("species_name")
        if "pokemon" in generated and species_name not in species_names:
            raise DataValidationError(
                f"{owner}: evolution chain references unknown species {species_name!r}"
            )
        for evolution in node.get("evolves_to", []):
            for detail in evolution.get("evolution_details", []):
                for field in ("item", "held_item"):
                    reference = detail.get(field)
                    if (
                        "item" in generated
                        and reference is not None
                        and reference not in item_names
                    ):
                        raise DataValidationError(
                            f"{owner}: evolution references unknown item {reference!r}"
                        )
                known_move = detail.get("known_move")
                if (
                    "move" in generated
                    and known_move is not None
                    and known_move not in move_names
                ):
                    raise DataValidationError(
                        f"{owner}: evolution references unknown move {known_move!r}"
                    )
            validate_evolution_references(evolution, owner)

    for resource in ("pokemon", "variant", "transformation", "cosmetic"):
        for pokemon in loaded.get(resource, []):
            if "move" in generated:
                referenced_moves = {
                    move["name"]
                    for method in pokemon["moves"].values()
                    for move in method
                }
                missing_moves = referenced_moves - move_names
                if missing_moves:
                    raise DataValidationError(
                        f"{pokemon['name']}: unknown moves {sorted(missing_moves)}"
                    )
            if "item" in generated:
                missing_items = set(pokemon["held_items"]) - item_names
                if missing_items:
                    raise DataValidationError(
                        f"{pokemon['name']}: unknown held items {sorted(missing_items)}"
                    )
            validate_evolution_references(
                pokemon.get("evolution_chain"), pokemon["name"]
            )

    for resource in ("pokemon", "variant", "transformation", "cosmetic"):
        for pokemon in loaded[resource]:
            for item_versions in pokemon["held_items"].values():
                if not set(item_versions) <= set(versions):
                    raise DataValidationError(
                        f"{pokemon['name']}: held items reference unknown versions"
                    )
            for form in pokemon["forms"]:
                category = (
                    "pokemon" if form["category"] == "default" else form["category"]
                )
                if category in generated and form["name"] not in {
                    entry["name"] for entry in loaded[category]
                }:
                    raise DataValidationError(
                        f"{pokemon['name']}: unknown form {form['name']}"
                    )
            parent = pokemon["evolves_from_species"]
            if (
                "pokemon" in generated
                and parent is not None
                and parent not in species_names
            ):
                raise DataValidationError(
                    f"{pokemon['name']}: unknown evolution parent {parent}"
                )

    if "item" in generated:
        for move in loaded["move"]:
            missing = {
                item for item in move["machine"].values() if item is not None
            } - item_names
            if missing:
                raise DataValidationError(
                    f"{move['name']}: unknown machine items {sorted(missing)}"
                )
    if metadata.get("content_sha256") != generation_content_digest(generation_root):
        raise DataValidationError(
            f"{index_path}: content_sha256 does not match resource files"
        )
