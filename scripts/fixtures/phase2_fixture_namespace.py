"""Validate the database namespace before building a test-only procedure copy."""

from __future__ import annotations

import re

from scripts.pipeline.build_procedure_bundle import MODULES, REPO_ROOT


SOURCE_DATABASE = "QUAKEWATCH"
TEST_DATABASE = "QUAKEWATCH_PHASE2_FIXTURE"
QUALIFIED_OBJECT = re.compile(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b")
SQL_FILES = (
    "phase1_raw_tables.sql",
    "phase2_staging_table.sql",
    "phase2_process_attempt.sql",
    "phase2_dimensions_bridge.sql",
    "phase2_revision_current.sql",
    "phase2_batch_fact.sql",
    "phase2_create_procedure.sql",
)


def inputs() -> dict[str, str]:
    files = {f"quakewatch/{name}": (REPO_ROOT / "src" / "quakewatch" / name).read_text()
             for name in MODULES}
    files.update({f"sql/{name}": (REPO_ROOT / "sql" / name).read_text()
                  for name in SQL_FILES})
    return files


def validate_and_rewrite(path: str, source: str) -> tuple[str, int]:
    """Reject unknown qualified objects; rewrite only project database names."""
    refs = list(QUALIFIED_OBJECT.finditer(source))
    for match in refs:
        database, schema, _object = match.groups()
        if database != SOURCE_DATABASE or schema not in {"RAW", "CURATED"}:
            raise ValueError(f"{path}: unexpected qualified object {match.group()}")
    rewritten = source.replace(f"{SOURCE_DATABASE}.", f"{TEST_DATABASE}.")
    if f"{SOURCE_DATABASE}." in rewritten:
        raise ValueError(f"{path}: source database qualifier remains")
    for match in QUALIFIED_OBJECT.finditer(rewritten):
        if match.group(1) != TEST_DATABASE or match.group(2) not in {"RAW", "CURATED"}:
            raise ValueError(f"{path}: invalid rewritten object {match.group()}")
    if len(refs) != len(list(QUALIFIED_OBJECT.finditer(rewritten))):
        raise ValueError(f"{path}: qualified object count changed")
    return rewritten, len(refs)


def validate_all() -> dict[str, int]:
    return {path: validate_and_rewrite(path, source)[1]
            for path, source in inputs().items()}


def main() -> None:
    counts = validate_all()
    print("Phase 2 fixture namespace: offline validation only; no Snowflake connection")
    print(f"Files checked: {len(counts)}; qualified objects: {sum(counts.values())}")
    print(f"Test-only database: {TEST_DATABASE}; production files unchanged")


if __name__ == "__main__":
    main()
