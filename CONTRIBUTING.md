# Contributing

Use short-lived feature or fix branches and open pull requests into `main`. All changes to `main` require a pull request and a passing `CI gate`, including changes by administrators. Resolve review conversations before merging. Squash merging focused changes is recommended; merge and rebase remain available, matching the other organization repositories. GitHub automatically deletes merged branches.

The `data` branch contains generated artifacts only; do not merge it into source branches or edit its datasets by hand. Like `leak-duck`, it accepts normal automated data updates while its history is protected against deletion and force pushes. It does not require a pull request for every generated snapshot. There is no permanent `dev` branch. Unmerged work from the retired branch is preserved at the annotated `archive/dev-2026-10-13` tag; that artwork change has not been merged into `main`.

## Local checks

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

## Dataset publication

The scheduled and manual update workflow only publishes from `main`. It runs the same reusable checks against the selected source commit, generates every catalog for every generation with a read-only token, and transfers a validated archive to a separate job with write access. Required API fetch failures stop generation. Publishing updates `data` and creates an annotated `data-v<schema>-<run-id>-<attempt>` tag in one atomic push. No tag is created when the dataset, provenance, and accompanying documentation are unchanged.

Consumers can pin a dataset tag or full data commit in raw GitHub URLs instead of using the mutable `data` branch. Preserve published dataset tags. Schema changes require a schema-version increment, migration documentation, and complete regeneration; partial updates cannot mix schema versions.

Like `leak-duck`, GitHub Pages serves the published `data` snapshot as JSON endpoints at `https://pokelitee.github.io/pokedb/`. `.github/workflows/deploy-pages.yaml` deploys after a successful data update, when its deployment code changes on `main`, or on manual dispatch. It exports the data branch without changing resource files and adds a discovery page showing each generation's actual schema and the published data commit. Deployment does not regenerate data; older snapshots retain their existing schema. Raw GitHub URLs remain supported. The Pages source is configured as GitHub Actions.

Each index identifies generated catalogs, target game versions, a SHA-256 digest of canonical resource files, and generator/dependency provenance for each catalog. Partial regeneration retains provenance for untouched catalogs. CI supplies the full source commit through `POKEDB_GENERATOR_COMMIT`; local runs may supply it too. Without that variable the commit is `null`. Identical resource contents and provenance retain the previous snapshot timestamp.

Generation writers use an OS lock, staging, validation, and rollback. A crashed process releases its lock automatically; interrupted backups are recovered under that lock before the next run. Publication briefly renames the previous generation directory, so applications requiring uninterrupted reads should consume immutable published Git snapshots.

## GitHub repository settings

The repository's active rulesets are tracked in `.github/rulesets/` so their intended configuration can be reviewed alongside workflow changes. GitHub enforces the live settings; editing these JSON files alone does not apply them.

- Keep `main` as the default branch. Require pull requests, the `CI gate` status check, and resolved conversations before merging, with no administrator bypass. Disable force pushes and deletion of `main`.
- Allow merge, squash, and rebase merges, and automatically delete merged branches. No approving review is required while there is one maintainer, since authors cannot approve their own pull requests. Increase that requirement when another reviewer is available.
- Protect `data` against deletion and force pushes, matching `leak-duck`. Normal automation pushes remain allowed. Protect `data-v*` and `archive/dev-*` tags against modification and deletion; creation remains allowed.
- Use read-only default Actions permissions. Grant write access only to the publication job. Enable dependency alerts and secret scanning where available.

Repository administrators can create a missing ruleset with `gh api --method POST repos/pokelitee/pokedb/rulesets --input .github/rulesets/main.json`, or update an existing one using `--method PUT` and its `/rulesets/<id>` endpoint. Repeat for `data.json` and `tags.json`, then read back the live rulesets to verify them. Do not delete an existing branch until its outstanding changes have been accounted for.
