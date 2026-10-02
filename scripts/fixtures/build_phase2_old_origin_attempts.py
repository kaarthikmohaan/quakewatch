"""Build two local synthetic attempts for an old-origin event and later update."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.fixtures.build_phase2_fixture_attempts import OUTPUT_ROOT, build_attempts

SEQUENCE = (
    ("fixture-old-origin-original-v1", "synthetic_old_origin_original.json"),
    ("fixture-old-origin-update-v1", "synthetic_old_origin_update.json"),
)
FETCH_BASE = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)


def main() -> None:
    summaries = build_attempts(OUTPUT_ROOT, SEQUENCE, FETCH_BASE)
    print("Phase 2 old-origin attempts: local files only; no USGS or Snowflake request")
    for item in summaries:
        print(f"{item['attempt_id']}: {item['fixture']}, {item['rows']} row")
    print(f"Output: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
