import copy
from logging import getLogger
from typing import Any

from ..api_client import ApiClient
from ..config import Config
from ..utils import (
    get_all_english_entries_by_version,
    get_english_entry,
    write_json_file,
)
from ..utils.exceptions import ParserExecutionError
from .evolution import EvolutionResolver, evolution_parent
from .generation import GenerationParser
from .history import apply_past_values
from .media import select_cries, select_sprites

logger = getLogger(__name__)


class PokemonParser(GenerationParser):
    """
    A comprehensive parser for Pokémon species and all their forms/varieties.

    This is the most complex parser as it handles:
    - Default/primary Pokémon forms
    - Regional variants (e.g., Alolan, Galarian forms)
    - Battle-only transformations (e.g., Mega Evolution, Gigantamax)
    - Cosmetic forms (e.g., Unown letters, Spinda patterns)
    - Historical types, abilities, and stats from structured PokéAPI data
    - Evolution chains with generation filtering
    - Moves, held items, and sprites per generation

    The parser organizes output into four categories defined by PokemonCategory.
    """

    def __init__(
        self,
        config: Config,
        api_client: ApiClient,
        generation_version_groups: dict[int, list[str]],
        target_gen: int,
        generation_dex_map: dict[int, str],
        is_historical: bool = False,
        target_versions: set[str] | None = None,
    ):
        super().__init__(
            config,
            api_client,
            generation_version_groups,
            target_gen,
            generation_dex_map,
            is_historical,
        )
        self.entity_type = "Species"
        self.api_endpoint = "pokemon_species"
        self.output_dir_key_pokemon = "output_dir_pokemon"
        self.output_dir_key_variant = "output_dir_variant"
        self.output_dir_key_transformation = "output_dir_transformation"
        self.output_dir_key_cosmetic = "output_dir_cosmetic"
        self.target_versions = target_versions or set()
        self.evolutions = EvolutionResolver(
            config, api_client, generation_version_groups, target_gen
        )

    def _get_generation_data(
        self,
        data: dict[str, Any],
        key: str,
        name_key: str,
        details_key: str,
        version_key: str,
    ) -> dict[str, Any]:
        """A generic helper to filter data by the target generation."""
        gen_data: dict[str, Any] = {}
        if not self.generation_version_groups or self.target_gen is None:
            return {}

        target_groups = self.generation_version_groups.get(self.target_gen, [])

        for item in data.get(key, []):
            item_name = item[name_key]["name"]
            for details in item[details_key]:
                entity_name = details[version_key]["name"]

                is_relevant = False
                if key == "moves":
                    is_relevant = entity_name in target_groups
                elif key == "held_items":
                    is_relevant = entity_name in self.target_versions

                if is_relevant:
                    if key == "moves":
                        method = details["move_learn_method"]["name"]
                        level = details["level_learned_at"]
                        move_key = (item_name, level)
                        if method not in gen_data:
                            gen_data[method] = {}
                        if move_key not in gen_data[method]:
                            gen_data[method][move_key] = set()
                        gen_data[method][move_key].add(entity_name)
                    elif key == "held_items":
                        if item_name not in gen_data:
                            gen_data[item_name] = {}
                        gen_data[item_name][entity_name] = details["rarity"]

        if key == "moves":
            processed_moves: dict[str, Any] = {}
            for method, move_groups in gen_data.items():
                processed_moves[method] = []
                for (move_name, level), games in move_groups.items():
                    processed_moves[method].append(
                        {
                            "name": move_name,
                            "level_learned_at": level,
                            "version_groups": sorted(list(games)),
                        }
                    )
            return processed_moves

        return gen_data

    def _get_generation_pokedex_numbers(
        self, pokedex_numbers: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Filters Pokédex numbers for national and the target generation's regional dex."""
        gen_numbers: dict[str, int] = {}
        if not self.generation_dex_map or self.target_gen is None:
            return {}
        regional_dex_name = self.generation_dex_map.get(self.target_gen)
        for entry in pokedex_numbers:
            pokedex_name = entry["pokedex"]["name"]
            if pokedex_name == "national" or pokedex_name == regional_dex_name:
                gen_numbers[pokedex_name] = entry["entry_number"]
        return gen_numbers

    def _get_varieties_with_default(
        self, species_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Gets varieties list from species data, creating a synthetic default variety if none exist.

        Args:
            species_data: The species API data

        Returns:
            List of variety dictionaries, guaranteed to have at least one entry
        """
        varieties = species_data.get("varieties", [])
        if not varieties:
            species_name = species_data["name"]
            default_pokemon_url = (
                f"{self.config.api_base_url}pokemon/{species_data['id']}"
            )
            default_variety = {
                "is_default": True,
                "pokemon": {"name": species_name, "url": default_pokemon_url},
            }
            varieties = [default_variety]
        return varieties

    def _should_skip_form(self, form_data: dict[str, Any]) -> bool:
        """Checks if a form should be skipped based on the target generation."""
        # Validate form_data structure
        if not form_data or not isinstance(form_data, dict):
            raise ParserExecutionError("Expected a non-empty form object")

        version_group = form_data.get("version_group")
        if not version_group or not isinstance(version_group, dict):
            return False

        version_group_url = version_group.get("url")
        if not version_group_url:
            return False

        try:
            version_group_data = self.api_client.get(version_group_url)
            if not version_group_data or not isinstance(version_group_data, dict):
                raise ParserExecutionError(
                    f"Invalid version group response from {version_group_url}"
                )

            generation = version_group_data.get("generation")
            if not generation or not isinstance(generation, dict):
                raise ParserExecutionError(
                    f"Missing or invalid generation in version group data from {version_group_url}"
                )

            generation_url = generation.get("url")
            if not generation_url:
                raise ParserExecutionError(
                    f"Missing generation URL in version group data from {version_group_url}"
                )

            form_introduction_gen = int(generation_url.split("/")[-2])
            return (
                self.target_gen is not None and form_introduction_gen > self.target_gen
            )
        except (ValueError, IndexError, KeyError) as e:
            raise ParserExecutionError(
                f"Could not determine form generation from {version_group_url}"
            ) from e

    def _build_base_pokemon_data(
        self,
        pokemon_data: dict[str, Any],
        species_data: dict[str, Any],
        source_url: str,
    ) -> dict[str, Any]:
        """Builds the common data dictionary for any Pokémon form or variety."""
        # Filter abilities based on generation (hidden abilities introduced in Gen 5)
        all_abilities = pokemon_data.get("abilities", [])
        if self.target_gen is not None and self.target_gen < 3:
            abilities = []
        elif self.target_gen is not None and self.target_gen < 5:
            # Remove hidden abilities for generations before Gen 5
            abilities = [
                {
                    "name": a["ability"]["name"],
                    "is_hidden": a["is_hidden"],
                    "slot": a["slot"],
                }
                for a in all_abilities
                if not a["is_hidden"]
            ]
        else:
            abilities = [
                {
                    "name": a["ability"]["name"],
                    "is_hidden": a["is_hidden"],
                    "slot": a["slot"],
                }
                for a in all_abilities
            ]

        cleaned_data = {
            "id": pokemon_data["id"],
            "name": pokemon_data["name"],
            "species": species_data["name"],
            "is_default": pokemon_data.get("is_default", False),
            "source_url": source_url,
            "types": [t["type"]["name"] for t in pokemon_data.get("types", [])],
            "abilities": abilities,
            "stats": {
                s["stat"]["name"]: s["base_stat"] for s in pokemon_data.get("stats", [])
            },
            "ev_yield": [
                {"stat": s["stat"]["name"], "effort": s["effort"]}
                for s in pokemon_data.get("stats", [])
                if s["effort"] > 0
            ],
            "height": pokemon_data["height"],
            "weight": pokemon_data["weight"],
            "cries": select_cries(pokemon_data.get("cries", {}), self.target_gen),
            "sprites": select_sprites(
                pokemon_data.get("sprites", {}), self.target_gen, self.is_historical
            ),
        }
        if self.target_gen is not None and self.target_gen < 3:
            cleaned_data["ev_yield"] = None
        apply_past_values(cleaned_data, pokemon_data, self.target_gen)
        return cleaned_data

    def _add_default_species_data(
        self,
        cleaned_data: dict[str, Any],
        pokemon_data: dict[str, Any],
        species_data: dict[str, Any],
        evolution_chain: dict[str, Any] | None,
    ):
        """Adds extra fields that only apply to the default species."""
        cleaned_data.update(
            {
                **self._get_pokemon_specific_data(pokemon_data),
                "base_happiness": species_data.get("base_happiness"),
                "capture_rate": species_data.get("capture_rate"),
                "hatch_counter": species_data.get("hatch_counter"),
                "gender_rate": species_data.get("gender_rate"),
                "has_gender_differences": species_data.get("has_gender_differences"),
                "is_baby": species_data.get("is_baby"),
                "is_legendary": species_data.get("is_legendary"),
                "is_mythical": species_data.get("is_mythical"),
                "forms_switchable": species_data.get("forms_switchable"),
                "order": species_data.get("order"),
                "growth_rate": (
                    species_data.get("growth_rate", {}).get("name")
                    if species_data.get("growth_rate")
                    else None
                ),
                "habitat": (
                    species_data.get("habitat", {}).get("name")
                    if species_data.get("habitat")
                    else None
                ),
                "evolves_from_species": evolution_parent(
                    evolution_chain, species_data["name"]
                ),
                "pokedex_numbers": self._get_generation_pokedex_numbers(
                    species_data.get("pokedex_numbers", [])
                ),
                "color": (
                    species_data.get("color", {}).get("name")
                    if species_data.get("color")
                    else None
                ),
                "shape": (
                    species_data.get("shape", {}).get("name")
                    if species_data.get("shape")
                    else None
                ),
                "egg_groups": [
                    group["name"] for group in species_data.get("egg_groups", [])
                ],
                "flavor_text": get_all_english_entries_by_version(
                    species_data.get("flavor_text_entries", []),
                    "flavor_text",
                    self.target_versions,
                ),
                "genus": get_english_entry(species_data.get("genera", []), "genus"),
                "generation": species_data.get("generation", {}).get("name"),
                "evolution_chain": evolution_chain,
            }
        )
        self._flag_unverified_historical_fields(
            cleaned_data,
            [
                "base_happiness",
                "capture_rate",
                "hatch_counter",
                "gender_rate",
                "egg_groups",
                "growth_rate",
                "forms_switchable",
                "base_experience",
            ],
        )
        if self.target_gen is not None and self.target_gen < 2:
            cleaned_data.update(
                {
                    "base_happiness": None,
                    "hatch_counter": None,
                    "gender_rate": None,
                    "egg_groups": None,
                }
            )

    def _get_pokemon_specific_data(
        self, pokemon_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Returns fields that belong to a Pokémon variety rather than its species."""
        return {
            "base_experience": pokemon_data.get("base_experience"),
            "held_items": self._get_generation_data(
                pokemon_data, "held_items", "item", "version_details", "version"
            ),
            "moves": self._get_generation_data(
                pokemon_data,
                "moves",
                "move",
                "version_group_details",
                "version_group",
            ),
        }

    def _collect_varieties_and_forms(
        self,
        species_data: dict[str, Any],
        default_pokemon_data: dict[str, Any],
    ) -> tuple[
        list[dict[str, Any]], list[dict[str, str]], set[str], dict[str, dict[str, Any]]
    ]:
        """
        Collects and categorizes all varieties and forms for a species.

        Args:
            species_data: The species API data
            default_pokemon_data: The default Pokemon's API data

        Returns:
            A tuple of (varieties, all_forms_in_gen, variety_form_urls, variety_data_cache):
            - varieties: List of variety dictionaries from the API, or a synthetic
                         default variety if none exist
            - all_forms_in_gen: List of form names and categories in the target generation
            - variety_form_urls: Set of form URLs that belong to varieties
            - variety_data_cache: Dict mapping variety URLs to their fetched pokemon data
        """
        varieties = self._get_varieties_with_default(species_data)

        all_forms_in_gen: list[dict[str, str]] = []
        variety_form_urls: set[str] = set()
        variety_data_cache: dict[str, dict[str, Any]] = {}

        # Process varieties to categorize their forms
        for variety in varieties:
            variety_url = variety["pokemon"]["url"]
            try:
                pokemon_data = self.api_client.get(variety_url)
            except Exception as e:
                raise ParserExecutionError(
                    f"Could not fetch variety {variety_url}"
                ) from e

            # Cache the pokemon data for later use
            variety_data_cache[variety_url] = pokemon_data

            # Skip varieties with no forms - will be filtered in _process_variety
            forms = pokemon_data.get("forms", [])
            if not forms:
                logger.debug(
                    f"Variety {pokemon_data['name']} has no forms, will be skipped during processing."
                )
                continue

            # Note: We always use forms[0] because each variety should have exactly one
            # primary form that represents it. Additional cosmetic forms are handled separately.
            form_ref_url = forms[0].get("url") if forms else None
            if form_ref_url:
                variety_form_urls.add(form_ref_url)
                try:
                    form_data = self.api_client.get(form_ref_url)
                    if not self._should_skip_form(form_data):
                        category = "variant"
                        if variety.get("is_default"):
                            category = "default"
                        elif form_data.get("is_battle_only"):
                            category = "transformation"
                        all_forms_in_gen.append(
                            {"name": pokemon_data["name"], "category": category}
                        )
                except Exception as e:
                    raise ParserExecutionError(
                        f"Could not fetch form {form_ref_url}"
                    ) from e

        # Process cosmetic forms (forms that don't have varieties)
        all_form_urls = {form["url"] for form in default_pokemon_data.get("forms", [])}
        for form_url in all_form_urls - variety_form_urls:
            try:
                form_data = self.api_client.get(form_url)
                if not self._should_skip_form(form_data) and not form_data.get(
                    "is_default"
                ):
                    form_name = form_data.get("name")
                    if not form_name:
                        raise ParserExecutionError(
                            f"Cosmetic form at {form_url} has no name"
                        )
                    all_forms_in_gen.append({"name": form_name, "category": "cosmetic"})
            except Exception as e:
                raise ParserExecutionError(
                    f"Could not fetch cosmetic form {form_url}"
                ) from e

        all_forms_in_gen.sort(key=lambda x: x["name"])
        return varieties, all_forms_in_gen, variety_form_urls, variety_data_cache

    def _process_default_pokemon(
        self,
        default_variety: dict[str, Any],
        default_pokemon_data: dict[str, Any],
        species_data: dict[str, Any],
        evolution_chain: dict[str, Any] | None,
        all_forms_in_gen: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Processes the default/primary Pokemon form.

        Args:
            default_variety: The default variety from the API
            default_pokemon_data: The default Pokemon's API data
            species_data: The species API data
            evolution_chain: The evolution chain data
            all_forms_in_gen: List of all forms in the target generation

        Returns:
            The processed default Pokemon data dictionary
        """
        default_template = self._build_base_pokemon_data(
            default_pokemon_data, species_data, default_variety["pokemon"]["url"]
        )
        self._add_default_species_data(
            default_template, default_pokemon_data, species_data, evolution_chain
        )
        default_template["forms"] = all_forms_in_gen

        output_dir = str(self.config.output_path(self.output_dir_key_pokemon))
        write_json_file(output_dir, default_template["name"], default_template)

        return default_template

    def _process_variety(
        self,
        variety: dict[str, Any],
        species_data: dict[str, Any],
        default_template: dict[str, Any],
        variety_data_cache: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[str, dict[str, Any]] | None:
        """
        Processes a single variety (variant or transformation).

        Args:
            variety: The variety data from the API
            species_data: The species API data
            default_template: The default Pokemon template to base this variety on
            variety_data_cache: Optional cached pokemon data to avoid redundant API calls

        Returns:
            A tuple of (category, summary_dict) where category is either "variant" or
            "transformation", or None if the variety should be skipped
        """
        variety_url = variety["pokemon"]["url"]

        # Use cached data if available, otherwise fetch from API
        if variety_data_cache and variety_url in variety_data_cache:
            pokemon_data = variety_data_cache[variety_url]
        else:
            pokemon_data = self.api_client.get(variety_url)

        # Skip varieties with no forms
        if not pokemon_data.get("forms"):
            logger.debug(f"Skipping variety {pokemon_data['name']}: No forms found.")
            return None

        forms = pokemon_data.get("forms", [])
        # Note: We always use forms[0] because each variety should have exactly one
        # primary form that represents it. Additional cosmetic forms are handled separately.
        form_ref_url = forms[0].get("url") if forms else None

        form_data = self.api_client.get(form_ref_url) if form_ref_url else {}
        if self._should_skip_form(form_data):
            return None

        # Create variant data by copying default and updating with variety-specific info
        variant_data = copy.deepcopy(default_template)
        variant_base_data = self._build_base_pokemon_data(
            pokemon_data, species_data, variety["pokemon"]["url"]
        )
        variant_data.update(variant_base_data)
        variant_data.update(self._get_pokemon_specific_data(pokemon_data))

        # Determine category and output directory
        is_battle_only = form_data.get("is_battle_only", False)
        if is_battle_only:
            output_key, summary_key = (
                self.output_dir_key_transformation,
                "transformation",
            )
        else:
            output_key, summary_key = self.output_dir_key_variant, "variant"

        # Write to file
        output_dir = str(self.config.output_path(output_key))
        write_json_file(output_dir, variant_data["name"], variant_data)

        # Return summary
        summary = {
            "name": variant_data["name"],
            "id": variant_data["id"],
            "sprite": variant_data["sprites"].get("front_default"),
        }
        return summary_key, summary

    def _process_cosmetic_form(
        self,
        form_url: str,
        default_template: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Processes a single cosmetic form.

        Args:
            form_url: The API URL for the form
            default_template: The default Pokemon template to base this form on

        Returns:
            A summary dictionary or None if the form should be skipped
        """
        form_data = self.api_client.get(form_url)

        if self._should_skip_form(form_data) or form_data.get("is_default"):
            return None

        # Create cosmetic data by copying default and updating sprites
        cosmetic_data = copy.deepcopy(default_template)
        cosmetic_data["name"] = form_data.get("name", default_template["name"])
        cosmetic_data["is_default"] = False

        cosmetic_data["sprites"] = select_sprites(
            form_data.get("sprites", {}), self.target_gen, self.is_historical
        )
        # Write to file
        output_dir = str(self.config.output_path(self.output_dir_key_cosmetic))
        write_json_file(output_dir, cosmetic_data["name"], cosmetic_data)

        # Return summary
        return {
            "name": cosmetic_data["name"],
            "id": cosmetic_data["id"],
            "sprite": cosmetic_data["sprites"].get("front_default"),
        }

    def process(
        self, resource_ref: dict[str, str]
    ) -> dict[str, list[dict[str, Any]]] | str | None:
        """
        Processes a Pokémon species and all its varieties and forms.

        This method orchestrates the processing of:
        - Default Pokémon form with full species data
        - All regional variants and their differences
        - Battle-only transformations (Megas, Gigantamax, etc.)
        - Cosmetic forms (Unown, Spinda, etc.)

        Args:
            resource_ref: Dictionary with 'name' and 'url' for the species

        Returns:
            A dict with category keys mapping to lists of summary dicts,
            or an error string if processing fails
        """
        species_name = ""
        try:
            # Fetch species and evolution data
            species_data = self.api_client.get(resource_ref["url"])
            species_name = species_data["name"]
            evolution_chain_url = species_data.get("evolution_chain", {}).get("url")
            evolution_chain = (
                self.evolutions.get_chain(evolution_chain_url, species_data["name"])
                if evolution_chain_url
                else None
            )

            # Initialize summaries
            summaries: dict[str, list[dict[str, Any]]] = {
                "pokemon": [],
                "variant": [],
                "transformation": [],
                "cosmetic": [],
            }

            # Get default variety and its data
            varieties = self._get_varieties_with_default(species_data)

            default_variety = next((v for v in varieties if v["is_default"]), None)
            if not default_variety:
                logger.warning(
                    f"No default variety found for {species_name}, using first variety"
                )
                default_variety = varieties[0]
            default_pokemon_data = self.api_client.get(
                default_variety["pokemon"]["url"]
            )

            # Skip species with no forms (placeholder entries)
            if not default_pokemon_data.get("forms"):
                logger.info(
                    f"Skipping {species_name}: No forms found in default pokemon data."
                )
                return None

            # Collect and categorize all varieties and forms
            varieties, all_forms_in_gen, variety_form_urls, variety_data_cache = (
                self._collect_varieties_and_forms(species_data, default_pokemon_data)
            )

            # Process default Pokemon
            default_template = self._process_default_pokemon(
                default_variety,
                default_pokemon_data,
                species_data,
                evolution_chain,
                all_forms_in_gen,
            )
            summaries["pokemon"].append(
                {
                    "name": default_template["name"],
                    "id": default_template["id"],
                    "sprite": default_template["sprites"].get("front_default"),
                }
            )

            # Process varieties (variants and transformations)
            processed_urls = {default_variety["pokemon"]["url"]}
            for variety in varieties:
                if variety["pokemon"]["url"] in processed_urls:
                    continue

                result = self._process_variety(
                    variety, species_data, default_template, variety_data_cache
                )
                if result:
                    summary_key, summary = result
                    summaries[summary_key].append(summary)
                    processed_urls.add(variety["pokemon"]["url"])

            # Process cosmetic forms
            all_form_urls = {
                form["url"] for form in default_pokemon_data.get("forms", [])
            }
            for form_url in all_form_urls - variety_form_urls:
                summary = self._process_cosmetic_form(form_url, default_template)
                if summary:
                    summaries["cosmetic"].append(summary)

            return summaries
        except Exception as e:
            if not species_name:
                species_name = resource_ref.get("name", "unknown")
            logger.error(f"Unexpected error processing {species_name}: {e}")
            return f"Parsing failed for {species_name}: {e}"
