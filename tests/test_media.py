from pokedb.parsers.media import select_cries, select_sprites


def test_historical_form_media_uses_only_its_own_generation_assets():
    sprites = {
        "front_default": "current.png",
        "versions": {"generation-ii": {"gold": {"front_default": "historical.png"}}},
    }
    assert select_sprites(sprites, 2, True) == {
        "versions": {"gold": {"front_default": "historical.png"}}
    }
    assert select_sprites(sprites, 1, True) == {}


def test_current_form_media_retains_current_assets():
    assert select_sprites({"front_default": "current.png"}, 9, False) == {
        "front_default": "current.png"
    }


def test_cry_selection_respects_recording_eras():
    cries = {"legacy": "old.ogg", "latest": "new.ogg"}
    assert select_cries(cries, 5) == {"legacy": "old.ogg"}
    assert select_cries(cries, 6) == {"latest": "new.ogg"}
