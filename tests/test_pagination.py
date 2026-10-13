import pytest

from pokedb.utils.api_helpers import get_all_results
from pokedb.utils.exceptions import ParserExecutionError


class Pages:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages[url]


def test_listing_follows_every_page():
    api = Pages(
        {
            "first": {"results": [{"name": "a"}], "next": "second"},
            "second": {"results": [{"name": "b"}], "next": None},
        }
    )
    assert get_all_results(api, "first") == [{"name": "a"}, {"name": "b"}]


@pytest.mark.parametrize(
    "page", [{}, {"results": None}, {"results": [], "next": "first"}]
)
def test_malformed_or_cyclic_listing_fails(page):
    with pytest.raises(ParserExecutionError):
        get_all_results(Pages({"first": page}), "first")
