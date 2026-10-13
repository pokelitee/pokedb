# Contributing

Use short-lived feature or fix branches and open pull requests into `main`. Squash merge focused changes and delete merged branches. The `data` branch contains generated artifacts only; do not merge it into source branches or edit its datasets by hand. A permanent `dev` branch is not required. Any existing unmerged work on it must be reviewed before retiring it.

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

Each index identifies generated catalogs, target game versions, a SHA-256 digest of canonical resource files, and generator/dependency provenance for each catalog. Partial regeneration retains provenance for untouched catalogs. CI supplies the full source commit through `POKEDB_GENERATOR_COMMIT`; local runs may supply it too. Without that variable the commit is `null`. Identical resource contents and provenance retain the previous snapshot timestamp.

Generation writers use an OS lock, staging, validation, and rollback. A crashed process releases its lock automatically; interrupted backups are recovered under that lock before the next run. Publication briefly renames the previous generation directory, so applications requiring uninterrupted reads should consume immutable published Git snapshots.

## GitHub repository settings

These settings are managed in GitHub, separately from the tracked workflow files:

- Set the default branch to `main`; require pull requests, the `CI gate` status check, and resolved conversations before merging. Disable force pushes and deletion of `main`.
- Enable squash merges and automatic deletion of merged branches. Require a reviewer when another maintainer is available.
- Restrict human writes to `data` while allowing the publishing automation to update it. Protect `data-v*` tags against modification and deletion, while allowing the workflow to create them.
- Use read-only default Actions permissions. Grant write access only to the publication job. Enable dependency alerts and secret scanning where available.

Repository administrators must apply and verify these settings in the organization. Do not delete an existing branch until its outstanding changes have been accounted for.
