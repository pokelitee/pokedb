# Data contract

This is the version-controlled reference for generated PokéDB data. See the
[README](../README.md) for setup and [CONTRIBUTING.md](../CONTRIBUTING.md) for publication.


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

Identifiers originating in PokéAPI retain their exact upstream spelling, such
as `scarlet-violet`, `special-attack`, and `xtransceiver--red`. Structural field names remain snake_case.
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

An empty collection means the modeled field has no entries. `null` means a value
is unavailable, inapplicable, or not recorded by PokéAPI; its precise meaning depends
on the field. For example, a null version-group price means no price record exists,
while a null purchase amount in an existing record means the item cannot be bought.

PokéAPI does not track per-generation history for every scalar field. For
historical output, current-only Pokémon values such as base experience,
friendship, capture rate, breeding fields, growth rate, and form switching are
backfilled with their current PokéAPI value rather than discarded, as are
current-only move fields (`priority`, `target`, `metadata`, `stat_changes`) and
item fields (`fling_power`, `fling_effect`, `attributes`, `category`,
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

Python callers can validate an existing generation explicitly:

```python
from pathlib import Path

from pokedb import validate_generation_output

validate_generation_output(Path(".output/gen9"))
```

## Schema v5 migration

Schema version 5 changes `move.machine` from a scalar into an object keyed by every target version group. Each value is an item identifier or `null` when no assignment is recorded for that game. Item catalogs include every referenced machine assignment.

Items replace the removed `cost` field with `prices`, an object keyed by every target version group. A game's value is `null` when PokéAPI has no price record. Otherwise it maps currency identifiers to `purchase_price` and `sell_price`, each a non-negative integer or `null` when the item cannot be bought or sold. Prices are not inferred across games or currencies. These values come from versioned PokéAPI price records and are not listed as unverified historical fields.

Historical `evolves_from_species` is derived from the same reconstructed chain as `evolution_chain`. Historical cosmetic records contain only form-specific generation assets; when PokéAPI has no such assets, their `sprites` object is empty rather than borrowing another form's images.

The index's `metadata.generated_resources` distinguishes generated catalogs (including legitimately empty categories) from omitted catalogs. References are checked whenever their target catalog was generated. `metadata.resource_provenance` records package/dependency versions and the optional source commit for each catalog. `metadata.content_sha256` covers canonical resource JSON and relative paths.

Regenerate all output with `python -m pokedb --all --gen all --force` when upgrading from schemas 1–4. Consumers must check the schema version before loading data.

