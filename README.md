# PokéDB - Pokémon Data Collector

[![Update Pokémon Data](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yml/badge.svg)](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python tool for creating a comprehensive, generation-aware Pokémon database from the structured [PokéAPI](https://pokeapi.co/).

Parsed generation data is automatically saved to the `data` branch weekly.

`main` holds the source, `data` holds generated snapshots, and GitHub Pages provides a catalog explorer, fetch examples, and JSON endpoints at [pokelitee.github.io/pokedb](https://pokelitee.github.io/pokedb/). For example, [gen9/index.json](https://pokelitee.github.io/pokedb/gen9/index.json) lists the latest published Generation 9 catalog. Existing raw GitHub endpoints continue to work. Check the schema version in the published index: deploying Pages does not upgrade previously generated data.

## Features

- Uses PokéAPI as its sole runtime data source.
- Reconstructs generation-specific types, abilities, stats, EV yields, moves, and evolutions.
- Processes resources concurrently.
- Builds output in staging and publishes only complete successful runs.
- Generates data for the latest, a specific, or every generation.
- Writes structured JSON with a generation-level index.

## Getting started

Use Python 3.12+: activations are `.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in bash.

```bash
git clone https://github.com/pokelitee/pokedb.git
cd pokedb
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install -e .

# Parse every resource for the latest generation
python -m pokedb --all

# Parse selected resources
python -m pokedb ability move item pokemon

# Parse a historical generation
python -m pokedb --all --gen 3

# Parse without persistent caches
python -m pokedb --all --no-cache
```

## Architecture

`src/pokedb/` separates the CLI, configuration, API access, parser orchestration, and resource validation. Generation uses locks and staging so failed runs do not replace the previous output. See [Development](docs/development.md#architecture) for the module layout.

## Documentation

- [Data contract and schema v5 migration](docs/data-contract.md): generation semantics, field guarantees, validation, and compatibility.
- [Development](docs/development.md): setup, checks, architecture, and dependency updates.
- [Operations](docs/operations.md): CLI, configuration, generation, publication, and recovery.

Keep contract changes in this repository so documentation and implementation can be reviewed together.

## Contributing

Follow the [organization contribution guide](https://github.com/pokelitee/.github/blob/main/CONTRIBUTING.md) and the [development guide](docs/development.md). Use a short-lived branch and a pull request into `main`.

## License

This project is licensed under the [MIT License](LICENSE).
