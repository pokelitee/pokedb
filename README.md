# PokéDB - Pokémon Data Collector

[![Update Pokémon Data](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yaml/badge.svg)](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yaml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python tool for creating a comprehensive, generation-aware Pokémon database from the structured [PokéAPI](https://pokeapi.co/).

Parsed generation data is automatically saved to the `data` branch weekly.

`main` holds the source, `data` holds generated snapshots, and GitHub Pages serves the JSON at [pokelitee.github.io/pokedb](https://pokelitee.github.io/pokedb/). For example, [gen9/index.json](https://pokelitee.github.io/pokedb/gen9/index.json) lists the latest published Generation 9 catalog. Existing raw GitHub endpoints continue to work. Check the schema version in the published index: deploying Pages does not upgrade previously generated data.

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

`src/pokedb/` separates the CLI, configuration, API access, parser orchestration, and resource validation. Generation uses locks and staging so failed runs do not replace the previous output. See [Contributing](CONTRIBUTING.md#architecture) for the module layout.

## Configuration

PokéDB includes validated defaults and does not require a configuration file. Settings are selected in this order:

1. `--config path/to/config.json`
2. The `POKEDB_CONFIG` environment variable
3. Packaged defaults in `src/pokedb/default_config.json`

Custom files are partial overrides, so they only need values that differ from the defaults:

```json
{
  "max_workers": 4,
  "output_root": "./generated"
}
```

Relative paths in a custom file are resolved relative to that file. Without a custom file, default paths are resolved relative to the current working directory.

| Setting | Default | Description |
| --- | --- | --- |
| `api_base_url` | `https://pokeapi.co/api/v2/` | PokéAPI base URL; must be HTTP(S) and end in `/`. |
| `timeout` | `15` | Request timeout in seconds. |
| `max_retries` | `3` | Maximum HTTP retry count. |
| `max_workers` | `10` | Parser worker-thread count. |
| `parser_cache_dir` | `./.cache/parser` | API cache directory, or `null` to disable it. |
| `cache_expires` | `3600` | Cache lifetime in seconds, or `null` to keep entries indefinitely. |
| `output_root` | `./.output` | Root containing generated `gen1`, `gen2`, and other generation directories. |

`--no-cache` disables the API cache for the current run without changing the configuration file.

Python callers should import `Config` and `load_config` from `pokedb` or `pokedb.config`.

## Documentation

- [Data contract and schema v5 migration](docs/data-contract.md): generation semantics, field guarantees, validation, and compatibility.
- [Contributing](CONTRIBUTING.md): local checks, dependency updates, CI, and dataset publication.

Keep contract changes in this repository so documentation and implementation can be reviewed together.

## Contributing

Follow the [organization contribution guide](https://github.com/pokelitee/.github/blob/main/CONTRIBUTING.md) and the [project instructions](CONTRIBUTING.md). Use a short-lived branch and a pull request into `main`.

## License

This project is licensed under the [MIT License](LICENSE).
