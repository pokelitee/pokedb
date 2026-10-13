from pathlib import Path

from pokedb import runner
from pokedb.config import Config


class FakeApiClient:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url):
        return self.responses[url]


def test_gather_initial_data_collects_all_groups_and_target_versions(monkeypatch):
    base_url = "https://example.test/api/"
    responses = {
        f"{base_url}generation/": {
            "results": [
                {"url": f"{base_url}generation/1/"},
                {"url": f"{base_url}generation/2/"},
            ]
        },
        f"{base_url}generation/1/": {"version_groups": [{"name": "red-blue"}]},
        f"{base_url}generation/2/": {"version_groups": [{"name": "gold-silver"}]},
        f"{base_url}version-group/red-blue": {
            "versions": [{"name": "red"}, {"name": "blue"}]
        },
    }
    monkeypatch.setattr(
        runner,
        "get_generation_dex_map",
        lambda client, config: {1: "kanto"},
    )

    config = Config(
        api_base_url=base_url,
        timeout=1,
        max_retries=0,
        max_workers=1,
        parser_cache_dir=None,
        cache_expires=None,
        output_root=Path(".output"),
    )
    version_groups, dex_map, versions = runner.gather_initial_data(
        FakeApiClient(responses), config, target_gen=1
    )

    assert version_groups == {1: ["red-blue"], 2: ["gold-silver"]}
    assert dex_map == {1: "kanto"}
    assert versions == {"red", "blue"}
