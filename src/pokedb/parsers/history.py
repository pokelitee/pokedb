"""Historical Pokémon values reconstructed from structured API records."""

from typing import Any


def apply_past_values(
    cleaned_data: dict, pokemon_data: dict, target_gen: int | None
) -> None:
    """Applies PokéAPI's structured historical types, abilities, and stats."""
    if target_gen is None:
        return

    def ending_generation(entry: dict[str, Any]) -> int:
        generation_url = (entry.get("generation") or {}).get("url", "")
        try:
            return int(generation_url.rstrip("/").rsplit("/", 1)[-1])
        except ValueError:
            return 999

    applicable_types = sorted(
        (
            entry
            for entry in pokemon_data.get("past_types", [])
            if ending_generation(entry) >= target_gen
        ),
        key=ending_generation,
    )
    if applicable_types:
        cleaned_data["types"] = [
            entry["type"]["name"]
            for entry in sorted(
                applicable_types[0].get("types", []),
                key=lambda entry: entry["slot"],
            )
        ]

    abilities_by_slot = {
        ability["slot"]: ability for ability in cleaned_data["abilities"]
    }
    applied_ability_slots: set[int] = set()
    for past in sorted(pokemon_data.get("past_abilities", []), key=ending_generation):
        if ending_generation(past) < target_gen:
            continue
        for ability in past.get("abilities", []):
            slot = ability["slot"]
            if slot in applied_ability_slots:
                continue
            ability_ref = ability.get("ability")
            if ability_ref is None:
                abilities_by_slot.pop(slot, None)
            else:
                abilities_by_slot[slot] = {
                    "name": ability_ref["name"],
                    "is_hidden": ability["is_hidden"],
                    "slot": slot,
                }
            applied_ability_slots.add(slot)
    cleaned_data["abilities"] = [
        abilities_by_slot[slot] for slot in sorted(abilities_by_slot)
    ]
    if target_gen < 3:
        cleaned_data["abilities"] = []
    elif target_gen < 5:
        cleaned_data["abilities"] = [
            ability for ability in cleaned_data["abilities"] if not ability["is_hidden"]
        ]

    stats = cleaned_data["stats"]
    effort_by_stat = {
        entry["stat"]: entry["effort"] for entry in (cleaned_data["ev_yield"] or [])
    }
    applied_stats: set[str] = set()
    for past in sorted(pokemon_data.get("past_stats", []), key=ending_generation):
        if ending_generation(past) < target_gen:
            continue
        for stat in past.get("stats", []):
            stat_name = stat["stat"]["name"]
            if "special" in stats and stat_name in {
                "special-attack",
                "special-defense",
            }:
                continue
            if stat_name in applied_stats:
                continue
            if stat_name == "special":
                stats.pop("special-attack", None)
                stats.pop("special-defense", None)
                effort_by_stat.pop("special-attack", None)
                effort_by_stat.pop("special-defense", None)
            stats[stat_name] = stat["base_stat"]
            if stat["effort"] > 0:
                effort_by_stat[stat_name] = stat["effort"]
            else:
                effort_by_stat.pop(stat_name, None)
            applied_stats.add(stat_name)
    cleaned_data["ev_yield"] = [
        {"stat": stat, "effort": effort} for stat, effort in effort_by_stat.items()
    ]
    if target_gen < 3:
        cleaned_data["ev_yield"] = None
