# PokéDB - Pokémon Data Collector

[![Update Pokémon Data](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yaml/badge.svg)](https://github.com/pokelitee/pokedb/actions/workflows/update-data.yaml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python tool for creating a comprehensive, generation-aware Pokémon database from the structured [PokéAPI](https://pokeapi.co/).

Parsed generation data is automatically saved to the `data` branch weekly.

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

## Core Features

- Uses PokéAPI as its sole runtime data source.
- Reconstructs generation-specific types, abilities, stats, EV yields, moves, and evolutions.
- Processes resources concurrently.
- Builds output in staging and publishes only complete successful runs.
- Generates data for the latest, a specific, or every generation.
- Writes structured JSON with a generation-level index.

## Quick Start

```bash
git clone https://github.com/pokelitee/pokedb.git
cd pokedb
pip install -e .

# Parse every resource for the latest generation
python -m pokedb --all

# Parse selected resources
python -m pokedb ability move item pokemon

# Parse a historical generation
python -m pokedb --all --gen 3

# Parse without persistent caches
python -m pokedb --all --no-cache
```

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

See the [project wiki](https://github.com/pokelitee/pokedb/wiki) for API usage,
the data model, generation semantics, and configuration details. The wiki is
maintained in its dedicated Git repository.

## Data contract and validation

Each generation is written below `output_root/genN`. A generation is a cumulative
catalog: it includes resources introduced by or before that generation, but does not
imply that every resource is available in every game. Version-specific maps are used
where PokéAPI supplies that detail.

The generation `index.json` contains schema version `5`, PokéAPI source metadata,
version groups and game versions, resource summaries, counts, generated-catalog
identifiers, a resource-content digest, and per-catalog generator provenance. All resource keys are always present,
including empty lists for mechanics or categories with no entries. Individual files
live in the corresponding `ability`, `item`, `move`, or `pokemon` subdirectory.

Generated data is validated before the staging tree is published. Validation checks:

- index counts, unique names, and exact agreement between summaries and files;
- required scalar and collection types for each resource;
- version-group maps for generation-specific ability and move fields;
- Pokémon stat names and ranges, type counts, ability and EV entries, learnsets,
  and references to generated abilities, moves, items, and evolution species when
  the corresponding catalogs are present.

Identifiers originating in PokéAPI retain their canonical kebab-case spelling, such
as `scarlet-violet` and `special-attack`. Structural field names remain snake_case.
Ability `effect` and `short_effect` are always objects keyed by every version group
in the generated generation, with string or `null` values. This keeps their types
stable even when an ability has no historical changes.

Evolution conditions are reconstructed for the target generation instead of copying
every historical condition from PokéAPI. Each condition includes
`introduced_in_version_group` and the target `version_groups` for which it was
selected. This means, for example, Gen 9 Glaceon uses the Ice Stone condition rather
than retaining the obsolete Ice Rock locations from Generations 4–7.
Each evolution edge has an `availability` value. `available` edges contain one or
more applicable conditions; `unavailable` means both species existed but PokéAPI has
no applicable method for the target generation. Future baby species are removed and
their historical descendant is promoted to the chain root. Empty special relationships
such as Phione and Manaphy are not represented as evolutions.

For historical Pokémon data, PokéAPI `past_types`, `past_abilities`, and `past_stats`
reconstruct the supported values. Generation 1 uses its original single `special`
stat. Abilities are empty before Generation 3, while `ev_yield` is `null` because
Generations 1–2 used Stat Experience rather than modern EV yields.

The schema distinguishes an empty collection (the mechanic applies but has no
entries) from `null` (the mechanic is unavailable or inapplicable for that
generation).

PokéAPI does not track per-generation history for every scalar field. For
historical output, current-only Pokémon values such as base experience,
friendship, capture rate, breeding fields, growth rate, and form switching are
backfilled with their current PokéAPI value rather than discarded, as are
current-only move fields (`priority`, `target`, `metadata`, `stat_changes`) and
item fields (`cost`, `fling_power`, `fling_effect`, `attributes`, `category`,
`effect`, `short_effect`, `sprite`). Every move, item, and Pokémon record
carries an `unverified_historical_fields` array (empty for the latest
generation) naming exactly which of its fields are this best-effort backfill
rather than a value verified for that generation. Pre-Generation 4 move damage
class is derived from the reconstructed move type instead of being backfilled.
Historical sprites contain only the target generation's version assets, and
cries resolve to the `legacy` (Generations 1-5) or `latest` (Generation 6+)
recording PokéAPI provides for that generation, since PokéAPI versions cries
directly rather than only exposing a current value.

PokéAPI does not expose exact history for every scalar or every same-generation
game difference. Where a field cannot be resolved at all for a generation,
PokéDB records it as `null` instead of inferring unsupported data.

PokéAPI `game_indices` are also not a complete item-introduction history: many
Generation 1–2 items only have later indices, and some current items have none.
The item catalog therefore combines structured game-index evidence with item
references from generated machines, held items, and evolution conditions. This
guarantees referentially complete output without scraping a secondary source, but it
does not claim to enumerate every unreferenced item available in each historical game.
When generating all resources, items run after moves and Pokémon so these references
are available. For the same guarantee in a partial run, regenerate `item` together
with or after the resources that reference it.

Outputs generated with schema versions 1–4 are incompatible. Regenerate the complete
dataset with `python -m pokedb --all --gen all --force`; do not mix old and new
resource files in a partial run.

Python callers can validate an existing generation explicitly:

```python
from pathlib import Path

from pokedb import validate_generation_output

validate_generation_output(Path(".output/gen9"))
```

## Schema v5 migration

Schema version 5 changes `move.machine` from a scalar into an object keyed by every target version group. Each value is an item identifier or `null` when no assignment is recorded for that game. Item catalogs include every referenced machine assignment.

Historical `evolves_from_species` is derived from the same reconstructed chain as `evolution_chain`. Historical cosmetic records contain only form-specific generation assets; when PokéAPI has no such assets, their `sprites` object is empty rather than borrowing another form's images.

The index's `metadata.generated_resources` distinguishes generated catalogs (including legitimately empty categories) from omitted catalogs. References are checked whenever their target catalog was generated. `metadata.resource_provenance` records package/dependency versions and the optional source commit for each catalog. `metadata.content_sha256` covers canonical resource JSON and relative paths.

Regenerate all output with `python -m pokedb --all --gen all --force` when upgrading from schemas 1–4. Consumers must check the schema version before loading data.

## Development and releases

See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks, the branching model, locked CI dependencies, publication safeguards, and required GitHub repository settings. Generated snapshots are published with immutable `data-v<schema>-<run-id>-<attempt>` tags; use a tag or commit in place of `data` in raw GitHub URLs to pin a dataset version.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
