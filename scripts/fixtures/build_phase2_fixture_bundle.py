"""Build an ignored, test-only procedure ZIP and SQL from validated sources."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from scripts.pipeline.build_procedure_bundle import REPO_ROOT
from scripts.fixtures.phase2_fixture_namespace import TEST_DATABASE, inputs, validate_and_rewrite


DEFAULT_OUTPUT = REPO_ROOT / "data" / "procedure" / "phase2_fixture"


def build_fixture_copy(output_dir: Path) -> tuple[str, int]:
    """Write only under the requested output directory after all inputs pass."""
    rewritten = {path: validate_and_rewrite(path, source)[0]
                 for path, source in inputs().items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / "quakewatch_procedure.zip"
    with ZipFile(bundle_path, "w") as archive:
        for path, source in rewritten.items():
            if not path.startswith("quakewatch/"):
                continue
            member = ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            archive.writestr(member, source.encode("utf-8"))
    sql_dir = output_dir / "sql"
    sql_dir.mkdir(exist_ok=True)
    for path, source in rewritten.items():
        if path.startswith("sql/"):
            (output_dir / path).write_text(source, encoding="utf-8")
    with ZipFile(bundle_path) as archive:
        for name in archive.namelist():
            body = archive.read(name)
            if b"QUAKEWATCH.RAW." in body or b"QUAKEWATCH.CURATED." in body:
                raise ValueError(f"production reference in ZIP member {name}")
    for path in rewritten:
        if path.startswith("sql/"):
            body = (output_dir / path).read_text(encoding="utf-8")
            if "QUAKEWATCH.RAW." in body or "QUAKEWATCH.CURATED." in body:
                raise ValueError(f"production reference in generated {path}")
    return hashlib.sha256(bundle_path.read_bytes()).hexdigest(), len(rewritten)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    digest, file_count = build_fixture_copy(args.output_dir)
    print(f"Test-only database namespace: {TEST_DATABASE}")
    print(f"Generated files: {file_count}; output: {args.output_dir}")
    print(f"Procedure ZIP SHA-256: {digest}")
    print("Offline only; no Snowflake connection or schema changes")


if __name__ == "__main__":
    main()
