"""Parser dependency construction and generation metadata collection."""

import argparse
import logging
from typing import Any

from .api_client import ApiClient
from .config import Config
from .parsers import AbilityParser, BaseParser, ItemParser, MoveParser, PokemonParser
from .resources import PARSER_DEPENDENCIES
from .utils import GenerationNotFoundError, get_generation_dex_map
from .utils.api_helpers import get_all_results

logger = logging.getLogger(__name__)

PARSER_CLASSES: dict[str, type[BaseParser]] = {
    "ability": AbilityParser,
    "move": MoveParser,
    "pokemon": PokemonParser,
    # Items run last so their catalog can include references emitted by moves
    # and Pokemon when PokeAPI does not provide a game index.
    "item": ItemParser,
}


def gather_initial_data(
    api_client: ApiClient, config: Config, target_gen: int
) -> tuple[dict[int, list[str]], dict[int, str], set[str]]:
    """Collects version groups, target versions, and regional Pokédex mappings."""
    logger.info("Gathering generation metadata for Generation %s...", target_gen)
    generation_version_groups: dict[int, list[str]] = {}
    target_versions: set[str] = set()

    try:
        for generation_ref in get_all_results(
            api_client, f"{config.api_base_url}generation/"
        ):
            generation_number = int(generation_ref["url"].split("/")[-2])
            details = api_client.get(generation_ref["url"])
            version_groups = [
                group["name"] for group in details.get("version_groups", [])
            ]
            generation_version_groups[generation_number] = version_groups

            if generation_number == target_gen:
                for version_group_name in version_groups:
                    version_group = api_client.get(
                        f"{config.api_base_url}version-group/{version_group_name}"
                    )
                    target_versions.update(
                        version["name"] for version in version_group.get("versions", [])
                    )
    except Exception as error:
        raise GenerationNotFoundError(
            f"Could not fetch generation data: {error}"
        ) from error

    generation_dex_map = get_generation_dex_map(api_client, config)
    return generation_version_groups, generation_dex_map, target_versions


def run_parsers(
    args: argparse.Namespace,
    config: Config,
    api_client: ApiClient,
    generation_version_groups: dict[int, list[str]],
    target_gen: int,
    generation_dex_map: dict[int, str],
    is_historical: bool,
    target_versions: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Constructs and executes each requested parser."""
    summaries: dict[str, list[dict[str, Any]]] = {}

    completed: set[str] = set()
    requested = set(PARSER_CLASSES if args.all else args.parsers)
    for parser_name, parser_class in PARSER_CLASSES.items():
        if not (args.all or parser_name in args.parsers):
            continue

        if (
            not set(PARSER_DEPENDENCIES[parser_name]).intersection(requested)
            <= completed
        ):
            raise RuntimeError(f"Unmet parser dependencies for {parser_name}")
        parser_kwargs = {
            "config": config,
            "api_client": api_client,
            "generation_version_groups": generation_version_groups,
            "target_gen": target_gen,
            "generation_dex_map": generation_dex_map,
            "is_historical": is_historical,
        }
        if parser_name == "pokemon":
            parser_kwargs["target_versions"] = target_versions

        result = parser_class(**parser_kwargs).run()
        if isinstance(result, list):
            summaries[parser_name] = result
        elif isinstance(result, dict):
            summaries.update(result)
        completed.add(parser_name)
        logger.info("-" * 20)

    return summaries
