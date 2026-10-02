# Contributing to QuakeWatch

Thanks for your interest. QuakeWatch is a small, retrospective Snowflake batch
warehouse for historical USGS earthquake records. Questions, bug reports,
documentation fixes, and design feedback are all welcome.

Please read the [code of conduct](CODE_OF_CONDUCT.md) first.

## Before you start

- Read the [design](docs/design.md). It is the project plan; architecture
  changes need a written proposal with reasons and trade-offs before any code.
- Keep the scope: bounded batch extracts from the USGS FDSN GeoJSON API into
  Snowflake. Streaming infrastructure (Snowpipe Streaming, Kafka, and similar)
  is out of scope.
- QuakeWatch is not safety guidance. Do not add warnings, risk scores, shaking
  estimates, or damage assessments.
- For larger changes, open an issue or discussion first so we can agree on the
  approach.

## Local setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked --no-editable
```

Run the secret-free test suite, exactly as CI does:

```sh
PYTHONPATH=src:. .venv/bin/python scripts/build_phase2_fixture_bundle.py
PYTHONPATH=src:. .venv/bin/python scripts/build_phase2_fixture_attempts.py
PYTHONPATH=src:. .venv/bin/python scripts/build_phase2_old_origin_attempts.py
PYTHONPATH=src:. .venv/bin/python -m unittest discover -s tests
```

After changing package code, run `uv sync --locked --no-editable` again.

## Making a change

1. Fork the repository and create a branch from `main`.
2. Write or update tests in the same change. Tests must not need Snowflake
   credentials or network access.
3. Update the relevant documentation in the same change. Keep targets
   separate from measured results, and never present an estimate as evidence.
4. Use small [Conventional Commits](https://www.conventionalcommits.org/),
   for example `fix(extract): retry on 503` or `docs(runbook): clarify load`.
5. Open a pull request and complete the template.

## Snowflake and cost

Live Snowflake runs use warehouse credits, and Cortex uses separate AI
credits. Contributors are never expected to run them. If your change needs a
live check, say so in the pull request and the maintainer will decide whether
to run it.

## Secrets and private data

Never commit passwords, private keys, account identifiers, `.env` files, or
private site coordinates. Use only the public example sites in issues, pull
requests, and fixtures. If you find a secret in the repository, follow the
[security policy](SECURITY.md) instead of opening a public issue.

## Data source

Earthquake records come from the U.S. Geological Survey. Credit USGS and link
to official records when presenting data.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
