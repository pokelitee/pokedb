"""Command-line entry point for PokéDB data collection."""

import argparse
import logging
import sys
from pathlib import Path

from .api_client import ApiClient
from .config import load_config
from .pipeline import process_generation
from .resources import PARSER_OUTPUT_KEYS
from .utils import GenerationNotFoundError, PokeDBError, get_latest_generation

logger = logging.getLogger(__name__)


def _parse_generation(value: str) -> int | str:
    """Parses a positive generation number or the special value 'all'."""
    if value.lower() == "all":
        return "all"
    try:
        generation = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "generation must be a positive integer or 'all'"
        ) from error
    if generation < 1:
        raise argparse.ArgumentTypeError("generation must be at least 1")
    return generation


def parse_arguments() -> argparse.Namespace:
    """Parses and validates command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PokéDB - Parse Pokémon data with historical accuracy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m pokedb --all
  python -m pokedb ability move item
  python -m pokedb --all --gen 3
  python -m pokedb --all --gen all
  python -m pokedb --all --no-cache
  python -m pokedb --all --force
        """,
    )
    parser.add_argument(
        "parsers",
        nargs="*",
        choices=tuple(PARSER_OUTPUT_KEYS),
        help="Parser(s) to run: ability, item, move, or pokemon.",
    )
    parser.add_argument("--all", action="store_true", help="Run every parser.")
    parser.add_argument(
        "--gen",
        type=_parse_generation,
        help="Generation number to parse, or 'all'.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching for this run.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing output without confirmation.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Custom JSON configuration path (or set POKEDB_CONFIG).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()
    if not args.parsers and not args.all:
        parser.error("specify at least one parser or use --all")
    return args


def main() -> None:
    """Runs the requested parsers and publishes complete generation output."""
    try:
        args = parse_arguments()
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(levelname)s: %(message)s",
        )
        config = load_config(args.config)
        if args.no_cache:
            config = config.without_cache()

        api_client = ApiClient(config)
        latest_generation = get_latest_generation(api_client, config)
        if args.gen == "all":
            generations = range(1, latest_generation + 1)
        else:
            target_generation = (
                args.gen if isinstance(args.gen, int) else latest_generation
            )
            if target_generation > latest_generation:
                raise GenerationNotFoundError(
                    f"Generation {target_generation} is newer than the latest "
                    f"available generation ({latest_generation})."
                )
            generations = (target_generation,)

        for target_generation in generations:
            process_generation(
                args,
                config,
                api_client,
                target_generation,
                latest_generation,
            )
    except PokeDBError as error:
        logger.error("Fatal error: %s", error)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        sys.exit(130)
    except Exception as error:
        logger.exception("Unexpected error: %s", error)
        sys.exit(1)


if __name__ == "__main__":
    main()
