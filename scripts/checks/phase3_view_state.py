"""Inspect existing Phase 3 view definitions without modifying Snowflake."""

from __future__ import annotations

import hashlib
import json
import argparse

from quakewatch.raw_load import connect_project


NAMES = ("V_BATCH_HEALTH", "V_RECEIPT_WINDOW_AUDIT", "V_EVENT_REJECTS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definitions", action="store_true",
                        help="include full SQL definitions for exact review")
    args = parser.parse_args()
    with connect_project() as connection:
        with connection.cursor() as cursor:
            cursor.execute("USE ROLE QUAKEWATCH_ROLE")
            cursor.execute("""
                SELECT TABLE_NAME, VIEW_DEFINITION
                FROM QUAKEWATCH.INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME IN ('V_BATCH_HEALTH', 'V_RECEIPT_WINDOW_AUDIT',
                                     'V_EVENT_REJECTS')
                ORDER BY TABLE_NAME
            """)
            views = []
            for name, definition in cursor.fetchall():
                body = definition or ""
                views.append({
                    "name": name,
                    "definition_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "definition_visible": bool(body),
                    "null_count_guards": (
                        "PROCESSED_ROWS IS NULL" in body.upper()
                        and "REJECTED_ROWS IS NULL" in body.upper()
                    ) if name == "V_BATCH_HEALTH" else None,
                    **({"definition": body} if args.definitions else {}),
                })
    print(json.dumps({"existing_views": views, "missing_views": sorted(set(NAMES) - {
        view["name"] for view in views
    })}, indent=2))


if __name__ == "__main__":
    main()
