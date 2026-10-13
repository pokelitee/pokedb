# Development

See the [README](../README.md) for quick start and documentation links. General contribution policy lives in the [organization guide](https://github.com/pokelitee/.github/blob/main/CONTRIBUTING.md).

## Setup and checks

Run the commands below from the repository root.

Use Python 3.12 or newer and a virtual environment:

```bash
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install -r requirements/dev.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m ruff check .
python -m ruff format --check .
python -m pytest
python scripts/check_package.py
```

CI runs these checks on Ubuntu and Windows with Python 3.12 and 3.13. Tests use offline API fixtures. The wheel smoke check builds source and wheel distributions, installs the wheel in a clean environment, and checks the CLI and packaged configuration outside the checkout.

Package consumers use the supported dependency ranges in `pyproject.toml`. CI and scheduled generation use exact dependency versions in `requirements/`. Update the pinned files together, keeping transitive dependencies consistent, then run the complete checks. Dependabot opens weekly updates for Python dependencies and pinned GitHub Actions.

## Architecture

```text
pokedb/
|-- src/
|   `-- pokedb/
|       |-- __main__.py          # CLI arguments and exit handling
|       |-- pipeline.py          # Locked generation workflow
|       |-- resources.py         # Shared schema and resource layout
|       |-- locking.py           # Cross-platform generation locks
|       |-- api_client.py        # API client and caching
|       |-- config.py            # Typed configuration and validation
|       |-- default_config.json  # Packaged default values
|       |-- output.py            # Transactional output publishing
|       |-- runner.py            # Parser orchestration and metadata
|       |-- validation.py        # Runtime output schema and integrity checks
|       |-- parsers/             # Ability, item, move, and Pokémon parsers
|       `-- utils/               # Focused shared helpers
|-- .github/                     # Workflows and data-branch documentation
|-- tests/
`-- pyproject.toml               # Package metadata and dependencies
```

## Making changes

Keep resource paths, parser dependencies, and the schema version centralized in `src/pokedb/resources.py`. Extend existing parsers and utilities rather than adding parallel generation paths. Tests and captured upstream fixtures live in `tests/`; fixture READMEs record their provenance.

Changes to fields or generation semantics must update the [data contract](data-contract.md), its migration section, validation, and representative fixtures. Before publishing a contract change, verify complete generation against current PokéAPI as described in [Operations](operations.md).

The required PR check is `CI gate`. The reusable matrix in `.github/workflows/checks.yml` supplies its result; a failed or cancelled matrix must not allow merging.
