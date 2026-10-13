import json
from logging import getLogger
from typing import Any

from ..api_client import ApiClient
from ..config import Config
from ..utils import (
    DEFAULT_API_LIMIT,
    get_all_english_entries_for_gen_by_game,
    get_english_entry,
    write_json_file,
)
from ..utils.api_helpers import get_all_results
from ..utils.exceptions import ParserExecutionError
from .base import BaseParser

logger = getLogger(__name__)


class ItemParser(BaseParser):
    """
    A parser for Pokémon items.

    This parser fetches all items from the PokéAPI and filters them based on
    the target generation. It writes individual JSON files for each item that
    exists in the target generation.

    Features:
    - Generation-based filtering using game indices
    - Extracts item attributes, effects, and flavor text
    - Handles fling mechanics (power and effect)
    """

    def __init__(
        self,
        config: Config,
        api_client: ApiClient,
        generation_version_groups: dict[int, list[str]],
        target_gen: int,
        generation_dex_map: dict[int, str] | None = None,
        is_historical: bool = False,
    ):
        super().__init__(
            config,
            api_client,
            generation_version_groups,
            target_gen,
            generation_dex_map,
            is_historical,
        )
        self.entity_type = "Item"
        self.api_endpoint = "item"
        self.output_dir_key = "output_dir_item"
        self.referenced_item_names = self._get_referenced_item_names()

    def _get_referenced_item_names(self) -> set[str]:
        """Collects item identifiers referenced by already-generated resources."""
        names: set[str] = set()
        if self.config.generation is None:
            return names

        def visit_evolution(node: Any) -> None:
            if not isinstance(node, dict):
                return
            for evolution in node.get("evolves_to", []):
                for detail in evolution.get("evolution_details", []):
                    for field in ("item", "held_item"):
                        value = detail.get(field)
                        if isinstance(value, str):
                            names.add(value)
                visit_evolution(evolution)

        output_keys = (
            "output_dir_move",
            "output_dir_pokemon",
            "output_dir_variant",
            "output_dir_transformation",
            "output_dir_cosmetic",
        )
        for output_key in output_keys:
            directory = self.config.output_path(output_key)
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                try:
                    with path.open(encoding="utf-8") as file:
                        data = json.load(file)
                except (OSError, json.JSONDecodeError) as error:
                    raise ParserExecutionError(
                        f"Could not inspect item references in {path}"
                    ) from error
                machines = data.get("machine", {})
                names.update(value for value in machines.values() if value is not None)
                held_items = data.get("held_items")
                if isinstance(held_items, dict):
                    names.update(held_items)
                visit_evolution(data.get("evolution_chain"))
        return names

    def _get_all_item_refs(self) -> list[dict[str, str]]:
        """
        Retrieves all item references from the API.

        Unlike generation-specific parsers, items must be fetched from a single
        endpoint with a high limit, then filtered by generation.

        Returns:
            A list of item reference dictionaries with 'name' and 'url' keys
        """
        endpoint_url = (
            f"{self.config.api_base_url}{self.api_endpoint}?limit={DEFAULT_API_LIMIT}"
        )
        return get_all_results(self.api_client, endpoint_url)

    def _apply_generation_policy(self, cleaned_data: dict[str, Any]) -> None:
        """Flags item fields for which PokéAPI provides only current values."""
        self._flag_unverified_historical_fields(
            cleaned_data,
            [
                "fling_power",
                "fling_effect",
                "attributes",
                "category",
                "effect",
                "short_effect",
                "sprite",
            ],
        )

    def _get_prices_for_generation(
        self, prices: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Keeps observed prices for each target game and currency."""
        if not isinstance(prices, list):
            raise ValueError("Item prices must be a list")
        groups = self.generation_version_groups.get(self.target_gen, [])
        result: dict[str, Any] = dict.fromkeys(groups)
        for price in prices:
            group = price["version_group"]["name"]
            if group not in result:
                continue
            currency = price["currency"]["name"]
            amounts = {key: price[key] for key in ("purchase_price", "sell_price")}
            currencies = result[group]
            if currencies is None:
                currencies = result[group] = {}
            if currency in currencies and currencies[currency] != amounts:
                raise ValueError(f"Conflicting prices for {group}/{currency}")
            currencies[currency] = amounts
        return result

    def process(self, resource_ref: dict[str, str]) -> dict[str, Any] | str | None:
        """
        Processes a single item from its API reference.

        This method fetches the full item data, checks if it exists in the target
        generation, and writes it to a JSON file if applicable.

        Args:
            resource_ref: Dictionary containing 'name' and 'url' for the item

        Returns:
            A summary dict with name, id, and sprite, or None if item doesn't exist
            in the target generation, or an error string if processing fails
        """
        try:
            data = self.api_client.get(resource_ref["url"])
            game_indices = data.get("game_indices", [])

            # Determine which generations this item appears in
            item_generations = {
                int(game_index["generation"]["url"].split("/")[-2])
                for game_index in game_indices
            }

            # Generation outputs are cumulative catalogs, so retain every item
            # introduced by or before the target generation.
            has_generation_evidence = bool(item_generations) and (
                self.target_gen is None or min(item_generations) <= self.target_gen
            )
            is_referenced = data.get("name") in self.referenced_item_names
            if has_generation_evidence or is_referenced:
                # Extract fling effect name if it exists
                fling_effect_obj = data.get("fling_effect")
                fling_effect_name = (
                    fling_effect_obj.get("name") if fling_effect_obj else None
                )

                cleaned_data = {
                    "id": data["id"],
                    "name": data["name"],
                    "source_url": resource_ref["url"],
                    "prices": self._get_prices_for_generation(data.get("prices", [])),
                    "fling_power": data["fling_power"],
                    "fling_effect": fling_effect_name,
                    "attributes": [attr["name"] for attr in data.get("attributes", [])],
                    "category": data.get("category", {}).get("name"),
                    "effect": get_english_entry(
                        data.get("effect_entries", []), "effect"
                    ),
                    "short_effect": get_english_entry(
                        data.get("effect_entries", []), "short_effect"
                    ),
                    "flavor_text": get_all_english_entries_for_gen_by_game(
                        data.get("flavor_text_entries", []),
                        "text",
                        self.generation_version_groups,
                        self.target_gen,
                    ),
                    "sprite": data.get("sprites", {}).get("default"),
                }
                self._apply_generation_policy(cleaned_data)

                # Write to file
                output_path = str(self.config.output_path(self.output_dir_key))
                write_json_file(output_path, cleaned_data["name"], cleaned_data)

                return {
                    "name": cleaned_data["name"],
                    "id": cleaned_data["id"],
                    "sprite": cleaned_data["sprite"],
                }

            return None

        except (KeyError, ValueError) as e:
            return f"Parsing failed for {resource_ref.get('name', 'unknown')}: {type(e).__name__} - {e}"
        except Exception as e:
            logger.error(
                f"Unexpected error processing {resource_ref.get('name', 'unknown')}: {e}"
            )
            return f"Parsing failed for {resource_ref.get('name', 'unknown')}: {e}"
