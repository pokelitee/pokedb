import copy
from dataclasses import replace

import pytest

from pokedb.config import load_config

BASE = "https://example.test/"


def ref(endpoint, name):
    return {"name": name, "url": f"{BASE}{endpoint}/{name}/"}


class FixtureApi:
    def __init__(self, responses):
        self.responses = responses
        self.failures = set()

    def get(self, url):
        if url in self.failures:
            raise TimeoutError(f"Simulated failure: {url}")
        return copy.deepcopy(self.responses[url])


@pytest.fixture
def offline_api():
    groups = {1: ["red-blue", "yellow"], 2: ["gold-silver"], 3: ["ruby-sapphire"]}
    responses = {
        f"{BASE}generation/": {"results": [ref("generation", str(n)) for n in groups]},
        f"{BASE}pokedex?limit=100": {"results": [ref("pokedex", "kanto")]},
        ref("pokedex", "kanto")["url"]: {
            "name": "kanto",
            "is_main_series": True,
            "version_groups": [ref("version-group", "red-blue")],
        },
    }
    for n, names in groups.items():
        generation = {
            "version_groups": [ref("version-group", name) for name in names],
            "pokemon_species": [
                ref("pokemon-species", name) for name in ("pikachu", "raichu")
            ]
            if n == 1
            else [],
            "moves": [ref("move", "thunderbolt")] if n == 1 else [],
            "abilities": [ref("ability", "static")] if n == 3 else [],
        }
        responses[f"{BASE}generation/{n}/"] = generation
        responses[f"{BASE}generation/{n}"] = generation
        for name in names:
            data = {
                "generation": ref("generation", str(n)),
                "versions": [ref("version", name)],
                "regions": [{"name": "kanto"}],
            }
            responses[f"{BASE}version-group/{name}"] = data
            responses[f"{BASE}version-group/{name}/"] = data
    chain = {
        "species": ref("pokemon-species", "pichu"),
        "evolves_to": [
            {
                "species": ref("pokemon-species", "pikachu"),
                "evolution_details": [{"trigger": {"name": "level-up"}}],
                "evolves_to": [
                    {
                        "species": ref("pokemon-species", "raichu"),
                        "evolution_details": [
                            {
                                "trigger": {"name": "use-item"},
                                "item": {"name": "thunder-stone"},
                            }
                        ],
                        "evolves_to": [],
                    }
                ],
            }
        ],
    }
    responses[f"{BASE}evolution-chain/1/"] = {"chain": chain}
    responses[ref("pokemon-species", "pichu")["url"]] = {
        "generation": ref("generation", "2")
    }
    for number, name in enumerate(("pikachu", "raichu"), 25):
        species = {
            "id": number,
            "name": name,
            "generation": ref("generation", "1"),
            "varieties": [{"is_default": True, "pokemon": ref("pokemon", name)}],
            "evolution_chain": {"url": f"{BASE}evolution-chain/1/"},
            "evolves_from_species": {
                "name": "pichu" if name == "pikachu" else "pikachu"
            },
        }
        responses[ref("pokemon-species", name)["url"]] = species
        pokemon = {
            "id": number,
            "name": name,
            "is_default": True,
            "forms": [ref("pokemon-form", name)],
            "types": [{"slot": 1, "type": {"name": "electric"}}],
            "abilities": [
                {"ability": {"name": "static"}, "is_hidden": False, "slot": 1}
            ],
            "stats": [
                {"stat": {"name": stat}, "base_stat": 50, "effort": 0}
                for stat in (
                    "hp",
                    "attack",
                    "defense",
                    "special-attack",
                    "special-defense",
                    "speed",
                )
            ],
            "past_stats": [
                {
                    "generation": ref("generation", "1"),
                    "stats": [
                        {"stat": {"name": "special"}, "base_stat": 50, "effort": 0}
                    ],
                }
            ],
            "height": 4,
            "weight": 60,
            "base_experience": 112,
            "cries": {
                "legacy": "https://example.test/legacy.ogg",
                "latest": "https://example.test/latest.ogg",
            },
            "sprites": {
                "front_default": "https://example.test/current.png",
                "versions": {
                    "generation-i": {
                        "red-blue": {
                            "front_default": "https://example.test/historical.png"
                        }
                    }
                },
            },
            "held_items": [],
            "moves": [
                {
                    "move": {"name": "thunderbolt"},
                    "version_group_details": [
                        {
                            "version_group": {"name": "red-blue"},
                            "move_learn_method": {"name": "machine"},
                            "level_learned_at": 0,
                        }
                    ],
                }
            ],
        }
        responses[ref("pokemon", name)["url"]] = pokemon
        responses[ref("pokemon-form", name)["url"]] = {
            "name": name,
            "is_default": True,
            "version_group": ref("version-group", "red-blue"),
        }
    responses[ref("pokemon", "pikachu")["url"]]["forms"].append(
        ref("pokemon-form", "pikachu-costume")
    )
    responses[ref("pokemon-form", "pikachu-costume")["url"]] = {
        "name": "pikachu-costume",
        "is_default": False,
        "version_group": ref("version-group", "red-blue"),
        "sprites": {"front_default": "https://example.test/current-costume.png"},
    }
    responses[ref("move", "thunderbolt")["url"]] = {
        "id": 85,
        "name": "thunderbolt",
        "accuracy": 100,
        "power": 90,
        "pp": 15,
        "priority": 0,
        "damage_class": {"name": "special"},
        "type": {"name": "electric"},
        "target": {"name": "selected-pokemon"},
        "generation": {"name": "generation-i"},
        "effect_entries": [],
        "flavor_text_entries": [],
        "stat_changes": [],
        "machines": [
            {
                "version_group": {"name": group},
                "machine": {"url": f"{BASE}machine/{group}/"},
            }
            for group in groups[1]
        ],
    }
    for group, item in [("red-blue", "tm24"), ("yellow", "tm25")]:
        responses[f"{BASE}machine/{group}/"] = {"item": {"name": item}}
    items = ["tm24", "tm25", "thunder-stone"]
    responses[f"{BASE}item?limit=3000"] = {
        "results": [ref("item", name) for name in items]
    }
    for number, name in enumerate(items, 1):
        responses[ref("item", name)["url"]] = {
            "id": number,
            "name": name,
            "game_indices": [],
            "cost": 100,
            "fling_power": None,
            "fling_effect": None,
        }
    pichu_species = copy.deepcopy(responses[ref("pokemon-species", "pikachu")["url"]])
    pichu_species.update(
        id=172,
        name="pichu",
        generation=ref("generation", "2"),
        evolves_from_species=None,
        varieties=[{"is_default": True, "pokemon": ref("pokemon", "pichu")}],
    )
    responses[ref("pokemon-species", "pichu")["url"]] = pichu_species
    pichu_pokemon = copy.deepcopy(responses[ref("pokemon", "pikachu")["url"]])
    pichu_pokemon.update(id=172, name="pichu", forms=[ref("pokemon-form", "pichu")])
    responses[ref("pokemon", "pichu")["url"]] = pichu_pokemon
    responses[ref("pokemon-form", "pichu")["url"]] = {
        "name": "pichu",
        "is_default": True,
        "version_group": ref("version-group", "gold-silver"),
    }
    responses[f"{BASE}generation/2/"]["pokemon_species"] = [
        ref("pokemon-species", "pichu")
    ]
    responses[ref("ability", "static")["url"]] = {
        "id": 9,
        "name": "static",
        "is_main_series": True,
        "generation": {"name": "generation-iii"},
        "effect_entries": [],
        "effect_changes": [],
        "flavor_text_entries": [],
    }
    return FixtureApi(responses)


@pytest.fixture
def offline_config(tmp_path):
    return replace(
        load_config(),
        api_base_url=BASE,
        output_root=tmp_path / "output",
        parser_cache_dir=None,
    )
