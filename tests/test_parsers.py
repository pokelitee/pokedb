from dataclasses import replace

import pytest

from pokedb.config import load_config
from pokedb.parsers.ability import AbilityParser
from pokedb.parsers.base import BaseParser
from pokedb.parsers.history import apply_past_values
from pokedb.parsers.item import ItemParser
from pokedb.parsers.move import MoveParser
from pokedb.parsers.pokemon import PokemonParser
from pokedb.utils.exceptions import ParserExecutionError


class FailingParser(BaseParser):
    def __init__(self):
        super().__init__(load_config(), api_client=None)
        self.entity_type = "Test"
        self.api_endpoint = "test"

    def _get_all_item_refs(self):
        return [{"name": "broken", "url": "https://example.invalid/broken"}]

    def process(self, resource_ref):
        return f"Parsing failed for {resource_ref['name']}"


def test_parser_errors_fail_the_run():
    with pytest.raises(ParserExecutionError):
        FailingParser().run()


def test_move_history_uses_nearest_future_change_per_field():
    parser = MoveParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={
            5: ["black-white"],
            6: ["x-y"],
            8: ["sword-shield"],
        },
        target_gen=5,
    )
    cleaned_data = {
        "accuracy": 100,
        "power": 120,
        "pp": 5,
        "effect_chance": None,
        "type": "normal",
        "effect": "current",
        "short_effect": "current",
    }
    past_values = [
        {"version_group": {"name": "x-y"}, "power": 80},
        {
            "version_group": {"name": "sword-shield"},
            "power": 100,
            "pp": 10,
        },
    ]

    parser._apply_past_values(cleaned_data, past_values)

    assert cleaned_data["power"]["black-white"] == 80
    assert cleaned_data["pp"]["black-white"] == 10


def test_non_historical_move_has_empty_unverified_historical_fields():
    parser = MoveParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={9: ["scarlet-violet"]},
        target_gen=9,
        is_historical=False,
    )
    cleaned_data = {
        "priority": 0,
        "damage_class": "physical",
        "target": "selected-pokemon",
        "metadata": {},
        "stat_changes": [],
        "type": {"scarlet-violet": "normal"},
    }

    parser._apply_generation_policy(cleaned_data)

    assert cleaned_data["unverified_historical_fields"] == []


def test_pre_generation_four_damage_class_is_derived_from_type():
    parser = MoveParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={3: ["ruby-sapphire"]},
        target_gen=3,
        is_historical=True,
    )
    cleaned_data = {
        "priority": 0,
        "damage_class": "physical",
        "target": "selected-pokemon",
        "metadata": {},
        "stat_changes": [],
        "type": {"ruby-sapphire": "dark"},
    }

    parser._apply_generation_policy(cleaned_data)

    assert cleaned_data["damage_class"] == "special"
    assert cleaned_data["priority"] == 0
    assert cleaned_data["target"] == "selected-pokemon"
    assert cleaned_data["metadata"] == {}
    assert cleaned_data["stat_changes"] == []
    assert cleaned_data["unverified_historical_fields"] == [
        "priority",
        "target",
        "metadata",
        "stat_changes",
    ]


def test_historical_item_current_only_fields_are_flagged_unverified():
    parser = ItemParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={4: ["diamond-pearl"]},
        target_gen=4,
        is_historical=True,
    )
    cleaned_data = {
        "fling_power": 30,
        "fling_effect": "damage",
        "attributes": ["holdable"],
        "category": "medicine",
        "effect": "Current effect",
        "short_effect": "Current effect",
        "sprite": "https://example.test/item.png",
    }
    original_values = dict(cleaned_data)

    parser._apply_generation_policy(cleaned_data)

    for field, value in original_values.items():
        assert cleaned_data[field] == value
    assert set(cleaned_data["unverified_historical_fields"]) == set(original_values)


def test_referenced_item_without_game_indices_is_included(tmp_path):
    item_url = "https://example.test/item/fire-stone"
    item_data = {
        "id": 82,
        "name": "fire-stone",
        "game_indices": [],
        "prices": [],
        "fling_power": 30,
        "fling_effect": None,
        "attributes": [],
        "category": {"name": "evolution"},
        "effect_entries": [],
        "flavor_text_entries": [],
        "sprites": {"default": None},
    }

    class FakeApiClient:
        def get(self, url):
            assert url == item_url
            return item_data

    config = replace(load_config(), output_root=tmp_path).for_generation(1)
    parser = ItemParser(
        config=config,
        api_client=FakeApiClient(),
        generation_version_groups={1: ["red-blue"]},
        target_gen=1,
    )
    parser.referenced_item_names = {"fire-stone"}

    result = parser.process({"name": "fire-stone", "url": item_url})

    assert result["name"] == "fire-stone"
    assert (tmp_path / "gen1/item/fire-stone.json").exists()


