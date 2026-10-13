"""Generation index creation and transactional output publishing."""

import hashlib
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .resources import DATA_SCHEMA_VERSION, RESOURCE_INDEX_KEYS, RESOURCE_PATHS
from .utils import write_json_atomic

logger = logging.getLogger(__name__)


def generation_content_digest(generation_root: Path) -> str:
    """Hashes canonical resource contents and paths independently of timestamps."""
    digest = hashlib.sha256()
    for resource in RESOURCE_INDEX_KEYS:
        for path in sorted((generation_root / RESOURCE_PATHS[resource]).glob("*.json")):
            digest.update(path.relative_to(generation_root).as_posix().encode())
            digest.update(b"\0")
            digest.update(
                json.dumps(
                    json.loads(path.read_text(encoding="utf-8")), sort_keys=True
                ).encode()
            )
            digest.update(b"\0")
    return digest.hexdigest()


def generator_provenance() -> dict[str, Any]:
    """Records the installed generator and runtime dependencies for each catalog."""

    def installed_version(package: str) -> str:
        try:
            return version(package)
        except PackageNotFoundError:
            return "unknown"

    commit = os.environ.get("POKEDB_GENERATOR_COMMIT")
    if commit is not None and (
        len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)
    ):
        raise ValueError(
            "POKEDB_GENERATOR_COMMIT must be a full lowercase Git commit SHA"
        )
    return {
        "version": installed_version("pokedb"),
        "commit": commit,
        "dependencies": {
            name: installed_version(name) for name in ("requests", "tqdm")
        },
    }


def write_index_file(
    all_summaries: dict[str, list[dict[str, Any]]],
    target_gen: int,
    output_dir: Path,
    generation_version_groups: dict[int, list[str]],
    api_base_url: str,
    is_historical: bool,
    existing_index: dict[str, Any] | None = None,
    replaced_keys: set[str] | None = None,
    previous_index: dict[str, Any] | None = None,
    target_versions: set[str] | None = None,
) -> None:
    """Writes an index, preserving unrequested resources during partial runs."""
    resource_index = dict(existing_index or {})
    resource_index.pop("metadata", None)
    for key in replaced_keys or set():
        resource_index.pop(key, None)
    resource_index.update(all_summaries)
    for key in RESOURCE_INDEX_KEYS:
        resource_index.setdefault(key, [])

    generated_resources = set(
        (existing_index or {}).get("metadata", {}).get("generated_resources", [])
    )
    generated_resources.update(
        replaced_keys if replaced_keys is not None else all_summaries
    )
    provenance = dict(
        (existing_index or {}).get("metadata", {}).get("resource_provenance", {})
    )
    generator = generator_provenance()
    for resource in replaced_keys if replaced_keys is not None else all_summaries:
        provenance[resource] = generator

    metadata = {
        "schema_version": DATA_SCHEMA_VERSION,
        "generated_resources": sorted(generated_resources),
        "resource_provenance": provenance,
        "content_sha256": generation_content_digest(output_dir),
        "source": "pokeapi",
        "api_base_url": api_base_url,
        "is_historical": is_historical,
        "generation": target_gen,
        "version_groups": generation_version_groups.get(target_gen, []),
        "versions": sorted(target_versions or set()),
        "created_at": datetime.now(UTC).isoformat(),
        "counts": {
            key: len(value)
            for key, value in resource_index.items()
            if isinstance(value, list)
        },
    }
    if previous_index is not None:
        previous_metadata = previous_index.get("metadata", {})
        if {key: value for key, value in metadata.items() if key != "created_at"} == {
            key: value
            for key, value in previous_metadata.items()
            if key != "created_at"
        } and resource_index == {
            key: value for key, value in previous_index.items() if key != "metadata"
        }:
            metadata["created_at"] = previous_metadata["created_at"]
    write_json_atomic(
        output_dir / "index.json", {"metadata": metadata, **resource_index}
    )
    logger.info("Top-level index.json created at '%s'", output_dir / "index.json")


def publish_staged_output(staging_root: Path, final_root: Path) -> None:
    """Replaces a generation tree while restoring the old tree on failure."""
    recover_output(final_root)
    backup_root = final_root.with_name(f".{final_root.name}.backup")

    if final_root.exists():
        final_root.replace(backup_root)

    try:
        staging_root.replace(final_root)
    except Exception:
        if backup_root.exists() and not final_root.exists():
            backup_root.replace(final_root)
        raise
    else:
        if backup_root.exists():
            shutil.rmtree(backup_root)


def recover_output(final_root: Path) -> None:
    """Restores an interrupted publication before a writer inspects existing data."""
    backup_root = final_root.with_name(f".{final_root.name}.backup")
    if backup_root.exists():
        if final_root.exists():
            shutil.rmtree(backup_root)
        else:
            backup_root.replace(final_root)
