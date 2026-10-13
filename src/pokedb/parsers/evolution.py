"""Generation-aware evolution relationships and conditions."""

from typing import Any

from ..api_client import ApiClient
from ..config import Config
from ..utils.exceptions import ParserExecutionError


def evolution_parent(chain: dict[str, Any] | None, species: str) -> str | None:
    """Returns the species' parent in the reconstructed generation chain."""
    if chain is None:
        return None
    for child in chain["evolves_to"]:
        if child["species_name"] == species:
            return chain["species_name"]
        parent = evolution_parent(child, species)
        if parent is not None:
            return parent
    return None


class EvolutionResolver:
    """Reconstructs evolution chains using one generation's metadata."""

    def __init__(
        self,
        config: Config,
        api_client: ApiClient,
        generation_version_groups: dict[int, list[str]],
        target_gen: int,
    ):
        self.config = config
        self.api_client = api_client
        self.generation_version_groups = generation_version_groups
        self.target_gen = target_gen
        self._version_group_regions: dict[str, set[str]] = {}
        self._location_regions: dict[str, str | None] = {}
        self._species_generations: dict[str, int] = {}

    @staticmethod
    def _clean_evolution_detail(
        details: dict[str, Any], version_groups: list[str] | None = None
    ) -> dict[str, Any]:
        """Normalizes one evolution condition returned by PokéAPI."""
        return {
            "introduced_in_version_group": (details.get("version_group") or {}).get(
                "name"
            ),
            "version_groups": version_groups or [],
            "base_form": (details.get("base_form") or {}).get("name"),
            "evolved_form": (details.get("evolved_form") or {}).get("name"),
            "item": (details.get("item") or {}).get("name"),
            "trigger": (details.get("trigger") or {}).get("name"),
            "gender": details.get("gender"),
            "held_item": (details.get("held_item") or {}).get("name"),
            "known_move": (details.get("known_move") or {}).get("name"),
            "known_move_type": (details.get("known_move_type") or {}).get("name"),
            "location": (details.get("location") or {}).get("name"),
            "min_level": details.get("min_level"),
            "min_happiness": details.get("min_happiness"),
            "min_beauty": details.get("min_beauty"),
            "min_affection": details.get("min_affection"),
            "min_damage_taken": details.get("min_damage_taken"),
            "min_move_count": details.get("min_move_count"),
            "min_steps": details.get("min_steps"),
            "near_special_rock": details.get("near_special_rock", False),
            "needs_multiplayer": details.get("needs_multiplayer", False),
            "needs_overworld_rain": details.get("needs_overworld_rain"),
            "party_species": (details.get("party_species") or {}).get("name"),
            "party_type": (details.get("party_type") or {}).get("name"),
            "relative_physical_stats": details.get("relative_physical_stats"),
            "region": (details.get("region") or {}).get("name"),
            "time_of_day": details.get("time_of_day") or None,
            "trade_species": (details.get("trade_species") or {}).get("name"),
            "turn_upside_down": details.get("turn_upside_down"),
            "used_move": (details.get("used_move") or {}).get("name"),
        }

    def details_for_target(
        self, details_list: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Reconstructs the active conditions for each target version group."""
        target_groups = self.generation_version_groups.get(self.target_gen, [])
        if not target_groups:
            return [self._clean_evolution_detail(details) for details in details_list]

        group_order = {
            group: (generation, position)
            for generation, groups in self.generation_version_groups.items()
            for position, group in enumerate(groups)
        }
        merged_details: dict[str, dict[str, Any]] = {}

        for target_group in target_groups:
            target_order = group_order.get(target_group)
            if target_order is None:
                continue
            eligible = [
                details
                for details in details_list
                if group_order.get(
                    (details.get("version_group") or {}).get("name"),
                    (999, 999),
                )
                <= target_order
            ]
            if not eligible:
                eligible = [
                    details
                    for details in details_list
                    if not details.get("version_group")
                ]
            if not eligible:
                continue

            latest_order = max(
                group_order.get(
                    (details.get("version_group") or {}).get("name"),
                    (-1, -1),
                )
                for details in eligible
            )
            active_details = [
                details
                for details in eligible
                if group_order.get(
                    (details.get("version_group") or {}).get("name"),
                    (-1, -1),
                )
                == latest_order
                and self._is_evolution_detail_available(details, target_group)
            ]
            for details in active_details:
                cleaned = self._clean_evolution_detail(details)
                signature = repr(cleaned)
                if signature not in merged_details:
                    merged_details[signature] = cleaned
                merged_details[signature]["version_groups"].append(target_group)

        return list(merged_details.values())

    def _is_evolution_detail_available(
        self, details: dict[str, Any], target_group: str
    ) -> bool:
        """Rejects location evolutions in games that cannot access that region."""
        location = details.get("location") or {}
        location_url = location.get("url")
        if not location_url or self.api_client is None:
            return True

        if target_group not in self._version_group_regions:
            version_group = self.api_client.get(
                f"{self.config.api_base_url}version-group/{target_group}"
            )
            self._version_group_regions[target_group] = {
                region["name"] for region in version_group.get("regions", [])
            }
        if location_url not in self._location_regions:
            location_data = self.api_client.get(location_url)
            self._location_regions[location_url] = (
                location_data.get("region") or {}
            ).get("name")

        location_region = self._location_regions[location_url]
        target_regions = self._version_group_regions[target_group]
        return (
            not location_region
            or not target_regions
            or location_region in target_regions
        )

    def get_chain(
        self, chain_url: str, target_species: str | None = None
    ) -> dict[str, Any] | None:
        """
        Recursively fetches and processes an evolution chain, filtering future generations.

        Evolution chains are nested structures showing species → evolutions → further evolutions.
        This method filters out evolutions that don't exist in the target generation.

        Args:
            chain_url: API URL for the evolution chain endpoint

        Returns:
            A nested dictionary representing the evolution chain, or None if no species remain.
            Structure: {
                "species_name": str,
                "evolves_to": [
                    {
                        "species_name": str,
                        "evolution_details": {...},
                        "evolves_to": [...]
                    }
                ]
            }
        """
        response = self.api_client.get(chain_url)
        if not isinstance(response, dict) or not isinstance(
            response.get("chain"), dict
        ):
            raise ParserExecutionError(
                f"Invalid evolution chain response from {chain_url}"
            )

        chain_data = response["chain"]

        def species_generation(species: dict[str, Any]) -> int:
            species_url = species.get("url")
            if not species_url or self.target_gen is None:
                return self.target_gen or 1
            if species_url not in self._species_generations:
                species_data = self.api_client.get(species_url)
                self._species_generations[species_url] = int(
                    species_data["generation"]["url"].split("/")[-2]
                )
            return self._species_generations[species_url]

        def recurse_chain(chain: dict[str, Any]) -> list[dict[str, Any]]:
            species = chain["species"]
            species_name = species["name"]
            is_future = (
                self.target_gen is not None
                and species_generation(species) > self.target_gen
            )
            if is_future:
                promoted: list[dict[str, Any]] = []
                for evolution in chain.get("evolves_to", []):
                    promoted.extend(recurse_chain(evolution))
                return promoted

            evolves_to: list[dict[str, Any]] = []

            for evolution in chain.get("evolves_to", []):
                if (
                    self.target_gen is not None
                    and species_generation(evolution["species"]) > self.target_gen
                ):
                    continue
                raw_details = evolution.get("evolution_details", [])
                # Empty details in PokeAPI represent special relationships
                # such as Phione/Manaphy, not an evolution method.
                if not raw_details:
                    continue
                next_nodes = recurse_chain(evolution)
                if not next_nodes:
                    continue
                active_details = self.details_for_target(raw_details)
                next_evolution = next_nodes[0]
                evolves_to.append(
                    {
                        "species_name": next_evolution["species_name"],
                        "availability": (
                            "available" if active_details else "unavailable"
                        ),
                        "evolution_details": active_details,
                        "evolves_to": next_evolution["evolves_to"],
                    }
                )
            return [{"species_name": species_name, "evolves_to": evolves_to}]

        roots = recurse_chain(chain_data)
        if not roots:
            return None
        if target_species is None:
            return roots[0]

        def contains_species(node: dict[str, Any]) -> bool:
            return node["species_name"] == target_species or any(
                contains_species(child) for child in node["evolves_to"]
            )

        matching = next((root for root in roots if contains_species(root)), None)
        if matching is not None:
            return matching

        def find_species(node: dict[str, Any]) -> dict[str, Any] | None:
            if node["species"]["name"] == target_species:
                return node
            for child in node.get("evolves_to", []):
                found = find_species(child)
                if found is not None:
                    return found
            return None

        isolated = find_species(chain_data)
        if isolated is not None:
            isolated_roots = recurse_chain(isolated)
            if isolated_roots:
                return isolated_roots[0]
        raise ParserExecutionError(
            f"Species {target_species} absent from its evolution chain"
        )
