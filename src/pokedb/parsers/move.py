from logging import getLogger
from typing import Any

from ..api_client import ApiClient
from ..config import Config
from ..utils import (
    get_all_english_entries_for_gen_by_game,
    get_english_entry,
    write_json_file,
)
from .generation import GenerationParser

logger = getLogger(__name__)

PHYSICAL_TYPES_BEFORE_GENERATION_FOUR = {
    "normal",
    "fighting",
    "flying",
    "poison",
    "ground",
    "rock",
    "bug",
    "ghost",
    "steel",
}
SPECIAL_TYPES_BEFORE_GENERATION_FOUR = {
    "fire",
    "water",
    "grass",
    "electric",
    "psychic",
    "ice",
    "dragon",
    "dark",
}


class MoveParser(GenerationParser):
    """
    A parser for Pokémon moves.

    This parser fetches move data from the PokéAPI, processes generation-specific
    changes, and writes individual JSON files for each move.

    Features:
    - Handles generation-specific stat changes (power, PP, accuracy, etc.)
    - Processes move metadata (ailments, categories, hit/turn ranges)
    - Tracks TM/HM machine assignments per generation
    - Applies historical values for older generations
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
        self.entity_type = "Move"
        self.api_endpoint = "moves"
        self.output_dir_key = "output_dir_move"

    def _get_machine_for_generation(
        self, machine_entries: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        """Returns each target game's machine assignment without hiding fetch errors."""
        target_groups = (self.generation_version_groups or {}).get(self.target_gen, [])
        machines = dict.fromkeys(target_groups)
        for entry in machine_entries:
            group = entry["version_group"]["name"]
            if group in machines:
                item = self.api_client.get(entry["machine"]["url"])["item"]["name"]
                if machines[group] is not None and machines[group] != item:
                    raise ValueError(f"Conflicting machine assignments for {group}")
                machines[group] = item
        return machines

    def _clean_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        """
        Cleans and normalizes move metadata from the API.

        Move metadata includes information about ailments, hit/turn ranges,
        drain/healing percentages, and various probability chances.

        Args:
            metadata: The 'meta' dictionary from move API data, or None

        Returns:
            A cleaned metadata dictionary with consistent default values
        """
        # Provide default values if metadata is missing
        if not metadata:
            return {
                "ailment": None,
                "category": None,
                "min_hits": None,
                "max_hits": None,
                "min_turns": None,
                "max_turns": None,
                "drain": 0,
                "healing": 0,
                "crit_rate": 0,
                "ailment_chance": 0,
                "flinch_chance": 0,
                "stat_chance": 0,
            }

        ailment = metadata.get("ailment")
        category = metadata.get("category")

        return {
            "ailment": ailment.get("name") if ailment else None,
            "category": category.get("name") if category else None,
            "min_hits": metadata.get("min_hits"),
            "max_hits": metadata.get("max_hits"),
            "min_turns": metadata.get("min_turns"),
            "max_turns": metadata.get("max_turns"),
            "drain": metadata.get("drain"),
            "healing": metadata.get("healing"),
            "crit_rate": metadata.get("crit_rate"),
            "ailment_chance": metadata.get("ailment_chance"),
            "flinch_chance": metadata.get("flinch_chance"),
            "stat_chance": metadata.get("stat_chance"),
        }

    def _apply_past_values(
        self, cleaned_data: dict[str, Any], past_values: list[dict[str, Any]]
    ):
        """
        Applies historical stat changes to move data for the target generation.

        Many moves have had their stats changed across generations (e.g., Gust
        became Flying-type in Gen 2, many moves had power/accuracy adjusted).
        This method creates generation-specific values for each version group.

        Args:
            cleaned_data: The move data dictionary to modify in-place
            past_values: List of past value changes from the API

        Modifies:
            cleaned_data: Converts single values to version-group-specific dicts
        """
        if not self.target_gen or not self.generation_version_groups:
            return

        version_group_order = {
            version_group_name: (generation, position)
            for generation, version_groups in self.generation_version_groups.items()
            for position, version_group_name in enumerate(version_groups)
        }

        target_gen_version_groups = self.generation_version_groups.get(
            self.target_gen, []
        )

        # Fields that can change across generations
        change_fields = [
            "accuracy",
            "power",
            "pp",
            "effect_chance",
            "type",
            "effect",
            "short_effect",
        ]
        generation_specific_values: dict[str, dict[str, Any]] = {
            field: {} for field in change_fields
        }

        # For each version group in the target generation
        for version_group_name in target_gen_version_groups:
            # Start with current values
            temp_data = {
                "accuracy": cleaned_data.get("accuracy"),
                "power": cleaned_data.get("power"),
                "pp": cleaned_data.get("pp"),
                "effect_chance": cleaned_data.get("effect_chance"),
                "type": cleaned_data.get("type"),
                "effect": cleaned_data.get("effect"),
                "short_effect": cleaned_data.get("short_effect"),
            }

            sorted_past_values = sorted(
                past_values,
                key=lambda value: version_group_order.get(
                    value["version_group"]["name"], (999, 999)
                ),
            )
            current_version_group_order = version_group_order.get(
                version_group_name, (0, 0)
            )
            applied_fields = set()

            for past_value in sorted_past_values:
                past_value_order = version_group_order.get(
                    past_value["version_group"]["name"], (999, 999)
                )

                if past_value_order <= current_version_group_order:
                    continue

                for field in ("accuracy", "power", "pp", "effect_chance"):
                    if (
                        field not in applied_fields
                        and past_value.get(field) is not None
                    ):
                        temp_data[field] = past_value[field]
                        applied_fields.add(field)
                if "type" not in applied_fields and past_value.get("type"):
                    temp_data["type"] = past_value["type"]["name"]
                    applied_fields.add("type")
                if not {"effect", "short_effect"}.issubset(
                    applied_fields
                ) and past_value.get("effect_entries"):
                    effect = get_english_entry(past_value["effect_entries"], "effect")
                    short_effect = get_english_entry(
                        past_value["effect_entries"], "short_effect"
                    )
                    if effect and "effect" not in applied_fields:
                        temp_data["effect"] = effect
                        applied_fields.add("effect")
                    if short_effect and "short_effect" not in applied_fields:
                        temp_data["short_effect"] = short_effect
                        applied_fields.add("short_effect")

            # Store the final values for this version group
            for field in change_fields:
                generation_specific_values[field][version_group_name] = temp_data[field]

        # Replace single values with version-group-specific dictionaries
        for field, values_map in generation_specific_values.items():
            cleaned_data[field] = values_map

    def _apply_generation_policy(self, cleaned_data: dict[str, Any]) -> None:
        """Flags unversioned fields as unverified and derives pre-split move classes."""
        self._flag_unverified_historical_fields(
            cleaned_data, ["priority", "target", "metadata", "stat_changes"]
        )

        if not self.is_historical:
            return

        if self.target_gen is None or self.target_gen >= 4:
            cleaned_data["damage_class"] = None
            return
        if cleaned_data["damage_class"] == "status":
            return

        types = {
            value
            for value in cleaned_data.get("type", {}).values()
            if value is not None
        }
        if types and types <= PHYSICAL_TYPES_BEFORE_GENERATION_FOUR:
            cleaned_data["damage_class"] = "physical"
        elif types and types <= SPECIAL_TYPES_BEFORE_GENERATION_FOUR:
            cleaned_data["damage_class"] = "special"
        else:
            cleaned_data["damage_class"] = None

    def process(self, resource_ref: dict[str, str]) -> dict[str, Any] | str | None:
        """
        Processes a single move from its API reference.

        This method fetches the full move data, processes generation-specific changes,
        and writes the result to a JSON file.

        Args:
            resource_ref: Dictionary containing 'name' and 'url' for the move

        Returns:
            A summary dict with name and id, or an error string if processing fails
        """
        try:
            data = self.api_client.get(resource_ref["url"])

            # Build the basic move data structure
            cleaned_data = {
                "id": data["id"],
                "name": data["name"],
                "source_url": resource_ref["url"],
                "accuracy": data.get("accuracy"),
                "power": data.get("power"),
                "pp": data.get("pp"),
                "priority": data.get("priority"),
                "damage_class": data.get("damage_class", {}).get("name"),
                "type": data.get("type", {}).get("name"),
                "target": data.get("target", {}).get("name"),
                "generation": data.get("generation", {}).get("name"),
                "effect_chance": data.get("effect_chance"),
                "effect": get_english_entry(data.get("effect_entries", []), "effect"),
                "short_effect": get_english_entry(
                    data.get("effect_entries", []), "short_effect"
                ),
                "flavor_text": get_all_english_entries_for_gen_by_game(
                    data.get("flavor_text_entries", []),
                    "flavor_text",
                    self.generation_version_groups,
                    self.target_gen,
                ),
                "stat_changes": [
                    {
                        "change": stat_change["change"],
                        "stat": stat_change.get("stat", {}).get("name"),
                    }
                    for stat_change in data.get("stat_changes", [])
                ],
                "machine": self._get_machine_for_generation(data.get("machines", [])),
                "metadata": self._clean_metadata(data.get("meta")),
            }

            # Apply historical stat changes for the target generation
            past_values = data.get("past_values", [])
            self._apply_past_values(cleaned_data, past_values)
            self._apply_generation_policy(cleaned_data)

            # Write to file
            output_path = str(self.config.output_path(self.output_dir_key))
            write_json_file(output_path, cleaned_data["name"], cleaned_data)

            return {"name": cleaned_data["name"], "id": cleaned_data["id"]}

        except (KeyError, ValueError) as e:
            return f"Parsing failed for {resource_ref.get('name', 'unknown')}: {type(e).__name__} - {e}"
        except Exception as e:
            logger.error(
                f"Unexpected error processing {resource_ref.get('name', 'unknown')}: {e}"
            )
            return f"Parsing failed for {resource_ref.get('name', 'unknown')}: {e}"