def test_ability_history_uses_nearest_future_change():
    parser = AbilityParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={
            4: ["diamond-pearl"],
            5: ["black-white"],
            9: ["scarlet-violet"],
        },
        target_gen=4,
    )
    data = {
        "effect_entries": [
            {
                "language": {"name": "en"},
                "effect": "Current effect",
                "short_effect": "Current short effect",
            }
        ],
        "effect_changes": [
            {
                "version_group": {"name": "black-white"},
                "effect_entries": [
                    {
                        "language": {"name": "en"},
                        "effect": "Previous effect",
                    }
                ],
            }
        ],
    }

    effects, short_effects = parser._get_effects_for_target_generation(data)

    assert effects == {"diamond-pearl": "Previous effect"}
    assert short_effects == {"diamond-pearl": "Current short effect"}


def test_ability_effects_always_use_version_group_maps():
    parser = AbilityParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={9: ["scarlet-violet", "the-teal-mask"]},
        target_gen=9,
    )
    data = {
        "effect_entries": [
            {
                "language": {"name": "en"},
                "effect": "Current effect",
                "short_effect": "Current short effect",
            }
        ],
        "effect_changes": [],
    }

    effects, short_effects = parser._get_effects_for_target_generation(data)

    assert effects == {
        "scarlet-violet": "Current effect",
        "the-teal-mask": "Current effect",
    }
    assert set(short_effects) == {"scarlet-violet", "the-teal-mask"}


def test_pokemon_specific_data_comes_from_each_variety():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={9: ["scarlet-violet"]},
        target_gen=9,
        generation_dex_map={},
        target_versions={"scarlet"},
    )
    pokemon_data = {
        "base_experience": 182,
        "held_items": [],
        "moves": [
            {
                "move": {"name": "hydro-pump"},
                "version_group_details": [
                    {
                        "version_group": {"name": "scarlet-violet"},
                        "move_learn_method": {"name": "level-up"},
                        "level_learned_at": 1,
                    }
                ],
            }
        ],
    }

    result = parser._get_pokemon_specific_data(pokemon_data)

    assert result["base_experience"] == 182
    assert result["moves"]["level-up"][0]["name"] == "hydro-pump"


def test_historical_pokemon_backfills_current_base_experience():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={8: ["sword-shield"]},
        target_gen=8,
        generation_dex_map={},
        is_historical=True,
    )

    result = parser._get_pokemon_specific_data(
        {"base_experience": 182, "held_items": [], "moves": []}
    )

    assert result["base_experience"] == 182


def test_structured_pokeapi_history_is_applied():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={1: ["red-blue"]},
        target_gen=1,
        generation_dex_map={},
    )
    cleaned_data = {
        "types": ["electric", "steel"],
        "abilities": [
            {"name": "magnet-pull", "is_hidden": False, "slot": 1},
            {"name": "sturdy", "is_hidden": False, "slot": 2},
        ],
        "stats": {
            "hp": 25,
            "attack": 35,
            "defense": 70,
            "special-attack": 95,
            "special-defense": 55,
            "speed": 45,
        },
        "ev_yield": [{"stat": "special-attack", "effort": 1}],
    }
    pokemon_data = {
        "past_types": [
            {
                "generation": {"url": "https://example.test/generation/1/"},
                "types": [{"slot": 1, "type": {"name": "electric"}}],
            }
        ],
        "past_abilities": [
            {
                "generation": {"url": "https://example.test/generation/3/"},
                "abilities": [{"ability": None, "is_hidden": False, "slot": 2}],
            }
        ],
        "past_stats": [
            {
                "generation": {"url": "https://example.test/generation/1/"},
                "stats": [
                    {
                        "base_stat": 95,
                        "effort": 0,
                        "stat": {"name": "special"},
                    }
                ],
            }
        ],
    }

    apply_past_values(cleaned_data, pokemon_data, parser.target_gen)

    assert cleaned_data["types"] == ["electric"]
    assert cleaned_data["abilities"] == []
    assert cleaned_data["ev_yield"] is None
    assert cleaned_data["stats"] == {
        "hp": 25,
        "attack": 35,
        "defense": 70,
        "special": 95,
        "speed": 45,
    }


