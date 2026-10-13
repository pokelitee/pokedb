import json
from pathlib import Path

from pokedb.config import load_config
from pokedb.parsers.evolution import EvolutionResolver

GROUPS = {4: ["diamond-pearl", "platinum", "heartgold-soulsilver"]}


def detail(gender):
    return {
        "trigger": {"name": "level-up"},
        "min_level": 20,
        "gender": gender,
        "version_group": {"name": "diamond-pearl"},
    }


def test_repeated_evolution_conditions_keep_unique_version_groups():
    resolver = EvolutionResolver(load_config(), None, GROUPS, 4)
    fixture = Path(__file__).parent / "fixtures/evolutions/burmy.json"
    chain = json.loads(fixture.read_text(encoding="utf-8"))
    raw = chain["chain"]["evolves_to"][0]["evolution_details"]
    assert len(raw) == 3
    conditions = resolver.details_for_target(raw)
    assert len(conditions) == 1
    assert conditions[0]["version_groups"] == GROUPS[4]


def test_distinct_conditions_survive_deduplication():
    resolver = EvolutionResolver(load_config(), None, GROUPS, 4)
    conditions = resolver.details_for_target([detail(1), detail(2), detail(1)])
    assert {condition["gender"] for condition in conditions} == {1, 2}
    assert all(condition["version_groups"] == GROUPS[4] for condition in conditions)
