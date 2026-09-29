# QuakeWatch project guide

## Workflow

- Guide the owner as a data engineer, one small step at a time. At the start of each update, state the current phase and step, what is done, and what comes next.
- Before each step, briefly explain what we are doing, why it matters, and how it fits the project. Give exact commands or code and the expected result, then wait for the owner's output or confirmation before continuing.
- Explain questions patiently. When something fails, describe the cause in plain language and give the smallest useful fix.
- Follow `docs/design.md` phases 0 through 4 in order. Check a phase's completion criteria with the owner before moving on. Keep targets distinct from measured results and keep relevant documentation current in the same change.

## Design and scope

- Treat `docs/design.md` and accepted ADRs in `docs/adr/` as the project plan. Read relevant guidance before changing architecture.
- The design is frozen. For a needed design change, propose the next numbered ADR with reasons and trade-offs, then wait for approval before implementing it.
- Keep the core project a retrospective Snowflake batch warehouse using USGS FDSN GeoJSON. Preserve source records, audit bounded query windows, reconcile counts, and report unresolved coverage gaps honestly.
- Snowpark runs inside Snowflake procedures. Check the account's supported runtime and packages before choosing procedure dependencies.
- Do not add optional/post-MVP or out-of-scope features to the core build. Do not describe the project as streaming or add Snowpipe Streaming, Kafka, or similar streaming infrastructure.
- Write tests alongside implementation, use small Conventional Commit messages, and update relevant documentation in the same change.

## Safety and account operations

- Keep passwords, private keys, and private site coordinates out of Git and chat. Store credentials outside the repository.
- Before any action that may cost money, including Snowflake compute, Cortex, paid services, or purchases, explain the expected cost and ask the owner first.
- Ask before deleting data or pushing anything to GitHub.
- Use a dedicated project role for the pipeline; use an administrator role only for account provisioning.
