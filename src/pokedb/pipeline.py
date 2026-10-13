"""Generation execution, staging, and publication."""

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from .api_client import ApiClient
from .config import Config
from .locking import generation_lock
from .output import (
    publish_staged_output,
    recover_output,
    write_index_file,
)
from .resources import DATA_SCHEMA_VERSION, PARSER_OUTPUT_KEYS, PARSER_SUMMARY_KEYS
from .runner import gather_initial_data, run_parsers
from .utils import ConfigurationError
from .validation import validate_generation_output

logger = logging.getLogger(__name__)


def process_generation(
    args: argparse.Namespace,
    config: Config,
    api_client: ApiClient,
    target_generation: int,
    latest_generation: int,
) -> None:
    """Publishes a validated generation while excluding competing writers."""
    final_root = config.for_generation(target_generation).generation_output_root
    with generation_lock(final_root):
        recover_output(final_root)
        _process_generation_locked(
            args, config, api_client, target_generation, latest_generation
        )


def _requested_parser_names(args: argparse.Namespace) -> set[str]:
    return set(PARSER_OUTPUT_KEYS if args.all else args.parsers)


def _confirm_replacement(args: argparse.Namespace, target_generation: int) -> bool:
    if args.force:
        return True
    response = input(
        f"Output for Generation {target_generation} already exists. "
        "Replace the requested data? (y/n): "
    )
    return response.lower() == "y"


def _load_existing_index(
    staging_output_dir: Path, preserve_existing: bool
) -> dict[str, Any] | None:
    index_path = staging_output_dir / "index.json"
    if not preserve_existing:
        return None
    try:
        with index_path.open("r", encoding="utf-8") as index_file:
            index = json.load(index_file)
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(
            "Partial regeneration requires a readable existing index; use --all"
        ) from error
    if (
        not isinstance(index, dict)
        or not isinstance(index.get("metadata"), dict)
        or index["metadata"].get("schema_version") != DATA_SCHEMA_VERSION
    ):
        raise ConfigurationError(
            "Partial regeneration requires schema version "
            f"{DATA_SCHEMA_VERSION} output; "
            "regenerate the complete generation with --all"
        )
    return index


def _prepare_staging_tree(
    final_output_dir: Path, staging_output_dir: Path, preserve_existing: bool
) -> None:
    if staging_output_dir.exists():
        shutil.rmtree(staging_output_dir)
    if final_output_dir.exists() and preserve_existing:
        shutil.copytree(final_output_dir, staging_output_dir)
    else:
        staging_output_dir.mkdir(parents=True)


def _clear_requested_outputs(
    staging_config: Config,
    staging_output_dir: Path,
    requested_parsers: set[str],
) -> None:
    for parser_name in requested_parsers:
        for output_key in PARSER_OUTPUT_KEYS[parser_name]:
            parser_output_dir = staging_config.output_path(output_key)
            if parser_output_dir == staging_output_dir:
                raise ConfigurationError(
                    f"{output_key} cannot point to the generation root"
                )
            if parser_output_dir.exists():
                shutil.rmtree(parser_output_dir)
            parser_output_dir.mkdir(parents=True, exist_ok=True)


def _process_generation_locked(
    args: argparse.Namespace,
    config: Config,
    api_client: ApiClient,
    target_generation: int,
    latest_generation: int,
) -> None:
    is_historical = target_generation < latest_generation
    if is_historical:
        logger.info(
            "Performing a historical parse for Generation %s.", target_generation
        )

    version_groups, dex_map, target_versions = gather_initial_data(
        api_client, config, target_generation
    )
    requested_parsers = _requested_parser_names(args)
    logger.info(
        "Parsing %s for Generation %s",
        ", ".join(sorted(requested_parsers)),
        target_generation,
    )

    final_config = config.for_generation(target_generation)
    final_output_dir = final_config.generation_output_root
    if final_output_dir.exists() and not _confirm_replacement(args, target_generation):
        logger.info("Operation cancelled.")
        return

    full_run = requested_parsers == set(PARSER_OUTPUT_KEYS)
    preserve_existing = final_output_dir.exists() and not full_run
    previous_index = None
    if (final_output_dir / "index.json").exists():
        try:
            with (final_output_dir / "index.json").open(encoding="utf-8") as index_file:
                candidate = json.load(index_file)
            if isinstance(candidate, dict) and isinstance(
                candidate.get("metadata"), dict
            ):
                previous_index = candidate
        except (OSError, json.JSONDecodeError):
            if preserve_existing:
                raise ConfigurationError(
                    "Partial regeneration requires a readable existing index; use --all"
                )
            logger.warning(
                "Existing index is unreadable; replacing the complete generation"
            )
    staging_output_dir = final_output_dir.with_name(f".{final_output_dir.name}.staging")
    try:
        _prepare_staging_tree(final_output_dir, staging_output_dir, preserve_existing)
        staging_config = final_config.with_generation_root(staging_output_dir)
        _clear_requested_outputs(staging_config, staging_output_dir, requested_parsers)
        existing_index = _load_existing_index(staging_output_dir, preserve_existing)
        summaries = run_parsers(
            args,
            staging_config,
            api_client,
            version_groups,
            target_generation,
            dex_map,
            is_historical,
            target_versions,
        )
        replaced_keys = {
            summary_key
            for parser_name in requested_parsers
            for summary_key in PARSER_SUMMARY_KEYS[parser_name]
        }
        write_index_file(
            summaries,
            target_generation,
            staging_output_dir,
            version_groups,
            config.api_base_url,
            is_historical,
            existing_index=existing_index,
            replaced_keys=replaced_keys,
            previous_index=previous_index,
            target_versions=target_versions,
        )
        validate_generation_output(staging_output_dir)
        publish_staged_output(staging_output_dir, final_output_dir)
    finally:
        if staging_output_dir.exists():
            shutil.rmtree(staging_output_dir)
