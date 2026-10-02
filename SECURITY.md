# Security policy

## Supported versions

QuakeWatch is a single-branch educational project with no numbered releases.
Only the latest commit on `main` receives security fixes.

| Version | Supported |
| --- | --- |
| Latest `main` | :white_check_mark: |
| Older commits | :x: |

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
with GitHub's [private vulnerability reporting](https://github.com/kaarthikmohaan/quakewatch/security/advisories/new).

Include what you found, how to reproduce it, and its possible impact. Expect an
acknowledgement within 7 days. This is a personal project, so fix times are
best-effort.

## In scope

- Credentials, private keys, account identifiers, or private coordinates
  committed to the repository or its history
- Code that could expose Snowflake credentials or run unintended SQL
- Unsafe handling of USGS responses or local files
- Weaknesses in the GitHub Actions workflow or its dependencies

## Out of scope

- Accuracy or completeness of USGS earthquake data. Report source problems to
  the [U.S. Geological Survey](https://earthquake.usgs.gov/contactus/).
- The project's documented limits, such as known source gaps. These are
  already listed in [observed results](docs/results.md).

QuakeWatch is not a safety system. For earthquake information, use official
USGS and local emergency-management sources.
