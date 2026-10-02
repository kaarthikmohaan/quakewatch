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

Run everything CI runs (ruff lint and format check, mypy, fixture build, and
the secret-free tests under coverage, which must stay at or above 80%):

```sh
make check
```

Fix lint findings with `.venv/bin/ruff check --fix src scripts tests` and
formatting with `make format`. Optionally, `uvx pre-commit install` runs both
on every commit using the project's own ruff.

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

### Live integration check

The **Snowflake integration** workflow (`.github/workflows/integration.yml`)
runs `make integration EXECUTE=1` on demand from the GitHub Actions tab. It
compiles every SQL statement against Snowflake with `EXPLAIN` and runs the
read-only post-run and uniqueness checks; it never writes data. It needs four
repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `QUAKEWATCH_SNOWFLAKE_ACCOUNT` | Account identifier |
| `QUAKEWATCH_SNOWFLAKE_USER` | User whose key-pair is restricted to `QUAKEWATCH_ROLE` |
| `QUAKEWATCH_SNOWFLAKE_PRIVATE_KEY` | The encrypted private key, PEM text |
| `QUAKEWATCH_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Its passphrase |

Locally, leave these variables unset; the commands then read
`~/.snowflake/config.toml` and prompt for the passphrase.

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
