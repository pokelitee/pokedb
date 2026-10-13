import json

from pokedb.output import (
    publish_staged_output,
    write_index_file,
)
from pokedb.resources import DATA_SCHEMA_VERSION, RESOURCE_INDEX_KEYS
from pokedb.utils.file_ops import write_json_file


def test_partial_index_update_preserves_unrequested_resources(tmp_path):
    existing_index = {
        "metadata": {"generation": 9},
        "ability": [{"id": 1, "name": "stench"}],
        "move": [{"id": 1, "name": "pound"}],
    }

    write_index_file(
        {"move": [{"id": 2, "name": "karate-chop"}]},
        target_gen=9,
        output_dir=tmp_path,
        generation_version_groups={9: ["scarlet-violet"]},
        api_base_url="https://pokeapi.co/api/v2/",
        is_historical=False,
        existing_index=existing_index,
        replaced_keys={"move"},
    )

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["ability"] == existing_index["ability"]
    assert index["move"] == [{"id": 2, "name": "karate-chop"}]
    assert index["metadata"]["counts"] == {
        key: (1 if key in {"ability", "move"} else 0) for key in RESOURCE_INDEX_KEYS
    }
    assert index["metadata"]["schema_version"] == DATA_SCHEMA_VERSION
    assert index["metadata"]["source"] == "pokeapi"
    assert set(index) == {"metadata", *RESOURCE_INDEX_KEYS}


def test_publish_staged_output_replaces_complete_tree(tmp_path):
    final_output = tmp_path / "gen9"
    final_output.mkdir()
    (final_output / "old.json").write_text("{}", encoding="utf-8")
    staging_output = tmp_path / ".gen9.staging"
    staging_output.mkdir()
    (staging_output / "new.json").write_text("{}", encoding="utf-8")

    publish_staged_output(staging_output, final_output)

    assert not (final_output / "old.json").exists()
    assert (final_output / "new.json").exists()


def test_resource_writer_preserves_canonical_identifier_keys(tmp_path):
    write_json_file(
        tmp_path,
        "example",
        {"effect": {"scarlet-violet": "text"}, "stats": {"special-attack": 100}},
    )

    data = json.loads((tmp_path / "example.json").read_text(encoding="utf-8"))
    assert set(data["effect"]) == {"scarlet-violet"}
    assert set(data["stats"]) == {"special-attack"}


def test_failed_publish_restores_previous_tree(tmp_path, monkeypatch):
    from pathlib import Path

    import pytest

    final = tmp_path / "gen9"
    final.mkdir()
    (final / "old.json").write_text("old")
    staging = tmp_path / ".gen9.staging"
    staging.mkdir()
    (staging / "new.json").write_text("new")
    original = Path.replace

    def fail_staging(self, target):
        if self == staging:
            raise OSError("Simulated publication failure")
        return original(self, target)

    monkeypatch.setattr(Path, "replace", fail_staging)
    with pytest.raises(OSError, match="publication failure"):
        publish_staged_output(staging, final)
    assert (final / "old.json").read_text() == "old"
    assert not (final / "new.json").exists()


def test_interrupted_publish_recovers_before_partial_run(tmp_path):
    from pokedb.output import recover_output

    backup = tmp_path / ".gen9.backup"
    backup.mkdir()
    (backup / "old.json").write_text("old")
    final = tmp_path / "gen9"
    recover_output(final)
    assert (final / "old.json").read_text() == "old"
    assert not backup.exists()


def test_generation_lock_excludes_another_process_and_releases(tmp_path):
    import subprocess
    import sys

    from pokedb.locking import generation_lock

    final = tmp_path / "gen9"
    code = "from pathlib import Path; from pokedb.locking import generation_lock; import sys; lock = generation_lock(Path(sys.argv[1])); lock.__enter__(); lock.__exit__(None, None, None)"
    with generation_lock(final):
        contender = subprocess.run(
            [sys.executable, "-c", code, str(final)], capture_output=True, text=True
        )
        assert contender.returncode != 0
        assert "Cannot lock" in contender.stderr
    contender = subprocess.run(
        [sys.executable, "-c", code, str(final)], capture_output=True, text=True
    )
    assert contender.returncode == 0, contender.stderr