def test_structured_pokeapi_past_ability_replaces_current_ability():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={6: ["x-y"]},
        target_gen=6,
        generation_dex_map={},
    )
    cleaned_data = {
        "types": ["ghost", "poison"],
        "abilities": [{"name": "cursed-body", "is_hidden": False, "slot": 1}],
        "stats": {},
        "ev_yield": [],
    }
    pokemon_data = {
        "past_types": [],
        "past_stats": [],
        "past_abilities": [
            {
                "generation": {"url": "https://example.test/generation/6/"},
                "abilities": [
                    {
                        "ability": {"name": "levitate"},
                        "is_hidden": False,
                        "slot": 1,
                    }
                ],
            }
        ],
    }

    apply_past_values(cleaned_data, pokemon_data, parser.target_gen)

    assert cleaned_data["abilities"][0]["name"] == "levitate"


def test_evolution_details_preserve_each_condition():
    chain_url = "https://example.test/evolution-chain/1"
    species_url = "https://example.test/pokemon-species/vaporeon"
    responses = {
        chain_url: {
            "chain": {
                "species": {"name": "eevee"},
                "evolves_to": [
                    {
                        "species": {"name": "vaporeon", "url": species_url},
                        "evolution_details": [
                            {
                                "item": {"name": "water-stone"},
                                "trigger": {"name": "use-item"},
                            },
                            {
                                "location": {"name": "special-location"},
                                "trigger": {"name": "level-up"},
                            },
                        ],
                        "evolves_to": [],
                    }
                ],
            }
        },
        species_url: {"generation": {"url": "https://example.test/generation/1/"}},
    }

    class FakeApiClient:
        def get(self, url):
            return responses[url]

    parser = PokemonParser(
        config=load_config(),
        api_client=FakeApiClient(),
        generation_version_groups={},
        target_gen=9,
        generation_dex_map={},
    )
    chain = parser.evolutions.get_chain(chain_url)
    details = chain["evolves_to"][0]["evolution_details"]

    assert len(details) == 2
    assert chain["evolves_to"][0]["availability"] == "available"
    assert details[0]["item"] == "water-stone"
    assert details[1]["location"] == "special-location"


def test_evolution_chain_promotes_a_future_baby_root():
    chain_url = "https://example.test/evolution-chain/chansey"
    happiny_url = "https://example.test/species/happiny"
    chansey_url = "https://example.test/species/chansey"
    responses = {
        chain_url: {
            "chain": {
                "species": {"name": "happiny", "url": happiny_url},
                "evolution_details": [],
                "evolves_to": [
                    {
                        "species": {"name": "chansey", "url": chansey_url},
                        "evolution_details": [{"trigger": {"name": "level-up"}}],
                        "evolves_to": [],
                    }
                ],
            }
        },
        happiny_url: {"generation": {"url": "https://example.test/generation/4/"}},
        chansey_url: {"generation": {"url": "https://example.test/generation/1/"}},
    }

    class FakeApiClient:
        def get(self, url):
            return responses[url]

    parser = PokemonParser(
        config=load_config(),
        api_client=FakeApiClient(),
        generation_version_groups={1: ["red-blue"]},
        target_gen=1,
        generation_dex_map={},
    )

    chain = parser.evolutions.get_chain(chain_url)

    assert chain == {"species_name": "chansey", "evolves_to": []}


def test_empty_special_relationship_is_not_reported_as_evolution():
    chain_url = "https://example.test/evolution-chain/manaphy"
    phione_url = "https://example.test/species/phione"
    manaphy_url = "https://example.test/species/manaphy"
    responses = {
        chain_url: {
            "chain": {
                "species": {"name": "phione", "url": phione_url},
                "evolves_to": [
                    {
                        "species": {"name": "manaphy", "url": manaphy_url},
                        "evolution_details": [],
                        "evolves_to": [],
                    }
                ],
            }
        },
        phione_url: {"generation": {"url": "https://example.test/generation/4/"}},
        manaphy_url: {"generation": {"url": "https://example.test/generation/4/"}},
    }

    class FakeApiClient:
        def get(self, url):
            return responses[url]

    parser = PokemonParser(
        config=load_config(),
        api_client=FakeApiClient(),
        generation_version_groups={4: ["diamond-pearl"]},
        target_gen=4,
        generation_dex_map={},
    )

    assert parser.evolutions.get_chain(chain_url)["evolves_to"] == []


