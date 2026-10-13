"""Shared resource layout and dataset contract."""

from dataclasses import dataclass
from pathlib import Path

DATA_SCHEMA_VERSION = 5


@dataclass(frozen=True)
class Resource:
    parser: str
    output_key: str
    path: Path


RESOURCES = {
    "ability": Resource("ability", "output_dir_ability", Path("ability")),
    "item": Resource("item", "output_dir_item", Path("item")),
    "move": Resource("move", "output_dir_move", Path("move")),
    "pokemon": Resource("pokemon", "output_dir_pokemon", Path("pokemon/default")),
    "variant": Resource("pokemon", "output_dir_variant", Path("pokemon/variant")),
    "transformation": Resource(
        "pokemon", "output_dir_transformation", Path("pokemon/transformation")
    ),
    "cosmetic": Resource("pokemon", "output_dir_cosmetic", Path("pokemon/cosmetic")),
}
RESOURCE_INDEX_KEYS = tuple(RESOURCES)
RESOURCE_PATHS = {name: resource.path for name, resource in RESOURCES.items()}
OUTPUT_PATHS = {resource.output_key: resource.path for resource in RESOURCES.values()}
PARSER_SUMMARY_KEYS = {
    parser: tuple(
        name for name, resource in RESOURCES.items() if resource.parser == parser
    )
    for parser in dict.fromkeys(resource.parser for resource in RESOURCES.values())
}
PARSER_OUTPUT_KEYS = {
    parser: tuple(RESOURCES[name].output_key for name in names)
    for parser, names in PARSER_SUMMARY_KEYS.items()
}
PARSER_DEPENDENCIES = {
    "ability": (),
    "move": (),
    "pokemon": (),
    "item": ("move", "pokemon"),
}
