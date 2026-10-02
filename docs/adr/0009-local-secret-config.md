# ADR 0009: Credentials live in per-user Snowflake config, not .env

**Status:** Accepted · **Decided:** 29 September 2026 · **Recorded:** 2 October 2026; example added 2 October 2026

## Context

The design planned an `.env.example`. The code instead reads Snowflake connection profiles from `~/.snowflake/config.toml`, which the Snowflake CLI also uses, and requires key-pair authentication for the project role.

## Decision

Keep credentials in the per-user Snowflake config outside the repository and prompt for the private-key passphrase in the terminal. Provide [`snowflake-config.example.toml`](../../snowflake-config.example.toml) instead of an `.env.example`.

## Consequences

- No secret is read from the repository or command-line arguments.
- Setup needs a Snowflake account and a manual key-pair registration.

**References:** [raw_load.py](../../src/quakewatch/raw_load.py)
