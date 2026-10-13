import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokedb.config import load_config
from pokedb.parsers.item import ItemParser
from pokedb.utils.exceptions import DataValidationError
from pokedb.validation import _validate_common, _validate_item

FIXTURES = Path(__file__).parent / "fixtures/items"
GROUPS = {1: ["red-blue", "yellow"], 2: ["gold-silver"]}


def test_upstream_item_identifier_preserves_repeated_hyphens(tmp_path):
    item = parse_fixture(tmp_path, "xtransceiver--red")
    _validate_common(item, "xtransceiver--red", "https://pokeapi.co/api/v2/", tmp_path)
    assert item["name"] == "xtransceiver--red"


@pytest.mark.parametrize(
    "name", ["../item", "item/name", "item_name", "-item", "item-"]
)
def test_item_identifiers_reject_unsafe_or_rewritten_names(tmp_path, name):
    with pytest.raises(DataValidationError, match="filename"):
        _validate_common({"name": name}, name, "https://pokeapi.co/api/v2/", tmp_path)


def parse_fixture(tmp_path, name, generation=1):
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    class FixtureApi:
        def get(self, url):
            return payload

    config = replace(load_config(), output_root=tmp_path).for_generation(generation)
    parser = ItemParser(config, FixtureApi(), GROUPS, generation, is_historical=True)
    parser.referenced_item_names = {name}
    result = parser.process(
        {"name": name, "url": f"https://pokeapi.co/api/v2/item/{name}/"}
    )
    assert isinstance(result, dict), result
    path = config.output_path("output_dir_item") / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_api_prices_are_preserved_per_game(tmp_path):
    item = parse_fixture(tmp_path, "tm01")
    assert "cost" not in item
    assert item["prices"] == {
        group: {"poke-dollar": {"purchase_price": 3000, "sell_price": 1500}}
        for group in GROUPS[1]
    }
    assert "prices" not in item["unverified_historical_fields"]
    _validate_item(item, set(GROUPS[1]), 1, True, tmp_path / "tm01.json")


def test_unpurchasable_item_price_is_distinct_from_missing_price_data(tmp_path):
    item = parse_fixture(tmp_path, "tm01", generation=2)
    assert item["prices"] == {
        "gold-silver": {"poke-dollar": {"purchase_price": None, "sell_price": 1500}}
    }
    item = parse_fixture(tmp_path, "potion")
    assert item["prices"] == {"red-blue": None, "yellow": None}
    _validate_item(item, set(GROUPS[1]), 1, True, tmp_path / "potion.json")


def test_prices_keep_multiple_currencies_and_explicit_zero():
    parser = ItemParser(load_config(), None, GROUPS, 1)
    prices = [
        {
            "version_group": {"name": "red-blue"},
            "currency": {"name": currency},
            "purchase_price": amount,
            "sell_price": None,
        }
        for currency, amount in [("poke-dollar", 0), ("battle-point", 16)]
    ]
    assert parser._get_prices_for_generation(prices) == {
        "red-blue": {
            "poke-dollar": {"purchase_price": 0, "sell_price": None},
            "battle-point": {"purchase_price": 16, "sell_price": None},
        },
        "yellow": None,
    }


def test_conflicting_prices_fail_instead_of_overwriting():
    parser = ItemParser(load_config(), None, GROUPS, 1)
    base = {
        "version_group": {"name": "red-blue"},
        "currency": {"name": "poke-dollar"},
        "purchase_price": 100,
        "sell_price": 50,
    }
    with pytest.raises(ValueError, match="Conflicting prices"):
        parser._get_prices_for_generation([base, {**base, "purchase_price": 200}])


@pytest.mark.parametrize(
    "prices",
    [
        {"red-blue": None},
        {"red-blue": {}, "yellow": None},
        {
            "red-blue": {"poke-dollar": {"purchase_price": -1, "sell_price": 0}},
            "yellow": None,
        },
        {
            "red-blue": {"poke-dollar": {"purchase_price": True, "sell_price": 0}},
            "yellow": None,
        },
        {"red-blue": {"poke-dollar": {"purchase_price": 100}}, "yellow": None},
    ],
)
def test_invalid_price_records_are_rejected(tmp_path, prices):
    item = parse_fixture(tmp_path, "tm01")
    item["prices"] = prices
    with pytest.raises(DataValidationError):
        _validate_item(item, set(GROUPS[1]), 1, True, tmp_path / "tm01.json")
