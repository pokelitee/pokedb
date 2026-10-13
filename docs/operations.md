# Operations

See the [README](../README.md) for quick start and documentation links. General contribution policy lives in the [organization guide](https://github.com/pokelitee/.github/blob/main/CONTRIBUTING.md).

## CLI

Run `python -m pokedb --help` (or the installed `pokedb --help`) for usage. Commands execute from the runtime working directory; configuration paths follow the rules below.

| Argument | Behavior |
| --- | --- |
| `ability move item pokemon` | Select one or more parsers. |
| `--all` | Run every parser. |
| `--gen N` | Generate one positive generation number; omitted means the latest available from PokéAPI. |
| `--gen all` | Process every generation in ascending order. |
| `--no-cache` | Disable persistent API caching for this run. |
| `--force` | Replace existing output without prompting. |
| `--config PATH` | Load a partial JSON configuration override. |
| `--verbose` | Enable debug logs. |

At least one parser or `--all` is required. Errors exit with status 1, invalid arguments with status 2, and keyboard interruption with status 130.

```sh
# Complete regeneration, including historical generations
python -m pokedb --all --gen all --no-cache --force

# One generation with a custom output configuration
python -m pokedb --all --gen 3 --config config.local.json
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

## Dataset publication

The scheduled and manual update workflow only publishes from `main`. It runs the same reusable checks against the selected source commit, generates every catalog for every generation with a read-only token, and transfers a validated archive to a separate job with write access. Required API fetch failures stop generation. Publishing updates `data` and creates an annotated `data-v<schema>-<run-id>-<attempt>` tag in one atomic push. No tag is created when the dataset, provenance, and accompanying documentation are unchanged.

Consumers can pin a dataset tag or full data commit in raw GitHub URLs instead of using the mutable `data` branch. Preserve published dataset tags. Schema changes require a schema-version increment, migration documentation, and complete regeneration; partial updates cannot mix schema versions.

Like `leak-duck`, GitHub Pages serves the published `data` snapshot as JSON endpoints at `https://pokelitee.github.io/pokedb/`. `.github/workflows/deploy-pages.yml` deploys after a successful data update, when its deployment code changes on `main`, or on manual dispatch. It exports the data branch without changing resource files and adds a discovery page showing each generation's actual schema and the published data commit. Deployment does not regenerate data; older snapshots retain their existing schema. Raw GitHub URLs remain supported. The Pages source is configured as GitHub Actions.

Each index identifies generated catalogs, target game versions, a SHA-256 digest of canonical resource files, and generator/dependency provenance for each catalog. Partial regeneration retains provenance for untouched catalogs. CI supplies the full source commit through `POKEDB_GENERATOR_COMMIT`; local runs may supply it too. Without that variable the commit is `null`. Identical resource contents and provenance retain the previous snapshot timestamp.

Generation writers use an OS lock, staging, validation, and rollback. A crashed process releases its lock automatically; interrupted backups are recovered under that lock before the next run. Publication briefly renames the previous generation directory, so applications requiring uninterrupted reads should consume immutable published Git snapshots.

## GitHub repository settings

The repository's active rulesets are tracked in `.github/rulesets/` so their intended configuration can be reviewed alongside workflow changes. GitHub enforces the live settings; editing these JSON files alone does not apply them.

- Keep `main` as the default branch. Require pull requests, the `CI gate` status check, and resolved conversations before merging, with no administrator bypass. Disable force pushes and deletion of `main`.
- Allow merge, squash, and rebase merges, and automatically delete merged branches. No approving review is required while there is one maintainer, since authors cannot approve their own pull requests. Increase that requirement when another reviewer is available.
- Protect `data` against deletion and force pushes, matching `leak-duck`. Normal automation pushes remain allowed. Protect `data-v*` and `archive/dev-*` tags against modification and deletion; creation remains allowed.
- Use read-only default Actions permissions. Grant write access only to the publication job. Enable dependency alerts and secret scanning where available.

Repository administrators can create a missing ruleset with `gh api --method POST repos/pokelitee/pokedb/rulesets --input .github/rulesets/main.json`, or update an existing one using `--method PUT` and its `/rulesets/<id>` endpoint. Repeat for `data.json` and `tags.json`, then read back the live rulesets to verify them. Do not delete an existing branch until its outstanding changes have been accounted for.

## Scheduling and manual runs

`.github/workflows/update-data.yml` is scheduled for Sunday at 00:00 UTC and supports manual dispatch from `main`. GitHub schedules can be delayed. Publishers are serialized by the workflow concurrency group.

```sh
gh workflow run update-data.yml --repo pokelitee/pokedb --ref main
gh run list --repo pokelitee/pokedb --workflow update-data.yml
```

The workflow validates every generation before the write job starts. Local `--gen all` runs publish each generation independently as it succeeds; a later generation failure can leave earlier local generations updated. The remote workflow publishes none of that partial local output when generation fails.

## Troubleshooting and recovery

- **API or validation failure:** inspect the failed generation and resource in the logs. Capture a representative upstream response, reproduce offline, and fix the parser or contract before rerunning. Do not bypass validation to publish a snapshot.
- **Existing output or schema mismatch:** use a complete regeneration with `--force` when upgrading schema. Do not combine old and new resources in a partial run.
- **Writer already running:** wait for the process holding the generation lock. Locks are released by the OS when the process exits; do not remove files to work around a live writer.
- **Stale Pages content:** check both the data-update and `deploy-pages.yml` runs. Compare the discovery page's data commit with the latest `data` commit. A successful deploy alone does not regenerate data.

To serve an older immutable dataset, consumers can pin its tag or commit in raw GitHub URLs. Changing the current Pages snapshot requires a reviewed workflow or publishing change; never force-push `data` or modify an existing dataset tag.