def test_evolution_details_use_latest_method_for_target_generation():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={
            4: ["diamond-pearl"],
            5: ["black-white"],
            6: ["x-y", "omega-ruby-alpha-sapphire"],
            8: ["sword-shield"],
            9: ["scarlet-violet", "the-teal-mask"],
        },
        target_gen=9,
        generation_dex_map={},
    )
    details = [
        {
            "trigger": {"name": "level-up"},
            "location": {"name": "sinnoh-route-217"},
            "near_special_rock": True,
            "version_group": {"name": "diamond-pearl"},
        },
        {
            "trigger": {"name": "use-item"},
            "item": {"name": "ice-stone"},
            "version_group": {"name": "sword-shield"},
        },
    ]

    result = parser.evolutions.details_for_target(details)

    assert len(result) == 1
    assert result[0]["item"] == "ice-stone"
    assert result[0]["location"] is None
    assert result[0]["introduced_in_version_group"] == "sword-shield"
    assert result[0]["version_groups"] == ["scarlet-violet", "the-teal-mask"]


def test_evolution_details_can_differ_within_one_generation():
    parser = PokemonParser(
        config=load_config(),
        api_client=None,
        generation_version_groups={
            4: ["diamond-pearl"],
            6: ["x-y", "omega-ruby-alpha-sapphire"],
        },
        target_gen=6,
        generation_dex_map={},
    )
    details = [
        {
            "trigger": {"name": "level-up"},
            "location": {"name": "eterna-forest"},
            "version_group": {"name": "diamond-pearl"},
        },
        {
            "trigger": {"name": "level-up"},
            "location": {"name": "kalos-route-20"},
            "version_group": {"name": "x-y"},
        },
        {
            "trigger": {"name": "level-up"},
            "location": {"name": "petalburg-woods"},
            "version_group": {"name": "omega-ruby-alpha-sapphire"},
        },
    ]

    result = parser.evolutions.details_for_target(details)

    assert [(entry["location"], entry["version_groups"]) for entry in result] == [
        ("kalos-route-20", ["x-y"]),
        ("petalburg-woods", ["omega-ruby-alpha-sapphire"]),
    ]


def test_location_evolution_excludes_games_without_that_region():
    location_url = "https://example.test/location/route-217"

    class FakeApiClient:
        def get(self, url):
            responses = {
                "https://pokeapi.co/api/v2/version-group/diamond-pearl": {
                    "regions": [{"name": "sinnoh"}]
                },
                "https://pokeapi.co/api/v2/version-group/platinum": {
                    "regions": [{"name": "sinnoh"}]
                },
                "https://pokeapi.co/api/v2/version-group/heartgold-soulsilver": {
                    "regions": [{"name": "kanto"}, {"name": "johto"}]
                },
                location_url: {"region": {"name": "sinnoh"}},
            }
            return responses[url]

    parser = PokemonParser(
        config=load_config(),
        api_client=FakeApiClient(),
        generation_version_groups={
            4: ["diamond-pearl", "platinum", "heartgold-soulsilver"]
        },
        target_gen=4,
        generation_dex_map={},
    )
    details = [
        {
            "trigger": {"name": "level-up"},
            "location": {"name": "sinnoh-route-217", "url": location_url},
            "version_group": {"name": "diamond-pearl"},
        }
    ]

    result = parser.evolutions.details_for_target(details)

    assert result[0]["version_groups"] == ["diamond-pearl", "platinum"]


def test_special_relationship_target_has_its_own_chain(offline_api, offline_config):
    from conftest import BASE

    offline_api.responses[f"{BASE}evolution-chain/special/"] = {
        "chain": {
            "species": {"name": "phione"},
            "evolves_to": [
                {
                    "species": {"name": "manaphy"},
                    "evolution_details": [],
                    "evolves_to": [],
                }
            ],
        }
    }
    parser = PokemonParser(offline_config, offline_api, {1: ["red-blue"]}, 1, {})
    assert parser.evolutions.get_chain(
        f"{BASE}evolution-chain/special/", "manaphy"
    ) == {"species_name": "manaphy", "evolves_to": []}
