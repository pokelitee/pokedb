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


class AbilityParser(GenerationParser):
    """
    A parser for Pokémon abilities.

    This parser fetches ability data from the PokéAPI, processes it for a specific
    generation, and writes individual JSON files for each ability.

    Features:
    - Handles generation-specific effect changes
    - Extracts flavor text for all version groups in the target generation
    - Processes both current and historical ability effects
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
        self.entity_type = "Ability"
        self.api_endpoint = "abilities"
        self.output_dir_key = "output_dir_ability"

    def process(self, resource_ref: dict[str, str]) -> dict[str, Any] | str | None:
        """
        Processes a single ability from its API reference.

        This method fetches the full ability data, processes generation-specific
        effect changes, and writes the result to a JSON file.

        Args:
            resource_ref: Dictionary containing 'name' and 'url' for the ability

        Returns:
            A summary dict with name and id, or an error string if processing fails
        """
        try:
            data = self.api_client.get(resource_ref["url"])
            effect, short_effect = self._get_effects_for_target_generation(data)

            # Build the basic ability data structure
            cleaned_data = {
                "id": data["id"],
                "name": data["name"],
                "source_url": resource_ref["url"],
                "is_main_series": data.get("is_main_series"),
                "generation": data.get("generation", {}).get("name"),
                "effect": effect,
                "short_effect": short_effect,
                "flavor_text": get_all_english_entries_for_gen_by_game(
                    data.get("flavor_text_entries", []),
                    "flavor_text",
                    self.generation_version_groups,
                    self.target_gen,
                ),
            }

            # Write to file
            output_path = str(self.config.output_path(self.output_dir_key))
            write_json_file(output_path, cleaned_data["name"], cleaned_data)

            return {"name": cleaned_data["name"], "id": cleaned_data["id"]}

        except (KeyError, ValueError) as e:
            resource_name = resource_ref.get("name", "unknown")
            return f"Parsing failed for {resource_name}: {type(e).__name__} - {e}"
        except Exception as e:
            resource_name = resource_ref.get("name", "unknown")
            logger.error(f"Unexpected error processing {resource_name}: {e}")
            return f"Parsing failed for {resource_name}: {e}"

    def _get_effects_for_target_generation(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, str | None], dict[str, str | None]]:
        """Reconstructs effects using the nearest change after each target game."""
        target_groups = self.generation_version_groups.get(self.target_gen, [])
        current_effect = get_english_entry(data.get("effect_entries", []), "effect")
        current_short_effect = get_english_entry(
            data.get("effect_entries", []), "short_effect"
        )
        effects = {group: current_effect for group in target_groups}
        short_effects = {group: current_short_effect for group in target_groups}

        group_order = {
            group: (generation, position)
            for generation, groups in self.generation_version_groups.items()
            for position, group in enumerate(groups)
        }
        changes = sorted(
            data.get("effect_changes", []),
            key=lambda change: group_order.get(
                change.get("version_group", {}).get("name"), (999, 999)
            ),
        )
        for target_group in target_groups:
            target_order = group_order.get(target_group, (0, 0))
            effect_reconstructed = False
            short_effect_reconstructed = False
            for change in changes:
                change_order = group_order.get(
                    change.get("version_group", {}).get("name"), (999, 999)
                )
                if change_order <= target_order:
                    continue
                previous_effect = get_english_entry(
                    change.get("effect_entries", []), "effect"
                )
                change_entries = change.get("effect_entries", [])
                previous_short_effect = (
                    get_english_entry(change_entries, "short_effect")
                    if any("short_effect" in entry for entry in change_entries)
                    else None
                )
                if previous_effect is not None and not effect_reconstructed:
                    effects[target_group] = previous_effect
                    effect_reconstructed = True
                if previous_short_effect is not None and not short_effect_reconstructed:
                    short_effects[target_group] = previous_short_effect
                    short_effect_reconstructed = True
                if effect_reconstructed and short_effect_reconstructed:
                    break

        return effects, short_effects
