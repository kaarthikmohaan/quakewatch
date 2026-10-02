"""Build the standard-library-only QuakeWatch procedure import ZIP."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "quakewatch"
MODULES = (
    "__init__.py",
    "aliases.py",
    "process_batch.py",
    "process_transaction.py",
    "revisions.py",
    "settings.py",
    "site_distance.py",
    "snowpark_alias_read.py",
    "snowpark_alias_rekey.py",
    "snowpark_batch_fact_write.py",
    "snowpark_dimensions_write.py",
    "snowpark_model_writer.py",
    "snowpark_process_log.py",
    "snowpark_procedure.py",
    "snowpark_read.py",
    "snowpark_revision_write.py",
    "snowpark_staging_write.py",
    "staging.py",
)
DEFAULT_OUTPUT = REPO_ROOT / "data" / "procedure" / "quakewatch_procedure.zip"


def build_bundle(output: Path) -> str:
    """Write a reproducible ZIP containing only procedure dependency modules."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for name in MODULES:
            source = PACKAGE_ROOT / name
            member = ZipInfo(f"quakewatch/{name}", date_time=(2020, 1, 1, 0, 0, 0))
            member.compress_type = ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            archive.writestr(member, source.read_bytes())
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    digest = build_bundle(args.output)
    print(f"Bundle: {args.output}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
